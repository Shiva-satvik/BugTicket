import json
import re
from typing import TypedDict

from langgraph.graph import StateGraph, START, END

from app.services.llm_service import generate_response

# ============================================================
# CONFIDENCE STATE
# ============================================================


class ConfidenceState(TypedDict):

    ticket: str

    understanding: str
    summary: str
    category: str
    module: str
    problem: str
    keywords: list[str]

    retrieved_context: str

    analysis: str
    historical_evidence: str
    severity: str
    priority: str
    likely_cause: str
    suggested_resolution: str
    missing_information: list[str]

    confidence_score: float
    confidence_level: str
    confidence_reason: str
    retrieval_diagnostics: dict
    llm_status: str
    llm_error: str
    analysis_mode: str


# ============================================================
# CONFIDENCE CONFIGURATION
# ============================================================

SEMANTIC_WEIGHT = 0.40
KEYWORD_WEIGHT = 0.20
MODULE_CATEGORY_WEIGHT = 0.20
COMPLETENESS_WEIGHT = 0.20

TOP_RETRIEVED_TICKETS = 5

RELEVANCE_WEIGHTS = [
    0.50,
    0.25,
    0.15,
    0.07,
    0.03,
]


# ============================================================
# INTERNAL HISTORICAL EVIDENCE EXTRACTION
# ============================================================


def extract_retrieved_tickets(context: str) -> list[dict]:
    """
    Extract historical ticket metadata from the RAG context.

    This function is intentionally tolerant of missing fields
    because retrieval results may not always contain every
    metadata field.
    """

    if not context or not context.strip():
        return []

    tickets = []

    # The current context builder separates ticket blocks using
    # a long line of "=" characters.
    blocks = re.split(r"={20,}", context)

    for block in blocks:

        if not block.strip():
            continue

        ticket_match = re.search(
            r"Ticket Code:\s*(.+)",
            block,
            re.IGNORECASE,
        )

        module_match = re.search(
            r"Module:\s*(.+)",
            block,
            re.IGNORECASE,
        )

        category_match = re.search(
            r"Category:\s*(.+)",
            block,
            re.IGNORECASE,
        )

        distance_match = re.search(
            r"Semantic Distance:\s*([\d.]+|Not available)",
            block,
            re.IGNORECASE,
        )

        # A block without a ticket code is not treated as a
        # historical ticket.
        if not ticket_match:
            continue

        ticket_code = ticket_match.group(1).strip()

        module = module_match.group(1).strip() if module_match else ""

        category = category_match.group(1).strip() if category_match else ""

        distance = None

        if distance_match:

            value = distance_match.group(1).strip()

            if value.lower() != "not available":

                try:
                    distance = float(value)

                except (ValueError, TypeError):
                    distance = None

        tickets.append(
            {
                "ticket_code": ticket_code,
                "module": module,
                "category": category,
                "semantic_distance": distance,
            }
        )

    return tickets


# ============================================================
# SEMANTIC RELEVANCE
# ============================================================


def calculate_semantic_relevance(tickets: list[dict]) -> float:
    """
    Convert Chroma semantic distances into an internal
    relevance estimate.

    Lower distance means stronger relevance.

    This value is used internally only and is never exposed
    directly to the user.
    """

    distances = [
        ticket["semantic_distance"]
        for ticket in tickets
        if ticket.get("semantic_distance") is not None
    ]

    if not distances:
        return 0.0

    distances = distances[:TOP_RETRIEVED_TICKETS]

    relevance_scores = [1 / (1 + distance) for distance in distances]

    weighted_relevance = 0.0
    total_weight = 0.0

    for relevance, weight in zip(
        relevance_scores,
        RELEVANCE_WEIGHTS,
    ):

        weighted_relevance += relevance * weight
        total_weight += weight

    if total_weight == 0:
        return 0.0

    return weighted_relevance / total_weight


# ============================================================
# CONFIDENCE SCORE CALCULATION
# ============================================================


def calculate_confidence_score(state: ConfidenceState):

    retrieved_context = state.get(
        "retrieved_context",
        "",
    )

    keywords = [
        str(keyword).lower().strip()
        for keyword in state.get("keywords", [])
        if str(keyword).strip()
    ]

    module = str(state.get("module", "")).lower().strip()

    category = str(state.get("category", "")).lower().strip()

    analysis = state.get("analysis", "")
    historical_evidence = state.get(
        "historical_evidence",
        "",
    )
    likely_cause = state.get(
        "likely_cause",
        "",
    )
    suggested_resolution = state.get(
        "suggested_resolution",
        "",
    )
    severity = state.get("severity", "")
    priority = state.get("priority", "")

    # ========================================================
    # 1. HISTORICAL / SEMANTIC EVIDENCE
    # ========================================================

    tickets = extract_retrieved_tickets(retrieved_context)

    semantic_relevance = calculate_semantic_relevance(tickets)

    semantic_score = semantic_relevance * SEMANTIC_WEIGHT

    # ========================================================
    # 2. KEYWORD EVIDENCE
    # ========================================================

    matched_keywords = []

    context_lower = retrieved_context.lower() if retrieved_context else ""

    for keyword in keywords:

        if keyword in context_lower:
            matched_keywords.append(keyword)

    keyword_score = 0.0

    if keywords:

        keyword_match_ratio = len(matched_keywords) / len(keywords)

        keyword_score = keyword_match_ratio * KEYWORD_WEIGHT

    # ========================================================
    # 3. MODULE / CATEGORY EVIDENCE
    # ========================================================

    module_match = False
    category_match = False

    for ticket in tickets:

        historical_module = ticket.get("module", "").lower().strip()

        historical_category = ticket.get("category", "").lower().strip()

        if module and historical_module and historical_module == module:
            module_match = True

        if category and historical_category and historical_category == category:
            category_match = True

    module_category_score = 0.0

    if module_match:
        module_category_score += 0.10

    if category_match:
        module_category_score += 0.10

    # ========================================================
    # 4. ANALYSIS COMPLETENESS
    # ========================================================

    fields = [
        analysis,
        historical_evidence,
        likely_cause,
        suggested_resolution,
        severity,
        priority,
    ]

    completed_fields = 0

    for field in fields:

        if field and str(field).strip():
            completed_fields += 1

    completeness_ratio = completed_fields / len(fields) if fields else 0.0

    completeness_score = completeness_ratio * COMPLETENESS_WEIGHT

    # ========================================================
    # FINAL INTERNAL SCORE
    # ========================================================

    confidence_score = (
        semantic_score + keyword_score + module_category_score + completeness_score
    )

    confidence_score = max(
        0.0,
        min(confidence_score, 1.0),
    )

    confidence_score = round(
        confidence_score,
        2,
    )

    # ========================================================
    # CONFIDENCE LEVEL
    # ========================================================

    if confidence_score >= 0.80:

        confidence_level = "High"

    elif confidence_score >= 0.60:

        confidence_level = "Medium"

    else:

        confidence_level = "Low"

    # ========================================================
    # USER-FACING PERCENTAGE
    # ========================================================

    confidence_percentage = round(confidence_score * 100)

    return {
        "confidence_score": confidence_percentage,
        "confidence_level": confidence_level,
    }


# ============================================================
# USER-FACING CONFIDENCE EXPLANATION
# ============================================================


def generate_confidence_reason(state: ConfidenceState):

    ticket = state.get("ticket", "")
    summary = state.get("summary", "")
    module = state.get("module", "")
    category = state.get("category", "")

    retrieved_context = state.get(
        "retrieved_context",
        "",
    )

    analysis = state.get("analysis", "")
    historical_evidence = state.get(
        "historical_evidence",
        "",
    )

    severity = state.get("severity", "")
    priority = state.get("priority", "")

    likely_cause = state.get(
        "likely_cause",
        "",
    )

    suggested_resolution = state.get(
        "suggested_resolution",
        "",
    )

    missing_information = state.get(
        "missing_information",
        [],
    )

    confidence_score = state.get(
        "confidence_score",
        0,
    )

    confidence_level = state.get(
        "confidence_level",
        "Low",
    )

    diagnostics = state.get("retrieval_diagnostics", {}) or {}
    llm_status = state.get("llm_status", "available")
    ticket_count = int(diagnostics.get("ticket_count", 0) or 0)
    document_count = int(diagnostics.get("financial_document_count", 0) or 0)
    if llm_status != "available":
        evidence_bits = []
        if ticket_count:
            evidence_bits.append(f"{ticket_count} historical ticket(s) were retrieved")
        if document_count:
            evidence_bits.append(f"{document_count} financial SOP/policy document(s) were retrieved")
        evidence_summary = " and ".join(evidence_bits) if evidence_bits else "no supporting retrieval evidence was found"
        reason = (f"Confidence is {confidence_level.lower()} ({confidence_score}%). One or more Hugging Face agent calls failed, so part of the workflow used a fallback. "
                  f"Retrieval status: {evidence_summary}. The recommendation is an investigation aid, not a confirmed root cause. "
                  "Check the displayed provider error, confirm evidence against the ERP records, and retest before applying a fix.")
        error = state.get("llm_error", "")
        return {"confidence_reason": reason, "llm_status": llm_status, "llm_error": error}

    # ========================================================
    # CONFIDENCE EXPLANATION PROMPT
    # ========================================================

    prompt = f"""
You are the Confidence Explanation component of BugPilot.

Your job is to explain the confidence level to the USER.

The user does NOT need to know how the confidence score
was calculated.

============================================================
VERY IMPORTANT
============================================================

NEVER mention:

- semantic score
- semantic distance
- keyword score
- keyword matching
- retrieval score
- embeddings
- vector database
- weights
- formulas
- internal scoring
- mathematical calculations
- ranking
- similarity percentages
- implementation details
- internal AI reasoning

The user should only understand:

1. Why BugPilot has this confidence level.
2. What evidence supports the analysis.
3. What makes the recommendation useful.
4. What limitations or uncertainty remain.

============================================================
CURRENT TICKET
============================================================

{ticket}

Summary:
{summary}

Module:
{module}

Category:
{category}

============================================================
HISTORICAL EVIDENCE
============================================================

{retrieved_context[:4000]}

============================================================
BUGPILOT ANALYSIS
============================================================

{analysis}

Historical Evidence Explanation:
{historical_evidence}

Likely Cause:
{likely_cause}

Suggested Resolution:
{suggested_resolution}

Severity:
{severity}

Priority:
{priority}

Missing Information:
{missing_information}

============================================================
CONFIDENCE RESULT
============================================================

Confidence:
{confidence_score}%

Level:
{confidence_level}

============================================================
WRITE THE EXPLANATION
============================================================

Write a comprehensive but easy-to-understand explanation.

The explanation should:

- Explain why BugPilot considers the result reliable.
- Refer to relevant historical evidence when available.
- Explain whether the evidence strongly or partially supports
  the analysis.
- Clearly explain any uncertainty.
- Make the user comfortable using the recommendation while
  avoiding false guarantees.
- Explain that additional investigation may be required when
  the exact root cause is not confirmed.
- Distinguish available evidence from assumptions.
- Avoid claiming that the issue has been definitively solved
  unless the available information supports that conclusion.

The explanation should sound like a senior engineer giving
a professional assessment.

Do NOT expose internal AI reasoning or calculations.

Do NOT simply say:

"The confidence is high because historical tickets were found."

Explain WHY the available evidence is useful.

Keep it concise and meaningful: one short paragraph of
3-5 sentences (roughly 80-120 words).

Return ONLY valid JSON.

Use exactly:

{{
    "confidence_reason": "Detailed confidence explanation"
}}

Do not use Markdown.
Do not add anything outside the JSON.
"""

    # ========================================================
    # CALL LLM
    # ========================================================

    try:
        response = generate_response(prompt, num_predict=220)
    except Exception as error:
        diagnostics = state.get("retrieval_diagnostics", {}) or {}
        ticket_count = int(diagnostics.get("ticket_count", 0) or 0)
        document_count = int(diagnostics.get("financial_document_count", 0) or 0)
        reason = (f"Confidence is {confidence_level.lower()} ({confidence_score}%). The confidence explanation LLM call failed. "
                  f"Evidence retrieved: {ticket_count} historical ticket(s) and {document_count} financial document(s). "
                  "Treat the result as preliminary and verify the evidence before applying a fix.")
        return {"confidence_reason": reason, "llm_status": "degraded", "llm_error": f"Confidence explanation LLM call failed: {type(error).__name__}: {str(error)[:350]}", "analysis_mode": "partial_llm_failure"}

    if not response:
        return {
            "confidence_reason": (
                f"BugPilot assigned a "
                f"{confidence_level.lower()} confidence level "
                f"based on the available ticket information and "
                f"supporting evidence. The assessment should still "
                f"be validated against the relevant system and "
                f"business data before applying a correction."
            )
        }

    response = response.strip()

    # ========================================================
    # CLEAN JSON RESPONSE
    # ========================================================

    if response.startswith("```json"):

        response = response[7:].strip()

    elif response.startswith("```"):

        response = response[3:].strip()

    if response.endswith("```"):

        response = response[:-3].strip()

    # ========================================================
    # PARSE RESPONSE
    # ========================================================

    try:

        data = json.loads(response)

        reason = data.get(
            "confidence_reason",
            "",
        )

        if not isinstance(reason, str):
            reason = str(reason)

        reason = reason.strip()

        if not reason:
            raise ValueError("Empty confidence reason.")

    except (
        json.JSONDecodeError,
        ValueError,
        TypeError,
    ):

        reason = (
            f"BugPilot assigned a "
            f"{confidence_level.lower()} confidence level "
            f"to this assessment. The recommendation is "
            f"supported by the available ticket information "
            f"and historical evidence. However, the exact "
            f"root cause should be confirmed against the "
            f"available system and business data before "
            f"applying the recommended correction."
        )

    return {"confidence_reason": reason}


# ============================================================
# LANGGRAPH
# ============================================================

builder = StateGraph(ConfidenceState)

builder.add_node(
    "calculate_confidence_score",
    calculate_confidence_score,
)

builder.add_node(
    "generate_confidence_reason",
    generate_confidence_reason,
)

builder.add_edge(
    START,
    "calculate_confidence_score",
)

builder.add_edge(
    "calculate_confidence_score",
    "generate_confidence_reason",
)

builder.add_edge(
    "generate_confidence_reason",
    END,
)

confidence_graph = builder.compile()
