import hashlib
import logging
import os
import re
import threading
import time
from collections import OrderedDict
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

logger = logging.getLogger(__name__)


# ============================================================
# PIPELINE DISPATCHER (fast by default) + RESULT CACHE
# ============================================================
#
# BUGPILOT_PIPELINE=fast     -> single merged LLM call (default; ~3x faster)
# BUGPILOT_PIPELINE=accurate -> original 5-node LangGraph workflow
#
# Identical tickets submitted within BUGPILOT_RESULT_CACHE_TTL seconds are
# answered from an in-process cache instead of re-running the whole model.
#
# FIX: degraded/fallback results are NEVER cached. The old code cached
# every result for BUGPILOT_RESULT_CACHE_TTL (default 3600s), including
# fallbacks produced while Ollama was down. That froze the "standard
# template response" into the cache for a full hour, so even after the
# provider was fixed, identical tickets kept returning the same fallback.

PIPELINE_MODE = os.getenv("BUGPILOT_PIPELINE", "fast").strip().lower()
if PIPELINE_MODE not in {"fast", "accurate"}:
    PIPELINE_MODE = "fast"

RESULT_CACHE_TTL = int(os.getenv("BUGPILOT_RESULT_CACHE_TTL", "3600"))
RESULT_CACHE_MAX = 256

_result_cache: OrderedDict[str, tuple[float, dict]] = OrderedDict()
_result_cache_lock = threading.Lock()


def _initial_state(ticket_text: str) -> dict:
    return {
        "ticket": ticket_text,
        "understanding": "",
        "summary": "",
        "category": "",
        "module": "",
        "problem": "",
        "keywords": [],
        "retrieved_context": "",
        "retrieval_diagnostics": {},
        "llm_status": "available",
        "llm_error": "",
        "ticket_understanding_status": "available",
        "ticket_understanding_error": "",
        "analysis_mode": "llm_rag",
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


def _normalize_ticket_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def _result_cache_get(key: str) -> dict | None:
    if RESULT_CACHE_TTL <= 0:
        return None
    now = time.monotonic()
    with _result_cache_lock:
        entry = _result_cache.get(key)
        if entry is None:
            return None
        stored_at, result = entry
        if now - stored_at > RESULT_CACHE_TTL:
            _result_cache.pop(key, None)
            return None
        _result_cache.move_to_end(key)
        return dict(result)


def _result_cache_put(key: str, result: dict) -> None:
    if RESULT_CACHE_TTL <= 0:
        return
    with _result_cache_lock:
        _result_cache[key] = (time.monotonic(), dict(result))
        _result_cache.move_to_end(key)
        while len(_result_cache) > RESULT_CACHE_MAX:
            _result_cache.popitem(last=False)


def run_analysis(ticket_text: str) -> dict:
    """
    Run the configured BugPilot pipeline for one ticket.

    This is the single entry point used by the API layer. The returned
    dictionary matches the original graph output contract in both modes.
    """
    ticket_text = str(ticket_text or "").strip()
    if not ticket_text:
        raise ValueError("Cannot run BugPilot analysis on an empty ticket.")

    from app.services.llm_service import OLLAMA_MODEL

    cache_key = hashlib.sha256(
        f"{PIPELINE_MODE}|{OLLAMA_MODEL}|{_normalize_ticket_text(ticket_text)}".encode("utf-8")
    ).hexdigest()

    cached = _result_cache_get(cache_key)
    if cached is not None:
        # The cached copy keeps its own ticket wording; restore the caller's.
        cached["ticket"] = ticket_text
        return cached

    if PIPELINE_MODE == "fast":
        from app.agents.fast_pipeline import run_fast_pipeline

        result = run_fast_pipeline(ticket_text)
    else:
        result = bugpilot_graph.invoke(_initial_state(ticket_text))

    # Only cache fully successful analyses. Degraded/fallback results
    # (llm_status != "available") must not poison the cache: the moment
    # the provider recovers, the next submission must get a real LLM run.
    if result.get("llm_status") == "available":
        _result_cache_put(cache_key, result)
    else:
        logger.warning(
            "Skipping result cache: analysis finished in degraded mode "
            "(llm_status=%s, mode=%s).",
            result.get("llm_status"),
            result.get("analysis_mode"),
        )

    return result


if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO)

    initial_state = {
        "ticket": "Payroll overtime salary is incorrect.",
        "understanding": "",
        "summary": "",
        "category": "",
        "module": "",
        "problem": "",
        "keywords": [],
        "retrieved_context": "",
        "retrieval_diagnostics": {},
        "llm_status": "available",
        "llm_error": "",
        "ticket_understanding_status": "available",
        "ticket_understanding_error": "",
        "analysis_mode": "llm_rag",
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
