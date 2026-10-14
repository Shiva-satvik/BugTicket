
import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.dependencies import get_current_user
from app.database.analytics_service import (
    get_dashboard_statistics,
    get_ticket_timeline,
    get_ticket_breakdowns,
)
from app.database.enterprise_ticket_service import (
    get_user_ticket_context,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/analytics",
    tags=["Dashboard Analytics"],
)


# --------------------------------------------------
# Shared Authentication and Authorization
# --------------------------------------------------

def _get_analytics_context(current_user: dict) -> dict:
    """Resolve an active employee's roles and department."""

    employee_id = current_user.get("employee_id")

    if not employee_id:
        raise HTTPException(
            status_code=401,
            detail="Authenticated employee information is missing.",
        )

    context = get_user_ticket_context(employee_id)

    if context is None or not context["is_active"]:
        raise HTTPException(
            status_code=403,
            detail="User not found or inactive.",
        )

    roles = {
        role.upper()
        for role in context["roles"]
    }

    if not roles:
        raise HTTPException(
            status_code=403,
            detail="User has no assigned roles.",
        )

    if "MANAGER" in roles and "ADMIN" not in roles:
        if context["department_id"] is None:
            raise HTTPException(
                status_code=403,
                detail="Manager department could not be determined.",
            )

    return {
        "employee_id": employee_id,
        "roles": list(roles),
        "department_id": context["department_id"],
    }


def _get_scope_name(roles: list[str]) -> str:
    """Return the effective analytics scope."""

    normalized_roles = {
        role.upper()
        for role in roles
    }

    if "ADMIN" in normalized_roles:
        return "company"

    if normalized_roles.intersection({"MANAGER", "VIEWER"}):
        return "department"

    if normalized_roles.intersection({"DEVELOPER", "SUPPORT"}):
        return "assigned + created"

    return "personal"


# --------------------------------------------------
# 6.1 Dashboard Statistics
# GET /api/analytics/dashboard
# --------------------------------------------------

@router.get("/dashboard")
def dashboard_statistics(
    current_user: dict = Depends(get_current_user),
):
    try:
        context = _get_analytics_context(current_user)

        statistics = get_dashboard_statistics(
            employee_id=context["employee_id"],
            roles=context["roles"],
            department_id=context["department_id"],
        )

        return {
            "message": "Dashboard statistics retrieved successfully.",
            "scope": _get_scope_name(context["roles"]),
            "statistics": statistics,
        }

    except HTTPException:
        raise

    except ValueError as error:
        logger.warning("Dashboard access rejected: %s", error)

        raise HTTPException(
            status_code=403,
            detail="Dashboard access could not be determined.",
        ) from error

    except Exception as error:
        logger.exception("Failed to retrieve dashboard statistics.")

        raise HTTPException(
            status_code=500,
            detail="Could not retrieve dashboard statistics.",
        ) from error


# --------------------------------------------------
# 6.2 Daily, Weekly, and Monthly Timeline
# GET /api/analytics/timeline
# --------------------------------------------------

@router.get("/timeline")
def ticket_timeline(
    period: str = Query(
        default="daily",
        description="Grouping period: daily, weekly, or monthly.",
    ),
    limit: int = Query(
        default=30,
        ge=1,
        le=365,
        description="Maximum number of periods to return.",
    ),
    current_user: dict = Depends(get_current_user),
):
    normalized_period = period.lower()

    if normalized_period not in {
        "daily",
        "weekly",
        "monthly",
    }:
        raise HTTPException(
            status_code=400,
            detail="Period must be daily, weekly, or monthly.",
        )

    try:
        context = _get_analytics_context(current_user)

        result = get_ticket_timeline(
            employee_id=context["employee_id"],
            roles=context["roles"],
            department_id=context["department_id"],
            period=normalized_period,
            limit=limit,
        )

        return {
            "message": "Ticket timeline retrieved successfully.",
            "scope": _get_scope_name(context["roles"]),
            **result,
        }

    except HTTPException:
        raise

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    except Exception as error:
        logger.exception("Failed to retrieve ticket timeline.")

        raise HTTPException(
            status_code=500,
            detail="Could not retrieve ticket timeline.",
        ) from error


# --------------------------------------------------
# 6.3 Department, Status, Severity, Priority
# GET /api/analytics/breakdowns
# --------------------------------------------------

@router.get("/breakdowns")
def ticket_breakdowns(
    current_user: dict = Depends(get_current_user),
):
    try:
        context = _get_analytics_context(current_user)

        breakdowns = get_ticket_breakdowns(
            employee_id=context["employee_id"],
            roles=context["roles"],
            department_id=context["department_id"],
        )

        return {
            "message": "Ticket breakdowns retrieved successfully.",
            "scope": _get_scope_name(context["roles"]),
            "breakdowns": breakdowns,
        }

    except HTTPException:
        raise

    except ValueError as error:
        logger.warning("Ticket breakdown access rejected: %s", error)

        raise HTTPException(
            status_code=403,
            detail="Ticket breakdown access could not be determined.",
        ) from error

    except Exception as error:
        logger.exception("Failed to retrieve ticket breakdowns.")

        raise HTTPException(
            status_code=500,
            detail="Could not retrieve ticket breakdowns.",
        ) from error


# --------------------------------------------------
# 6.4 Effective Dashboard Access
# GET /api/analytics/access
# --------------------------------------------------

@router.get("/access")
def dashboard_access(
    current_user: dict = Depends(get_current_user),
):
    """Return the authenticated user's effective dashboard scope."""

    context = _get_analytics_context(current_user)

    return {
        "employee_id": context["employee_id"],
        "roles": context["roles"],
        "department_id": context["department_id"],
        "scope": _get_scope_name(context["roles"]),
        "permissions": {
            "view_company_analytics": (
                "ADMIN" in context["roles"]
            ),
            "view_department_analytics": (
                "ADMIN" in context["roles"]
                or "MANAGER" in context["roles"]
                or "VIEWER" in context["roles"]
            ),
            "view_personal_tickets": True,
            "view_ticket_breakdowns": True,
            "view_ticket_timeline": True,
        },
    }
