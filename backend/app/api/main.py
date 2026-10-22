
import logging
import os
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.agents.bugpilot_graph import bugpilot_graph
from app.api.analytics_routes import router as analytics_router
from app.api.schemas import (
    TicketAnalysisResponse,
    TicketHistoryResponse,
    TicketRequest,
)
from app.api.ticket_routes import router as enterprise_ticket_router
from app.auth.dependencies import get_current_user
from app.auth.rbac import get_user_roles
from app.auth.routes import router as auth_router
from app.database.schema import create_master_tables
from app.database.ticket_service import (
    get_all_analyzed_tickets,
    get_analyzed_ticket,
    initialize_database,
    save_analyzed_ticket,
)

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")


def reconcile_ticket_embeddings() -> None:
    """Synchronize pending ticket embeddings with ChromaDB."""
    try:
        from app.embeddings.ticket_embedding_service import (
            sync_pending_ticket_embeddings,
        )

        result = sync_pending_ticket_embeddings(limit=100)

        logger.info(
            "Embedding reconciliation completed: %s",
            result,
        )

    except Exception:
        logger.exception("Embedding reconciliation failed.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize application resources and manage the scheduler."""

    # Initialize the separate AI-analysis history table.
    initialize_database()

    # Initialize the enterprise database tables and FTS index.
    # This intentionally fails if the existing tickets table needs
    # migration; do not delete or recreate the database automatically.
    create_master_tables()

    # Schedule reconciliation asynchronously. Running model downloads synchronously
    # during startup can make the API appear unavailable on a fresh/offline machine.
    if not scheduler.running:
        scheduler.add_job(
            reconcile_ticket_embeddings,
            trigger="interval",
            hours=24,
            id="bugpilot_embedding_reconciliation",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        scheduler.start()

        logger.info("Embedding reconciliation scheduler started.")

    try:
        yield
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)
            logger.info("Embedding reconciliation scheduler stopped.")


app = FastAPI(
    title="BugPilot API",
    description=(
        "AI-powered software bug analysis and "
        "enterprise ticket management backend."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# --------------------------------------------------
# CORS
# --------------------------------------------------

cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------
# Routers
# --------------------------------------------------

app.include_router(auth_router)
app.include_router(enterprise_ticket_router)
app.include_router(analytics_router)

# Serve saved profile photos. Files are written by the authenticated profile-photo endpoints.
PROFILE_UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
os.makedirs(PROFILE_UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=PROFILE_UPLOAD_DIR), name="uploads")


# --------------------------------------------------
# Authorization helper
# --------------------------------------------------

def _is_admin(employee_id: str) -> bool:
    """Return True if the employee has the ADMIN role."""
    return "ADMIN" in get_user_roles(employee_id)


# --------------------------------------------------
# Health check
# --------------------------------------------------

@app.get("/health", tags=["Health"])
def health_check():
    return {
        "status": "healthy",
        "service": "BugPilot API",
    }


# --------------------------------------------------
# Enterprise master data and administration
# --------------------------------------------------

@app.get("/api/enterprise/departments/", tags=["Enterprise Master Data"])
def list_departments(current_user: dict = Depends(get_current_user)):
    from app.database.connection import get_connection
    connection = get_connection()
    try:
        rows = connection.execute(
            "SELECT department_id, department_code, department_name FROM departments WHERE is_active = 1 ORDER BY department_name"
        ).fetchall()
        return {"departments": [dict(row) for row in rows]}
    finally:
        connection.close()


@app.get("/api/admin/users", tags=["Administration"])
def list_users_for_admin(current_user: dict = Depends(get_current_user)):
    if not _is_admin(current_user["employee_id"]):
        raise HTTPException(status_code=403, detail="Administrator role required.")
    from app.database.connection import get_connection
    connection = get_connection()
    try:
        rows = connection.execute(
            """SELECT u.employee_id, u.username, u.full_name, u.email,
                      d.department_name, u.department_id, u.designation,
                      u.is_active, u.last_login_at, u.created_at
               FROM users u LEFT JOIN departments d
                 ON d.department_id = u.department_id
               ORDER BY u.full_name"""
        ).fetchall()
        users = []
        for row in rows:
            item = dict(row)
            item["roles"] = get_user_roles(item["employee_id"])
            users.append(item)
        return {"count": len(users), "users": users}
    finally:
        connection.close()


# --------------------------------------------------
# AI ticket analysis
# --------------------------------------------------

@app.post(
    "/api/tickets/analyze",
    response_model=TicketAnalysisResponse,
    tags=["AI Ticket Analysis"],
)
def analyze_ticket(
    request: TicketRequest,
    current_user: dict = Depends(get_current_user),
):
    ticket_text = request.ticket.strip()

    if not ticket_text:
        raise HTTPException(
            status_code=400,
            detail="Ticket description cannot be empty.",
        )

    initial_state = {
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

    try:
        result = bugpilot_graph.invoke(initial_state)
        # Guard against incomplete graph output before persisting it.
        defaults = {
            "ticket": ticket_text, "summary": ticket_text[:180],
            "category": "ERP", "module": "Unspecified", "problem": ticket_text,
            "keywords": [], "analysis": "", "historical_evidence": "No historical evidence returned.",
            "severity": "MEDIUM", "priority": "MEDIUM",
            "likely_cause": "The available AI workflow did not identify a confirmed cause.",
            "suggested_resolution": "Collect reproduction steps, affected user, module, timestamp, and exact error text; then investigate application logs.",
            "missing_information": ["Exact error message", "Steps to reproduce", "Affected ERP module"],
            "confidence_score": 25.0, "confidence_level": "Low",
            "confidence_reason": "The analysis response was incomplete; treat these suggestions as preliminary.",
        }
        result = {**defaults, **(result or {})}
        result["ticket"] = ticket_text
        if not isinstance(result.get("keywords"), list):
            result["keywords"] = []
        if not isinstance(result.get("missing_information"), list):
            result["missing_information"] = []
        result["confidence_score"] = max(0.0, min(100.0, float(result.get("confidence_score") or 0)))
    except Exception:
        logger.exception(
            "BugPilot analysis failed for employee %s; returning low-confidence local fallback",
            current_user.get("employee_id", "unknown"),
        )
        lower = ticket_text.lower()
        module = next((name for name in ["payroll", "finance", "expense", "invoice", "access", "report"] if name in lower), "ERP")
        severity = "HIGH" if any(word in lower for word in ["blocked", "denied", "failed", "cannot", "unable", "error"]) else "MEDIUM"
        result = {
            "ticket": ticket_text,
            "summary": ticket_text[:180],
            "category": "Access" if "access" in lower or "denied" in lower else "ERP",
            "module": module.title(),
            "problem": ticket_text,
            "keywords": [word for word in ["payroll", "finance", "expense", "invoice", "access", "report", "error"] if word in lower],
            "analysis": "Local fallback analysis. The AI graph/provider did not respond, so this is rule-based triage rather than an LLM result.",
            "historical_evidence": "Historical ticket retrieval was not confirmed for this fallback result.",
            "severity": severity,
            "priority": "HIGH" if severity == "HIGH" else "MEDIUM",
            "likely_cause": "Possible permissions, validation, configuration, or service issue; the root cause is not confirmed.",
            "suggested_resolution": "Verify the affected user's role and department permissions, reproduce the issue, inspect application logs, and compare with a known-good user/workflow.",
            "missing_information": ["Exact error message", "Steps to reproduce", "Affected user/role", "Timestamp and ERP module"],
            "confidence_score": 25.0,
            "confidence_level": "Low",
            "confidence_reason": "Emergency rule-based fallback used because the analysis graph failed. Confirm findings manually.",
            "retrieval_diagnostics": {"ticket_count": 0, "financial_document_count": 0, "keyword_search": "not_run", "semantic_search": "not_run", "financial_document_search": "not_run"},
            "llm_status": "failed",
            "llm_error": "The analysis graph failed before completing. See backend logs for the traceback.",
            "analysis_mode": "emergency_fallback",
        }

    try:
        ticket_id = save_analyzed_ticket(
            result,
            created_by=current_user["employee_id"],
        )

    except Exception as error:
        logger.exception("Could not save the AI analysis result.")
        raise HTTPException(
            status_code=500,
            detail=(
                "BugPilot completed the analysis "
                "but could not save the result."
            ),
        ) from error

    return {
        "id": ticket_id,
        "ticket": result["ticket"],
        "summary": result["summary"],
        "category": result["category"],
        "module": result["module"],
        "problem": result["problem"],
        "keywords": result["keywords"],
        "analysis": result["analysis"],
        "historical_evidence": result["historical_evidence"],
        "severity": result["severity"],
        "priority": result["priority"],
        "likely_cause": result["likely_cause"],
        "suggested_resolution": result["suggested_resolution"],
        "missing_information": result["missing_information"],
        "confidence_score": result["confidence_score"],
        "confidence_level": result["confidence_level"],
        "confidence_reason": result["confidence_reason"],
        "retrieval_diagnostics": result.get("retrieval_diagnostics", {}),
        "llm_status": result.get("llm_status", "unknown"),
        "llm_error": result.get("llm_error", ""),
        "analysis_mode": result.get("analysis_mode", "unknown"),
    }


# --------------------------------------------------
# AI-analyzed ticket history
# --------------------------------------------------

@app.get(
    "/api/tickets",
    response_model=TicketHistoryResponse,
    tags=["AI Ticket Analysis"],
)
def get_ticket_history(
    current_user: dict = Depends(get_current_user),
):
    employee_id = current_user["employee_id"]

    try:
        tickets = get_all_analyzed_tickets(
            employee_id=employee_id,
            is_admin=_is_admin(employee_id),
        )

        return {
            "count": len(tickets),
            "tickets": tickets,
        }

    except Exception as error:
        logger.exception("Could not retrieve analyzed-ticket history.")
        raise HTTPException(
            status_code=500,
            detail="BugPilot could not retrieve ticket history.",
        ) from error


# --------------------------------------------------
# Retrieve one AI-analyzed ticket
# --------------------------------------------------

@app.get(
    "/api/tickets/{ticket_id}",
    tags=["AI Ticket Analysis"],
)
def get_ticket(
    ticket_id: int,
    current_user: dict = Depends(get_current_user),
):
    if ticket_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="Ticket ID must be greater than 0.",
        )

    employee_id = current_user["employee_id"]

    try:
        ticket = get_analyzed_ticket(
            ticket_id,
            employee_id=employee_id,
            is_admin=_is_admin(employee_id),
        )

    except Exception as error:
        logger.exception(
            "Could not retrieve analyzed ticket %s.",
            ticket_id,
        )
        raise HTTPException(
            status_code=500,
            detail="BugPilot could not retrieve the requested ticket.",
        ) from error

    if ticket is None:
        raise HTTPException(
            status_code=404,
            detail="Ticket not found.",
        )

    return ticket
