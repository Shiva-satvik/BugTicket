
from datetime import date
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.auth.rbac import require_roles
from app.database.enterprise_ticket_service import (
    assign_ticket,
    create_ticket,
    delete_ticket as delete_ticket_record,
    get_all_tickets,
    get_ticket_by_id,
    get_ticket_history,
    get_user_ticket_context,
    update_ticket,
)


router = APIRouter(
    prefix="/api/enterprise/tickets",
    tags=["Enterprise Tickets"],
)

logger = logging.getLogger(__name__)

VALID_STATUSES = {"PENDING", "OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED"}
VALID_LEVELS = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
VALID_PRIORITIES = VALID_LEVELS | {"URGENT"}


# ============================================================
# REQUEST MODELS
# ============================================================

class CreateTicketRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=10000)
    department_id: int = Field(gt=0)
    module: str | None = None
    category: str | None = None
    issue_type: str | None = None
    severity: str = "MEDIUM"
    priority: str = "MEDIUM"


class AssignTicketRequest(BaseModel):
    assigned_to: str = Field(min_length=1)


class UpdateTicketRequest(BaseModel):
    status: str | None = None
    priority: str | None = None
    severity: str | None = None
    resolution: str | None = None
    resolution_notes: str | None = None


# ============================================================
# BACKGROUND EMBEDDING TASKS
# ============================================================

def sync_ticket_embedding_background(ticket_id: int) -> None:
    """Create or refresh a ticket's embedding."""

    try:
        from app.embeddings.ticket_embedding_service import (
            sync_ticket_embedding,
        )

        sync_ticket_embedding(ticket_id)

    except Exception:
        logger.exception(
            "Embedding synchronization failed for ticket ID %s",
            ticket_id,
        )


def delete_ticket_embedding_background(ticket_id: int) -> None:
    """Remove a deleted ticket's vector from ChromaDB."""

    try:
        from app.vectorstore.chroma_store import delete_ticket

        delete_ticket(ticket_id)

    except Exception:
        logger.exception(
            "Embedding deletion failed for ticket ID %s",
            ticket_id,
        )


# ============================================================
# AUTHORIZATION HELPERS
# ============================================================

def _context(current_user: dict) -> dict:
    context = get_user_ticket_context(
        current_user["employee_id"]
    )

    if not context or not context["is_active"]:
        raise HTTPException(
            status_code=401,
            detail="User is missing or inactive.",
        )

    if not context["roles"]:
        raise HTTPException(
            status_code=403,
            detail="User has no assigned role.",
        )

    return context


def _can_view(ticket: dict, context: dict) -> bool:
    """Determine whether the current user can view a ticket."""

    roles = set(context["roles"])
    employee_id = context["employee_id"]

    if "ADMIN" in roles:
        return True

    if roles.intersection({"MANAGER", "VIEWER"}):
        return ticket["department_id"] == context["department_id"]

    # EMPLOYEE / DEVELOPER / SUPPORT: a ticket is visible when the employee
    # historically created it OR it was assigned to them.
    if roles.intersection({"EMPLOYEE", "DEVELOPER", "SUPPORT"}):
        return (
            ticket["created_by"] == employee_id
            or ticket["assigned_to"] == employee_id
        )

    return False


def _require_ticket_view(
    ticket_id: int,
    context: dict,
) -> dict:
    ticket = get_ticket_by_id(ticket_id)

    if ticket is None or not _can_view(ticket, context):
        raise HTTPException(
            status_code=404,
            detail="Ticket not found.",
        )

    return ticket


def _ticket_scope(context: dict) -> dict:
    roles = set(context["roles"])

    if "ADMIN" in roles:
        return {}

    if roles.intersection({"MANAGER", "VIEWER"}):
        return {
            "scope_department_id": context["department_id"]
        }

    # EMPLOYEE, DEVELOPER, SUPPORT (and any combination of them) share the
    # same participant scope: tickets they created OR that were assigned
    # to them. The database enforces it in a single query, so sorting and
    # pagination stay consistent.
    return {"participant": context["employee_id"]}


# ============================================================
# TICKET FILTERING AND SORTING
# ============================================================

def _fetch_tickets(
    context: dict,
    status: str | None,
    priority: str | None,
    severity: str | None,
    department_id: int | None,
    start_date: date | None,
    end_date: date | None,
    sort_by: str,
    sort_order: str,
):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="start_date cannot be later than end_date.",
        )

    if status is not None:
        status = status.upper()
        if status not in VALID_STATUSES:
            raise HTTPException(
                status_code=400,
                detail="Invalid status filter.",
            )

    if priority is not None:
        priority = priority.upper()
        if priority not in VALID_PRIORITIES:
            raise HTTPException(
                status_code=400,
                detail="Invalid priority filter.",
            )

    if severity is not None:
        severity = severity.upper()
        if severity not in VALID_LEVELS:
            raise HTTPException(
                status_code=400,
                detail="Invalid severity filter.",
            )

    roles = set(context["roles"])
    scope = _ticket_scope(context)

    # Enforce department restrictions for non-admin users.
    if (
        "ADMIN" not in roles
        and roles.intersection({"MANAGER", "VIEWER"})
    ):
        if (
            department_id is not None
            and department_id != context["department_id"]
        ):
            raise HTTPException(
                status_code=403,
                detail="You cannot access another department's tickets.",
            )

        department_id = context["department_id"]

    elif "ADMIN" not in roles and department_id is not None:
        if department_id != context["department_id"]:
            raise HTTPException(
                status_code=403,
                detail="You cannot access another department's tickets.",
            )

    try:
        tickets = get_all_tickets(
            status=status,
            priority=priority,
            severity=severity,
            department_id=department_id,
            start_date=start_date.isoformat() if start_date else None,
            end_date=end_date.isoformat() if end_date else None,
            sort_by=sort_by,
            sort_order=sort_order,
            **scope,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return tickets


# ============================================================
# CREATE TICKET
# ============================================================

@router.post("/")
def create_new_ticket(
    request: CreateTicketRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    context = _context(current_user)
    roles = set(context["roles"])

    allowed_roles = {
        "ADMIN",
        "MANAGER",
        "DEVELOPER",
        "SUPPORT",
        "EMPLOYEE",
    }

    if not roles.intersection(allowed_roles):
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to create tickets.",
        )

    if (
        "ADMIN" not in roles
        and request.department_id != context["department_id"]
    ):
        raise HTTPException(
            status_code=403,
            detail="You can create tickets only for your department.",
        )

    result = create_ticket(
        title=request.title.strip(),
        description=request.description.strip(),
        created_by=context["employee_id"],
        department_id=request.department_id,
        module=request.module,
        category=request.category,
        issue_type=request.issue_type,
        severity=request.severity.upper(),
        priority=request.priority.upper(),
    )

    if "error" in result:
        raise HTTPException(
            status_code=400,
            detail=result["error"],
        )

    ticket_id = result.get("ticket_id")

    if ticket_id is not None:
        background_tasks.add_task(
            sync_ticket_embedding_background,
            int(ticket_id),
        )

    return {
        "message": "Ticket created successfully.",
        **result,
        "created_by": context["employee_id"],
        "embedding_sync_scheduled": ticket_id is not None,
    }


# ============================================================
# LIST TICKETS
# ============================================================

@router.get("/")
def get_tickets(
    status: str | None = None,
    priority: str | None = None,
    severity: str | None = None,
    department_id: int | None = Query(default=None, gt=0),
    start_date: date | None = None,
    end_date: date | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    current_user: dict = Depends(get_current_user),
):
    context = _context(current_user)

    tickets = _fetch_tickets(
        context,
        status,
        priority,
        severity,
        department_id,
        start_date,
        end_date,
        sort_by,
        sort_order,
    )

    return {
        "count": len(tickets),
        "tickets": tickets,
    }


# ============================================================
# MANAGEMENT TICKET VIEW
# ============================================================

@router.get("/management/all")
def management_ticket_view(
    status: str | None = None,
    priority: str | None = None,
    severity: str | None = None,
    department_id: int | None = Query(default=None, gt=0),
    start_date: date | None = None,
    end_date: date | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    current_user: dict = Depends(
        require_roles("ADMIN", "MANAGER")
    ),
):
    context = _context(current_user)

    tickets = _fetch_tickets(
        context,
        status,
        priority,
        severity,
        department_id,
        start_date,
        end_date,
        sort_by,
        sort_order,
    )

    return {
        "count": len(tickets),
        "tickets": tickets,
        "accessed_by": context["employee_id"],
        "roles": context["roles"],
    }


# ============================================================
# ASSIGN TICKET
# ============================================================

@router.patch("/{ticket_id}/assign")
def assign_ticket_to_employee(
    ticket_id: int,
    request: AssignTicketRequest,
    current_user: dict = Depends(
        require_roles("ADMIN", "MANAGER")
    ),
):
    if ticket_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="Ticket ID must be greater than zero.",
        )

    context = _context(current_user)
    ticket = get_ticket_by_id(ticket_id)

    if ticket is None:
        raise HTTPException(
            status_code=404,
            detail="Ticket not found.",
        )

    if (
        "ADMIN" not in context["roles"]
        and ticket["department_id"] != context["department_id"]
    ):
        raise HTTPException(
            status_code=403,
            detail="You can assign tickets only within your department.",
        )

    assignee_id = request.assigned_to.strip()
    assignee_context = get_user_ticket_context(assignee_id)

    if not assignee_context or not assignee_context["is_active"]:
        raise HTTPException(
            status_code=400,
            detail="Assignee not found or inactive.",
        )

    if (
        "ADMIN" not in context["roles"]
        and assignee_context["department_id"] != context["department_id"]
    ):
        raise HTTPException(
            status_code=403,
            detail="You can assign tickets only to users in your department.",
        )

    result = assign_ticket(
        ticket_id,
        assignee_id,
        context["employee_id"],
    )

    if "error" in result:
        status_code = (
            404 if result["error"] == "Ticket not found." else 400
        )
        raise HTTPException(
            status_code=status_code,
            detail=result["error"],
        )

    return result


# ============================================================
# UPDATE TICKET
# ============================================================

@router.patch("/{ticket_id}")
def update_ticket_details(
    ticket_id: int,
    request: UpdateTicketRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(
        require_roles("ADMIN", "MANAGER", "DEVELOPER", "SUPPORT")
    ),
):
    if ticket_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="Ticket ID must be greater than zero.",
        )

    context = _context(current_user)
    ticket = _require_ticket_view(ticket_id, context)
    roles = set(context["roles"])

    if "ADMIN" not in roles:
        if "MANAGER" in roles:
            if ticket["department_id"] != context["department_id"]:
                raise HTTPException(
                    status_code=403,
                    detail="You can update tickets only within your department.",
                )
        elif ticket["assigned_to"] != context["employee_id"]:
            raise HTTPException(
                status_code=403,
                detail="You can update only tickets assigned to you.",
            )

    result = update_ticket(
        ticket_id=ticket_id,
        changed_by=context["employee_id"],
        status=request.status.upper() if request.status else None,
        priority=request.priority.upper() if request.priority else None,
        severity=request.severity.upper() if request.severity else None,
        resolution=request.resolution,
        resolution_notes=request.resolution_notes,
    )

    if "error" in result:
        message = result["error"]
        status_code = 404 if message == "Ticket not found." else 400

        raise HTTPException(
            status_code=status_code,
            detail=message,
        )

    background_tasks.add_task(
        sync_ticket_embedding_background,
        ticket_id,
    )

    return {
        **result,
        "embedding_sync_scheduled": True,
    }


# ============================================================
# DELETE TICKET
# ============================================================

@router.delete("/{ticket_id}")
def delete_ticket_endpoint(
    ticket_id: int,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(
        require_roles("ADMIN", "MANAGER")
    ),
):
    if ticket_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="Ticket ID must be greater than zero.",
        )

    context = _context(current_user)
    ticket = get_ticket_by_id(ticket_id)

    if ticket is None:
        raise HTTPException(
            status_code=404,
            detail="Ticket not found.",
        )

    if (
        "ADMIN" not in context["roles"]
        and ticket["department_id"] != context["department_id"]
    ):
        raise HTTPException(
            status_code=403,
            detail="You can delete tickets only within your department.",
        )

    result = delete_ticket_record(
        ticket_id=ticket_id,
        deleted_by=context["employee_id"],
    )

    if "error" in result:
        message = result["error"]
        status_code = 404 if message == "Ticket not found." else 400

        raise HTTPException(
            status_code=status_code,
            detail=message,
        )

    background_tasks.add_task(
        delete_ticket_embedding_background,
        ticket_id,
    )

    return {
        **result,
        "vector_deletion_scheduled": True,
    }


# ============================================================
# TICKET HISTORY
# ============================================================

@router.get("/{ticket_id}/history")
def get_single_ticket_history(
    ticket_id: int,
    current_user: dict = Depends(get_current_user),
):
    if ticket_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="Ticket ID must be greater than zero.",
        )

    context = _context(current_user)
    _require_ticket_view(ticket_id, context)

    history = get_ticket_history(ticket_id)

    return {
        "ticket_id": ticket_id,
        "count": len(history or []),
        "history": history or [],
    }


# ============================================================
# SINGLE TICKET
# ============================================================

@router.get("/{ticket_id}")
def get_single_ticket(
    ticket_id: int,
    current_user: dict = Depends(get_current_user),
):
    if ticket_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="Ticket ID must be greater than zero.",
        )

    context = _context(current_user)

    return _require_ticket_view(ticket_id, context)
