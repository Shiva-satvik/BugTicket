"""Fast BugPilot analysis pipeline (single LLM call).

The original 5-node LangGraph workflow makes three sequential LLM calls
(understand -> analyze -> confidence explanation), which on a local Ollama
model costs 5-6 minutes per ticket. This pipeline produces the same output
contract with ONE merged LLM call:

    1. RAG retrieval first (FTS + semantic + financial documents; no LLM,
       typically 2-5 seconds; it only needs the raw ticket text).
    2. ONE merged JSON call returning understanding + analysis +
       evidence-backed confidence notes.
    3. Confidence score computed in pure Python (reuses the Confidence
       Agent's deterministic formula) and the user-facing reason assembled
       from the model's own notes - no third LLM call.

Set BUGPILOT_PIPELINE=accurate to keep the original graph behavior.

Notes on this version:
- The LLM call goes through the multi-provider llm_service (Ollama, then
  Hugging Face in auto mode).
- Small local models sometimes return slightly malformed JSON (missing
  commas, trailing commas, truncated tail). The reply is now parsed with a
  tolerant parser and, if it is still unusable, the call is retried once
  before the degraded fallback is used. The raw model output is logged on
  every failed attempt so the real cause is visible.
- The degraded fallback text no longer blames "Ollama" specifically and
  points at GET /api/ai/status for live diagnostics.
"""

import json
import logging
import re
import time

from app.services.llm_service import generate_response
from app.rag.context_builder import build_rag_context_with_diagnostics
from app.agents.confidence_agent import calculate_confidence_score
from app.agents.analysis_agent import validate_analysis_response

logger = logging.getLogger(__name__)

# Output budget for the merged call. The response contains ~11 fields and
# llama3.2 tends to compress long lists when the budget is tight, so the
# budget is generous (the service layer clamps it to its own maximum).
MERGED_NUM_PREDICT = 1400

# Number of attempts for the merged LLM call before using the fallback.
MERGED_MAX_ATTEMPTS = 2

# Retrieved evidence fed to the model. 3000 chars keeps the merged prompt
# well inside the configured context window (OLLAMA_NUM_CTX) so Ollama does
# not silently truncate or context-shift.
CONTEXT_CHAR_LIMIT = 3000

# Lightweight module/category rules used only by the degraded fallback
# (mirrors the Ticket Understanding Agent's heuristic table).
_FALLBACK_RULES = [
    (("payroll", "salary", "payslip", "overtime"), "Payroll", "Payroll"),
    (("invoice", "vendor", "payable", "goods receipt"), "Accounts Payable", "Finance"),
    (("expense", "reimbursement", "claim"), "Expense Reimbursement", "Finance"),
    (("payment", "bank", "credited", "transfer"), "Vendor Payments", "Finance"),
    (("access", "permission", "role", "denied", "login"), "Access Management", "Security"),
    (("report", "export", "download"), "Reporting", "ERP"),
]


def _clean_json_response(response: str) -> str:
    """Remove Markdown fences and isolate the outer JSON object."""
    response = (response or "").strip()
    if response.startswith("```"):
        lines = response.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        response = "\n".join(lines).strip()

    first_brace = response.find("{")
    last_brace = response.rfind("}")
    if first_brace >= 0 and last_brace > first_brace:
        response = response[first_brace:last_brace + 1]
    return response


def _close_truncated_json(text: str) -> str:
    """Close an unterminated string / arrays / objects (output cut off early)."""
    stack = []
    in_str = False
    esc = False
    for ch in text:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch in "{[":
                stack.append("}" if ch == "{" else "]")
            elif ch in "}]" and stack:
                stack.pop()
    if in_str:
        text += '"'
    text = re.sub(r",\s*$", "", text)
    return text + "".join(reversed(stack))


def _repair_json_text(text: str) -> str:
    """Best-effort repair of the usual small-model JSON mistakes."""
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    # Missing comma between two lines:  "a": "x"\n  "b": ...
    text = re.sub(r'(["\]}]|\d|true|false|null)(\s*\n\s*)"', r'\1,\2"', text)
    # Trailing commas before a closing bracket/brace.
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    text = _close_truncated_json(text)
    return re.sub(r",(\s*[}\]])", r"\1", text)


def _parse_llm_json(response: str) -> dict:
    """Parse model output: strict first, then repaired / truncation-closed."""
    response = response or ""
    candidates = [_clean_json_response(response)]
    start = response.find("{")
    if start >= 0:
        candidates.append(response[start:])  # keeps a truncated tail

    last_exc = None
    for candidate in candidates:
        for fix in (lambda s: s, _repair_json_text):
            try:
                return json.loads(fix(candidate), strict=False)
            except json.JSONDecodeError as exc:
                last_exc = exc
    if last_exc is None:
        raise ValueError("LLM response contained no JSON object.")
    raise last_exc


def _merged_prompt(ticket: str, retrieved_context: str) -> str:
    return f"""
You are BugPilot, a senior enterprise software bug analyst.
Understand and analyze THIS ticket using only the ticket details and retrieved evidence below. Do not invent facts, records, or policies. Historical records are leads, not proof of the current root cause. Clearly state uncertainty.

SPECIFICITY RULES (highest priority):
- Every ticket is different. Your output must be recognizably about THIS ticket's exact symptom, module and error.
- In "analysis" and "historical_evidence", cite the concrete ticket codes (e.g. BP-2026-000549) and document codes (e.g. FD-007) found in the retrieved evidence, and state in one sentence HOW each connects to this ticket. If no evidence was retrieved, say so plainly.
- "suggested_resolution" MUST contain AT LEAST 3 numbered steps (3-5 is ideal, never 1 or 2). Each step's target comes from THIS ticket and the evidence: name the exact interface/module/record type/error pattern to inspect and the specific observation that confirms or rules out each step.
- In "likely_cause", name the single most probable cause for THIS ticket and the strongest piece of evidence supporting it. If unconfirmed, add the specific finding that would confirm it.
- If the evidence lacks detail needed for a specific step, put the exact missing item in "missing_information" instead of writing vague text.

TICKET:
{ticket}

RETRIEVED HISTORICAL TICKETS / DOCUMENTS:
{retrieved_context[:CONTEXT_CHAR_LIMIT]}

Return ONLY one valid JSON object with exactly these fields:
{{
  "summary": "Short issue summary, max 20 words. Do not copy the ticket title verbatim; state the suspected cause and affected module.",
  "category": "Issue category",
  "module": "Affected module",
  "problem": "The reported problem restated specifically",
  "keywords": ["3 to 8 short relevant keywords"],
  "analysis": "2-4 sentences: specific symptom, affected area, impact, supporting evidence, and uncertainty.",
  "historical_evidence": "Mention the relevant record codes from the evidence and explain how each relates to this ticket. Do not invent outcomes.",
  "severity": "Low, Medium, High, or Critical",
  "priority": "P1, P2, P3, or P4",
  "likely_cause": "Most probable cause for THIS ticket, naming the supporting evidence; say if unconfirmed.",
  "suggested_resolution": "Numbered concrete steps, each with a specific target from this ticket/evidence, plus validation.",
  "missing_information": ["Specific information needed to confirm the cause"],
  "confidence_notes": "2-3 sentences for the user: what evidence supports this assessment and what remains uncertain. Never mention scores, weights, formulas, embeddings, or internal calculations."
}}

Choose severity and priority based on demonstrated impact, not merely because the issue concerns payroll/finance. Use valid JSON with double quotes, a comma after every field except the last, no trailing commas, and no Markdown fences. Write complete, specific values for every field; never abbreviate the resolution list to finish early.
"""


def _validate_merged_response(data: dict, ticket: str) -> dict:
    """
    Tolerant validation for the merged response.

    The analysis half is normalized by the Analysis Agent's validator
    (missing fields get sensible defaults instead of failing the run);
    the understanding half and confidence notes are normalized here.
    """
    if not isinstance(data, dict):
        raise ValueError("BugPilot merged response must be a JSON object.")

    def _text(field: str, default: str) -> str:
        value = data.get(field)
        if value is None:
            return default
        cleaned = str(value).strip()
        return cleaned or default

    keywords = data.get("keywords")
    if keywords is None:
        keywords = []
    elif isinstance(keywords, str):
        keywords = [keywords]
    elif not isinstance(keywords, list):
        keywords = []
    keywords = [str(k).strip() for k in keywords if str(k).strip()]

    analysis_half = validate_analysis_response(data)

    return {
        "summary": _text("summary", ticket[:160]),
        "category": _text("category", "Unknown"),
        "module": _text("module", "Unknown"),
        "problem": _text("problem", ticket),
        "keywords": keywords,
        **analysis_half,
        "confidence_notes": _text("confidence_notes", ""),
    }


def _retrieval_fallback_context() -> tuple[str, dict]:
    context = (
        "RETRIEVED HISTORICAL TICKETS\n"
        "No matching historical tickets were retrieved.\n\n"
        "RETRIEVED FINANCIAL SOPs AND POLICIES\n"
        "No relevant active financial document matched this query."
    )
    diagnostics = {
        "ticket_count": 0,
        "vector_count": None,
        "ticket_sources": [],
        "financial_document_count": 0,
        "financial_document_sources": [],
        "keyword_search": "not_run",
        "semantic_search": "not_run",
        "financial_document_search": "not_run",
        "keyword_error": None,
        "semantic_error": None,
        "financial_document_error": None,
    }
    return context, diagnostics


def _empty_diagnostics_error(error: str) -> dict:
    diagnostics = _retrieval_fallback_context()[1]
    diagnostics["keyword_error"] = error
    return diagnostics


def _heuristic_understanding(ticket: str) -> dict:
    """Rule-based understanding used only when the LLM call fails."""
    lower = ticket.lower()

    module = "Unknown"
    category = "ERP"
    for terms, candidate_module, candidate_category in _FALLBACK_RULES:
        if any(term in lower for term in terms):
            module = candidate_module
            category = candidate_category
            break

    words = re.findall(r"[a-zA-Z0-9]+", lower)
    keywords = list(dict.fromkeys(
        word for word in words if len(word) > 2
    ))[:12]

    return {
        "summary": ticket[:160],
        "category": category,
        "module": module,
        "problem": ticket,
        "keywords": keywords,
    }


def _fallback_result(ticket: str, retrieved_context: str, diagnostics: dict, error: Exception) -> dict:
    """Retrieval-grounded fallback, explicitly labeled (mirrors the Analysis Agent)."""
    understanding = _heuristic_understanding(ticket)

    blocks = [line.strip() for line in retrieved_context.splitlines() if line.strip()]
    ticket_sources = [
        line.split(":", 1)[1].strip()
        for line in blocks
        if line.lower().startswith("ticket code:")
    ]
    doc_sources = [
        line.split(":", 1)[1].strip()
        for line in blocks
        if line.lower().startswith("document code:")
    ]
    evidence_names = ticket_sources + doc_sources
    has_evidence = bool(evidence_names)

    lower = ticket.lower()
    severity = (
        "High"
        if any(term in lower for term in ["blocked", "denied", "failed", "cannot", "unable", "error", "incorrect"])
        else "Medium"
    )

    if has_evidence:
        evidence_text = "Retrieved evidence available: " + ", ".join(evidence_names[:8]) + "."
    else:
        evidence_text = "No historical ticket or financial-document evidence was returned by retrieval for this query."

    # This text is what the user sees as the "standard response" when the AI
    # provider is down or returns unusable output. Keep it explicit and
    # actionable instead of quietly returning boilerplate.
    analysis_text = (
        "AI model call failed, so this is a rule-based fallback, not an LLM-generated analysis. "
        + evidence_text + " "
        + f"Provider error: {type(error).__name__}: {str(error)[:250]} "
        + "Fix: check GET /api/ai/status for live provider health. If the error mentions "
        "JSONDecodeError, the model replied but returned malformed JSON; simply retry. "
        "If Ollama is not running, start it (ollama serve) and make sure the model is pulled "
        "(ollama pull llama3.2:latest). HF_TOKEN in .env enables the Hugging Face fallback."
    )
    cause = (
        "The retrieved historical tickets and financial documents should be compared with the reported symptoms; "
        "they provide investigation leads, not proof of the root cause."
        if has_evidence
        else "The root cause cannot be confirmed because no supporting historical or financial-document evidence was retrieved and the LLM call failed."
    )
    resolution = (
        "1. Capture the exact ERP error, timestamp, affected record and user role. "
        "2. Compare the issue with the retrieved historical tickets and applicable financial SOP/policy passages listed above. "
        "3. Verify the relevant database records, approval state and permissions. "
        "4. Apply only a confirmed correction and retest the same workflow."
    )

    return {
        "ticket": ticket,
        "understanding": json.dumps(understanding, ensure_ascii=False),
        **understanding,
        "retrieved_context": retrieved_context,
        "retrieval_diagnostics": diagnostics,
        "analysis": analysis_text,
        "historical_evidence": evidence_text,
        "severity": severity,
        "priority": "P2" if severity == "High" else "P3",
        "likely_cause": cause,
        "suggested_resolution": resolution,
        "missing_information": [
            "Exact error message and code",
            "Timestamp and affected record",
            "Steps to reproduce",
            "User role and approval state",
        ],
        "llm_status": "degraded",
        "llm_error": f"Merged analysis LLM call failed: {type(error).__name__}: {str(error)[:350]}",
        "ticket_understanding_status": "degraded",
        "ticket_understanding_error": "",
        "analysis_mode": (
            "retrieval_grounded_fallback" if has_evidence else "no_evidence_fallback"
        ),
    }


def _build_confidence_reason(
    confidence_score: int,
    confidence_level: str,
    confidence_notes: str,
    diagnostics: dict,
    llm_status: str,
) -> str:
    """Assemble the user-facing confidence explanation without an LLM call."""
    ticket_count = int((diagnostics or {}).get("ticket_count", 0) or 0)
    document_count = int((diagnostics or {}).get("financial_document_count", 0) or 0)

    if llm_status != "available":
        evidence_bits = []
        if ticket_count:
            evidence_bits.append(f"{ticket_count} historical ticket(s) were retrieved")
        if document_count:
            evidence_bits.append(f"{document_count} financial SOP/policy document(s) were retrieved")
        evidence_summary = " and ".join(evidence_bits) if evidence_bits else "no supporting retrieval evidence was found"
        return (
            f"Confidence is {confidence_level.lower()} ({confidence_score}%). "
            "Part of the workflow used a fallback instead of the language model. "
            f"Retrieval status: {evidence_summary}. "
            "The recommendation is an investigation aid, not a confirmed root cause. "
            "Confirm the evidence against the ERP records and retest before applying a fix."
        )

    if ticket_count or document_count:
        parts = []
        if ticket_count:
            parts.append(f"{ticket_count} related historical ticket(s)")
        if document_count:
            parts.append(f"{document_count} financial SOP/policy document(s)")
        evidence_sentence = (
            " The assessment draws on " + " and ".join(parts) + " retrieved for this ticket."
        )
    else:
        evidence_sentence = (
            " No matching historical tickets or financial documents were retrieved, "
            "so the assessment relies on the ticket details alone."
        )

    caveat = (
        ""
        if confidence_level == "High"
        else " Treat the recommendation as an investigation aid and confirm the root cause against the system records before applying a fix."
    )

    notes = (confidence_notes or "").strip()
    if notes:
        return (
            f"Confidence is {confidence_level.lower()} ({confidence_score}%). "
            f"{notes}{evidence_sentence}{caveat}"
        )

    return (
        f"Confidence is {confidence_level.lower()} ({confidence_score}%). "
        "The assessment is based on the ticket details and the evidence BugPilot could retrieve."
        f"{evidence_sentence}{caveat}"
    )


_STEP_PREFIX_RE = re.compile(r"^\s*\d+(?:\.\d+)*[.)]?\s+")
_INLINE_STEP_RE = re.compile(r"(?:^|\s)\d+(?:\.\d+)*[.)]\s+")


def _split_resolution_steps(resolution: str) -> list:
    """Split a resolution string into individual step strings."""
    steps = []
    for raw_line in str(resolution or "").splitlines():
        line = _STEP_PREFIX_RE.sub("", raw_line.strip(), count=1).strip()
        if line:
            steps.append(line)
    if len(steps) <= 1 and steps:
        parts = [
            part.strip(" .;")
            for part in _INLINE_STEP_RE.split(steps[0])
            if part and part.strip(" .;")
        ]
        if len(parts) > 1:
            steps = parts
    return steps


def _enrich_resolution(resolution: str, module: str, evidence: str) -> str:
    """
    Guarantee a well-numbered, sufficiently detailed resolution list.

    Small local models occasionally return a single step or odd numbering
    such as "1.1". This normalizes the numbering to 1..N and, when fewer
    than three steps were returned, appends grounded, non-duplicative
    steps that reference the affected module and the retrieved evidence
    codes, so reports never ship with a thin single-line resolution.
    """
    seen = set()
    steps = []
    for step in _split_resolution_steps(resolution):
        key = re.sub(r"[^a-z0-9]+", "", step.lower())[:60]
        if key and key not in seen:
            seen.add(key)
            steps.append(step)

    if len(steps) < 3:
        module_label = (module or "the affected module").strip() or "the affected module"
        evidence = evidence or ""
        fd_codes = sorted(set(re.findall(r"\bFD-\d+(?:-\d+)*\b", evidence)))
        bp_codes = sorted(set(re.findall(r"\bBP-\d+(?:-\d+)*\b", evidence)))
        doc_ref = (
            "the retrieved policy document(s) " + ", ".join(fd_codes[:2])
            if fd_codes
            else "the governing policy or SOP"
        )
        candidates = [
            (
                f"Reproduce the issue with the reporting user's account in {module_label} and "
                "capture the exact error message, screen, and timestamp."
            ),
            (
                f"Compare the {module_label} access configuration and role permissions against "
                f"{doc_ref}; record any deviation found."
            ),
        ]
        if bp_codes:
            candidates.append(
                f"Review the outcome of the similar historical ticket(s) {', '.join(bp_codes[:2])} "
                "and check whether the same root cause or fix still applies."
            )
        candidates.extend(
            [
                (
                    f"Check recent change and audit logs for {module_label} around the first "
                    "occurrence to identify a triggering change or regression."
                ),
                (
                    "Apply the corrective change, verify the outcome with the reporting user, and "
                    "document the fix for future triage."
                ),
            ]
        )
        for candidate in candidates:
            if len(steps) >= 3:
                break
            key = re.sub(r"[^a-z0-9]+", "", candidate.lower())[:60]
            if key not in seen:
                seen.add(key)
                steps.append(candidate)

    return "\n".join(
        f"{index}. {step}" for index, step in enumerate(steps, start=1)
    )


def run_fast_pipeline(ticket: str) -> dict:
    """
    Analyze one ticket with a single LLM call (retried once on unusable output).

    Returns the same state keys the original LangGraph workflow produced,
    so the API layer and the analyzed-history storage need no changes.
    """
    ticket = str(ticket or "").strip()
    if not ticket:
        raise ValueError("Fast pipeline received an empty ticket.")

    started = time.monotonic()

    # ------------------------------------------------------------
    # STEP 1: RAG retrieval (no LLM; only needs the raw ticket text)
    # ------------------------------------------------------------
    try:
        retrieved_context, retrieval_diagnostics = build_rag_context_with_diagnostics(
            query=ticket,
            k=5,
        )
    except Exception as exc:
        logger.exception("RAG retrieval failed; continuing with empty evidence")
        retrieved_context, retrieval_diagnostics = _retrieval_fallback_context()
        retrieval_diagnostics = _empty_diagnostics_error(
            f"{type(exc).__name__}: {exc}"
        )

    # ------------------------------------------------------------
    # STEP 2: single merged LLM call (understanding + analysis)
    # ------------------------------------------------------------
    try:
        validated = None
        last_error = None
        prompt = _merged_prompt(ticket, retrieved_context)

        for attempt in range(1, MERGED_MAX_ATTEMPTS + 1):
            response = generate_response(
                prompt,
                response_format="json",
                num_predict=MERGED_NUM_PREDICT,
            )
            if not isinstance(response, str) or not response.strip():
                last_error = RuntimeError("LLM returned an empty merged analysis response.")
                logger.warning("Merged analysis attempt %d returned an empty response", attempt)
                continue
            try:
                data = _parse_llm_json(response)
                validated = _validate_merged_response(data, ticket)
                break
            except Exception as exc:
                last_error = exc
                # Log the raw model output so the real failure is visible.
                logger.warning(
                    "Merged analysis attempt %d returned unusable JSON (%s). Raw output: %.800s",
                    attempt,
                    exc,
                    response,
                )

        if validated is None:
            raise last_error or RuntimeError("Merged analysis produced no result.")

        validated["suggested_resolution"] = _enrich_resolution(
            validated["suggested_resolution"],
            validated["module"],
            retrieved_context,
        )

        llm_status = "available"
        llm_error = ""
        analysis_mode = "llm_rag_fast"

    except Exception as error:
        logger.exception("Merged analysis call failed; using retrieval-grounded fallback")
        fallback = _fallback_result(ticket, retrieved_context, retrieval_diagnostics, error)
        fallback["suggested_resolution"] = _enrich_resolution(
            fallback.get("suggested_resolution", ""),
            fallback.get("module", ""),
            retrieved_context,
        )

        # Confidence still computed deterministically for the fallback result.
        confidence = calculate_confidence_score(fallback)
        fallback["confidence_score"] = confidence["confidence_score"]
        fallback["confidence_level"] = confidence["confidence_level"]
        fallback["confidence_reason"] = _build_confidence_reason(
            confidence["confidence_score"],
            confidence["confidence_level"],
            "",
            retrieval_diagnostics,
            "degraded",
        )
        logger.info(
            "Fast pipeline (fallback) completed in %.2f seconds",
            time.monotonic() - started,
        )
        return fallback

    # ------------------------------------------------------------
    # STEP 3: deterministic confidence score + assembled reason
    # ------------------------------------------------------------
    confidence_state = {
        "retrieved_context": retrieved_context,
        "keywords": validated["keywords"],
        "module": validated["module"],
        "category": validated["category"],
        "analysis": validated["analysis"],
        "historical_evidence": validated["historical_evidence"],
        "likely_cause": validated["likely_cause"],
        "suggested_resolution": validated["suggested_resolution"],
        "severity": validated["severity"],
        "priority": validated["priority"],
    }
    confidence = calculate_confidence_score(confidence_state)
    confidence_reason = _build_confidence_reason(
        confidence["confidence_score"],
        confidence["confidence_level"],
        validated["confidence_notes"],
        retrieval_diagnostics,
        llm_status,
    )

    result = {
        "ticket": ticket,
        "understanding": json.dumps(
            {
                "summary": validated["summary"],
                "category": validated["category"],
                "module": validated["module"],
                "problem": validated["problem"],
                "keywords": validated["keywords"],
            },
            ensure_ascii=False,
        ),
        "summary": validated["summary"],
        "category": validated["category"],
        "module": validated["module"],
        "problem": validated["problem"],
        "keywords": validated["keywords"],
        "retrieved_context": retrieved_context,
        "retrieval_diagnostics": retrieval_diagnostics,
        "analysis": validated["analysis"],
        "historical_evidence": validated["historical_evidence"],
        "severity": validated["severity"],
        "priority": validated["priority"],
        "likely_cause": validated["likely_cause"],
        "suggested_resolution": validated["suggested_resolution"],
        "missing_information": validated["missing_information"],
        "confidence_score": confidence["confidence_score"],
        "confidence_level": confidence["confidence_level"],
        "confidence_reason": confidence_reason,
        "llm_status": llm_status,
        "llm_error": llm_error,
        "ticket_understanding_status": "available",
        "ticket_understanding_error": "",
        "analysis_mode": analysis_mode,
    }

    logger.info(
        "Fast pipeline completed in %.2f seconds (LLM call attempts allowed: %d)",
        time.monotonic() - started,
        MERGED_MAX_ATTEMPTS,
    )

    return result
