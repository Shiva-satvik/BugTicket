import json
from typing import TypedDict

from langgraph.graph import StateGraph, START, END

from app.services.llm_service import generate_response

# ============================================================
# ANALYSIS STATE
# ============================================================


class AnalysisState(TypedDict):

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
    llm_status: str
    llm_error: str
    ticket_understanding_status: str
    ticket_understanding_error: str
    analysis_mode: str


# ============================================================
# CONSTANTS
# ============================================================

VALID_SEVERITIES = {
    "Low",
    "Medium",
    "High",
    "Critical",
}

VALID_PRIORITIES = {
    "P1",
    "P2",
    "P3",
    "P4",
}


# ============================================================
# JSON CLEANING
# ============================================================


def clean_json_response(response: str) -> str:
    """Remove Markdown fences and isolate the JSON object."""
    response = (response or "").strip()
    if response.startswith("```"):
        lines = response.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        response = "\n".join(lines).strip()

    # If the model adds text around the JSON, isolate the outer object.
    first_brace = response.find("{")
    last_brace = response.rfind("}")
    if first_brace >= 0 and last_brace > first_brace:
        response = response[first_brace:last_brace + 1]
    return response


# ============================================================
# RESPONSE VALIDATION
# ============================================================


def validate_analysis_response(data: dict) -> dict:
    """
    Validate and normalize the structured response returned
    by the LLM.
    """

    if not isinstance(data, dict):
        raise ValueError("Analysis Agent response must be a JSON object.")

    required_fields = [
        "analysis",
        "historical_evidence",
        "severity",
        "priority",
        "likely_cause",
        "suggested_resolution",
        "missing_information",
    ]

    missing_fields = [field for field in required_fields if field not in data]

    if missing_fields:
        raise ValueError(
            "Analysis Agent response is missing required fields: "
            + ", ".join(missing_fields)
        )

    # --------------------------------------------------------
    # Validate severity
    # --------------------------------------------------------

    severity = str(data["severity"]).strip()

    if severity not in VALID_SEVERITIES:
        raise ValueError(
            f"Invalid severity returned by Analysis Agent: "
            f"{severity}. Expected one of: "
            f"{', '.join(sorted(VALID_SEVERITIES))}"
        )

    # --------------------------------------------------------
    # Validate priority
    # --------------------------------------------------------

    priority = str(data["priority"]).strip().upper()

    if priority not in VALID_PRIORITIES:
        raise ValueError(
            f"Invalid priority returned by Analysis Agent: "
            f"{priority}. Expected one of: "
            f"{', '.join(sorted(VALID_PRIORITIES))}"
        )

    # --------------------------------------------------------
    # Validate missing information
    # --------------------------------------------------------

    missing_information = data["missing_information"]

    if missing_information is None:
        missing_information = []

    elif isinstance(missing_information, str):
        missing_information = [missing_information]

    elif not isinstance(missing_information, list):
        raise ValueError("missing_information must be a list of strings.")

    # Make sure every item is a string.
    missing_information = [
        str(item).strip() for item in missing_information if str(item).strip()
    ]

    # --------------------------------------------------------
    # Normalize text fields
    # --------------------------------------------------------

    return {
        "analysis": str(data["analysis"]).strip(),
        "historical_evidence": str(data["historical_evidence"]).strip(),
        "severity": severity,
        "priority": priority,
        "likely_cause": str(data["likely_cause"]).strip(),
        "suggested_resolution": str(data["suggested_resolution"]).strip(),
        "missing_information": missing_information,
    }


# ============================================================
# ANALYZE TICKET
# ============================================================


def analyze_ticket(state: AnalysisState):

    # --------------------------------------------------------
    # READ CURRENT TICKET INFORMATION
    # --------------------------------------------------------

    ticket = state.get("ticket", "").strip()

    summary = state.get("summary", "").strip()
    category = state.get("category", "").strip()
    module = state.get("module", "").strip()
    problem = state.get("problem", "").strip()

    keywords = state.get("keywords", [])

    retrieved_context = state.get("retrieved_context", "")

    # --------------------------------------------------------
    # SAFETY CHECK
    # --------------------------------------------------------

    if not ticket:
        raise ValueError("Analysis Agent received an empty ticket.")

    # --------------------------------------------------------
    # ANALYSIS PROMPT
    # --------------------------------------------------------

    prompt = f"""
You are BugPilot, a senior enterprise software bug analyst.
Analyze the ticket using only the ticket details and retrieved evidence. Do not invent facts. Historical records are leads, not proof of the current root cause. Clearly state uncertainty.

TICKET: {ticket}
SUMMARY: {summary}
CATEGORY: {category}
MODULE: {module}
PROBLEM: {problem}
KEYWORDS: {keywords}
RETRIEVED HISTORICAL TICKETS / DOCUMENTS:
{retrieved_context[:7000]}

Return ONLY one valid JSON object with exactly these fields:
{{
  "analysis": "Explain the symptom, affected area, impact, evidence and uncertainty.",
  "historical_evidence": "Mention relevant record codes and explain relevance. Do not invent outcomes.",
  "severity": "Low, Medium, High, or Critical",
  "priority": "P1, P2, P3, or P4",
  "likely_cause": "Most reasonable cause or investigation direction; say if unconfirmed.",
  "suggested_resolution": "Numbered practical checks, conditional fix, and validation steps.",
  "missing_information": ["Specific information needed to confirm the cause"]
}}

Choose severity and priority based on demonstrated impact, not merely because the issue concerns payroll/finance. Use valid JSON with double quotes, no trailing commas, and no Markdown fences. Keep the response concise enough to finish completely.
"""

    # --------------------------------------------------------
    # CALL LLM
    # --------------------------------------------------------

    try:
        response = generate_response(prompt, response_format="json")
        if not isinstance(response, str) or not response.strip():
            raise RuntimeError("Ollama returned an empty analysis response.")

        cleaned_response = clean_json_response(response)
        try:
            data = json.loads(cleaned_response)
        except json.JSONDecodeError as error:
            # Include a short excerpt to help diagnose truncation without flooding logs/UI.
            excerpt = cleaned_response[max(0, error.pos - 80):error.pos + 80].replace("\n", " ")
            raise ValueError(
                "Ollama returned invalid or incomplete JSON "
                f"(line {error.lineno}, column {error.colno}). "
                f"Response excerpt: {excerpt!r}"
            ) from error

        if not isinstance(data, dict):
            raise ValueError("Ollama analysis response must be a JSON object.")

        validated_data = validate_analysis_response(data)
        understanding_degraded = state.get("ticket_understanding_status") == "degraded"
        return {
            **validated_data,
            "llm_status": "partial" if understanding_degraded else "available",
            "llm_error": state.get("ticket_understanding_error", "") if understanding_degraded else "",
            "analysis_mode": "partial_llm_failure" if understanding_degraded else "llm_rag",
        }
    except Exception as error:
        # This fallback is grounded in the actual retrieved context and is explicitly labeled.
        blocks = [line.strip() for line in retrieved_context.splitlines() if line.strip()]
        ticket_sources = [line.split(":", 1)[1].strip() for line in blocks if line.lower().startswith("ticket code:")]
        doc_sources = [line.split(":", 1)[1].strip() for line in blocks if line.lower().startswith("document code:")]
        evidence_names = ticket_sources + doc_sources
        has_evidence = bool(evidence_names)
        lower = ticket.lower()
        severity = "High" if any(term in lower for term in ["blocked", "denied", "failed", "cannot", "unable", "error", "incorrect"]) else "Medium"
        if has_evidence:
            evidence_text = "Retrieved evidence available: " + ", ".join(evidence_names[:8]) + "."
        else:
            evidence_text = "No historical ticket or financial-document evidence was returned by retrieval for this query."
        analysis_text = (
            "The Ollama analysis call failed, so this is a retrieval-grounded fallback, not an LLM-generated analysis. "
            + evidence_text + " Review the provider error and validate the issue manually."
        )
        cause = ("The retrieved historical tickets and financial documents should be compared with the reported symptoms; "
                 "they provide investigation leads, not proof of the root cause." if has_evidence else
                 "The root cause cannot be confirmed because no supporting historical or financial-document evidence was retrieved and the LLM call failed.")
        resolution = "1. Capture the exact ERP error, timestamp, affected record and user role. 2. Compare the issue with the retrieved historical tickets and applicable financial SOP/policy passages listed above. 3. Verify the relevant database records, approval state and permissions. 4. Apply only a confirmed correction and retest the same workflow."
        return {
            "analysis": analysis_text,
            "historical_evidence": evidence_text,
            "severity": severity,
            "priority": "P2" if severity == "High" else "P3",
            "likely_cause": cause,
            "suggested_resolution": resolution,
            "missing_information": ["Exact error message and code", "Timestamp and affected record", "Steps to reproduce", "User role and approval state"],
            "llm_status": "degraded",
            "llm_error": f"Analysis LLM call failed: {type(error).__name__}: {str(error)[:350]}",
            "analysis_mode": "retrieval_grounded_fallback" if has_evidence else "no_evidence_fallback",
        }



# ============================================================
# LANGGRAPH
# ============================================================

builder = StateGraph(AnalysisState)

builder.add_node("analyze_ticket", analyze_ticket)

builder.add_edge(START, "analyze_ticket")

builder.add_edge("analyze_ticket", END)

graph = builder.compile()
