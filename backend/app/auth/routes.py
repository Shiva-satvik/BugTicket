from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.auth.rbac import get_user_roles, require_roles
from app.auth.auth_service import authenticate_user
from app.auth.dependencies import get_current_user

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


# ============================================================
# LOGIN
# ============================================================


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(request: LoginRequest):

    result = authenticate_user(
        request.username,
        request.password,
    )

    if result is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
        )

    return result


# ============================================================
# CURRENT USER
# ============================================================


@router.get("/me")
def get_me(
    current_user: dict = Depends(get_current_user),
):
    """
    Return information about the currently
    authenticated user including assigned roles.
    """

    from app.database.connection import get_connection

    connection = get_connection()
    try:
        row = connection.execute(
            """SELECT u.employee_id, u.username, u.full_name, u.email,
                      u.department_id, d.department_name, u.designation,
                      u.is_active, u.last_login_at
               FROM users u
               LEFT JOIN departments d ON d.department_id = u.department_id
               WHERE u.employee_id = ?""",
            (current_user["employee_id"],),
        ).fetchone()
        if row is None or not row["is_active"]:
            raise HTTPException(status_code=401, detail="User is missing or inactive.")
        return {**dict(row), "roles": get_user_roles(current_user["employee_id"])}
    finally:
        connection.close()


# ============================================================
# ADMIN-ONLY TEST ENDPOINT
# ============================================================


@router.get("/admin-area")
def admin_area(
    current_user: dict = Depends(require_roles("ADMIN")),
):
    """
    Example endpoint accessible only to ADMIN users.
    """

    return {
        "message": "Admin access granted.",
        "employee_id": current_user["employee_id"],
        "username": current_user["username"],
        "roles": current_user["roles"],
    }
