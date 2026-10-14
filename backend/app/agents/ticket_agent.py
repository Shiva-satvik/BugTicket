
import json
import logging
import re
import time
from typing import TypedDict

from langgraph.graph import StateGraph, START, END

from app.services.llm_service import generate_response
from app.rag.context_builder import build_rag_context_with_diagnostics

logger = logging.getLogger(__name__)


class TicketState(TypedDict):
    ticket: str
    understanding: str
    summary: str
    category: str
    module: str
    problem: str
    keywords: list[str]
    retrieved_context: str
    retrieval_diagnostics: dict
    llm_status: str
    llm_error: str
    ticket_understanding_status: str
    ticket_understanding_error: str
    analysis_mode: str


def clean_json_response(response: str) -> str:
    """Remove surrounding Markdown fences from a model response."""
    response = response.strip()

    if response.startswith("```"):
        response = re.sub(r"^```(?:json)?\s*", "", response, count=1)

    if response.endswith("```"):
        response = response[:-3].strip()

    return response.strip()


def validate_ticket_response(data: dict) -> dict:
    """Validate and normalize the ticket-understanding JSON."""

    if not isinstance(data, dict):
        raise ValueError("Ticket agent response must be a JSON object.")

    required_fields = [
        "summary",
        "category",
        "module",
        "problem",
        "keywords",
    ]

    missing_fields = [
        field for field in required_fields if field not in data
    ]

    if missing_fields:
        raise ValueError(
            "Ticket Understanding Agent response is missing fields: "
            + ", ".join(missing_fields)
        )

    keywords = data["keywords"]

    if keywords is None:
        keywords = []
    elif isinstance(keywords, str):
        keywords = [keywords]
    elif not isinstance(keywords, list):
        raise ValueError("keywords must be a list of strings.")

    return {
        "summary": str(data["summary"]).strip() or "Unknown",
        "category": str(data["category"]).strip() or "Unknown",
        "module": str(data["module"]).strip() or "Unknown",
        "problem": str(data["problem"]).strip() or "Unknown",
        "keywords": [
            str(keyword).strip()
            for keyword in keywords
            if str(keyword).strip()
        ],
    }


def understand_ticket(state: TicketState):
    """Understand and structure an incoming BugPilot ticket."""

    ticket = str(state.get("ticket") or "").strip()

    if not ticket:
        raise ValueError(
            "Ticket Understanding Agent received an empty ticket."
        )

    prompt = f"""
You are the Ticket Understanding Agent for BugPilot.

Understand the following software or ERP bug ticket.

TICKET:
{ticket}

Identify:
1. A short summary.
2. The issue category.
3. The affected business or technical module.
4. The actual reported problem.
5. Important relevant keywords.

Rules:
- Do not solve the bug.
- Do not invent facts.
- Use "Unknown" when a field cannot be determined.
- Do not introduce unrelated systems or technologies.
- Return only a JSON object, without Markdown.

Required JSON structure:
{{
  "summary": "Short issue summary",
  "category": "Issue category",
  "module": "Affected module",
  "problem": "Reported problem",
  "keywords": ["keyword1", "keyword2"]
}}
"""

    started = time.monotonic()

    try:
        logger.info("Ticket understanding started")

        response = generate_response(
            prompt,
            response_format="json",
            num_predict=350,
        )

        if not response:
            raise RuntimeError("Ollama returned an empty response.")

        cleaned_response = clean_json_response(response)
        data = json.loads(cleaned_response)
        validated = validate_ticket_response(data)

        logger.info(
            "Ticket understanding completed in %.2f seconds",
            time.monotonic() - started,
        )

        return {
            "understanding": json.dumps(validated, ensure_ascii=False),
            **validated,
            "llm_status": "available",
            "llm_error": "",
            "ticket_understanding_status": "available",
            "ticket_understanding_error": "",
        }

    except Exception as error:
        logger.exception("Ticket understanding failed; using fallback")

        lower = ticket.lower()

        rules = [
            (
                ("payroll", "salary", "payslip", "overtime"),
                "Payroll",
                "Payroll",
            ),
            (
                ("invoice", "vendor", "payable", "goods receipt"),
                "Accounts Payable",
                "Finance",
            ),
            (
                ("expense", "reimbursement", "claim"),
                "Expense Reimbursement",
                "Finance",
            ),
            (
                ("payment", "bank", "credited", "transfer"),
                "Vendor Payments",
                "Finance",
            ),
            (
                ("access", "permission", "role", "denied", "login"),
                "Access Management",
                "Security",
            ),
            (
                ("report", "export", "download"),
                "Reporting",
                "ERP",
            ),
        ]

        module = "Unknown"
        category = "ERP"

        for terms, candidate_module, candidate_category in rules:
            if any(term in lower for term in terms):
                module = candidate_module
                category = candidate_category
                break

        words = re.findall(r"[a-zA-Z0-9]+", ticket.lower())
        keywords = list(dict.fromkeys(
            word for word in words if len(word) > 2
        ))[:12]

        fallback = {
            "summary": ticket[:160],
            "category": category,
            "module": module,
            "problem": ticket,
            "keywords": keywords,
        }

        error_message = (
            f"Ticket understanding failed: {type(error).__name__}: "
            f"{str(error)[:350]}"
        )

        return {
            "understanding": json.dumps(fallback, ensure_ascii=False),
            **fallback,
            "llm_status": "degraded",
            "llm_error": error_message,
            "ticket_understanding_status": "degraded",
            "ticket_understanding_error": error_message,
        }


def retrieve_context(state: TicketState):
    """Retrieve historical tickets and financial documents."""

    query = str(state.get("ticket") or "").strip()

    if not query:
        raise ValueError(
            "Cannot retrieve RAG context because the ticket is empty."
        )

    started = time.monotonic()
    logger.info("RAG retrieval started")

    context, diagnostics = build_rag_context_with_diagnostics(
        query=query,
        k=5,
    )

    logger.info(
        "RAG retrieval completed in %.2f seconds",
        time.monotonic() - started,
    )

    return {
        "retrieved_context": context,
        "retrieval_diagnostics": diagnostics,
    }


builder = StateGraph(TicketState)

builder.add_node("understand_ticket", understand_ticket)
builder.add_node("retrieve_context", retrieve_context)

builder.add_edge(START, "understand_ticket")
builder.add_edge("understand_ticket", "retrieve_context")
builder.add_edge("retrieve_context", END)

graph = builder.compile()
