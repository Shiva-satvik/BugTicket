from typing import TypedDict

from langgraph.graph import StateGraph, START, END

from app.agents.ticket_agent import understand_ticket, retrieve_context

from app.agents.analysis_agent import analyze_ticket

from app.agents.confidence_agent import (
    calculate_confidence_score,
    generate_confidence_reason,
)


class BugPilotState(TypedDict):

    # ========================================================
    # TICKET
    # ========================================================

    ticket: str

    # ========================================================
    # TICKET UNDERSTANDING
    # ========================================================

    understanding: str

    summary: str

    category: str

    module: str

    problem: str

    keywords: list[str]

    # ========================================================
    # RAG
    # ========================================================

    retrieved_context: str
    retrieval_diagnostics: dict
    llm_status: str
    llm_error: str
    ticket_understanding_status: str
    ticket_understanding_error: str
    analysis_mode: str

    # ========================================================
    # ANALYSIS
    # ========================================================

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


builder = StateGraph(BugPilotState)


builder.add_node("understand_ticket", understand_ticket)

builder.add_node("retrieve_context", retrieve_context)

builder.add_node("analyze_ticket", analyze_ticket)

builder.add_node("calculate_confidence_score", calculate_confidence_score)

builder.add_node("generate_confidence_reason", generate_confidence_reason)


builder.add_edge(START, "understand_ticket")

builder.add_edge("understand_ticket", "retrieve_context")

builder.add_edge("retrieve_context", "analyze_ticket")

builder.add_edge("analyze_ticket", "calculate_confidence_score")

builder.add_edge("calculate_confidence_score", "generate_confidence_reason")

builder.add_edge("generate_confidence_reason", END)


bugpilot_graph = builder.compile()


if __name__ == "__main__":

    initial_state = {
        "ticket": "Payroll overtime salary is incorrect.",
        "understanding": "",
        "summary": "",
        "category": "",
        "module": "",
        "problem": "",
        "keywords": [],
        "retrieved_context": "",
        "analysis": "",
        "historical_evidence": "",
        "severity": "",
        "priority": "",
        "likely_cause": "",
        "suggested_resolution": "",
        "missing_information": [],
        "confidence_score": 0.0,
        "confidence_level": "",
        "confidence_reason": "",
    }

    result = bugpilot_graph.invoke(initial_state)

    print("\n")

    print("=" * 70)

    print("                         BUGPILOT")

    print("              AI SOFTWARE BUG ASSISTANT")

    print("=" * 70)

    print("\n===== ORIGINAL TICKET =====")

    print(result["ticket"])

    print("\n===== TICKET UNDERSTANDING =====")

    print("\nSummary:")

    print(result["summary"])

    print("\nCategory:")

    print(result["category"])

    print("\nModule:")

    print(result["module"])

    print("\nProblem:")

    print(result["problem"])

    print("\nKeywords:")

    print(result["keywords"])

    print("\n===== HISTORICAL EVIDENCE =====")

    print(result["historical_evidence"])

    print("\n===== DETAILED ANALYSIS =====")

    print(result["analysis"])

    print("\n===== CLASSIFICATION =====")

    print("\nSeverity:")

    print(result["severity"])

    print("\nPriority:")

    print(result["priority"])

    print("\n===== LIKELY CAUSE =====")

    print(result["likely_cause"])

    print("\n===== SUGGESTED RESOLUTION =====")

    print(result["suggested_resolution"])

    print("\n===== INFORMATION REQUIRED =====")

    for item in result["missing_information"]:

        print(f"- {item}")

    print("\n===== CONFIDENCE CHECK =====")

    print("\nConfidence:")

    print(f"{result['confidence_score']}%")

    print("\nLevel:")

    print(result["confidence_level"])

    print("\nReason:")

    print(result["confidence_reason"])

    print("\n")

    print("=" * 70)

    print("                 BUGPILOT WORKFLOW COMPLETE")

    print("=" * 70)
