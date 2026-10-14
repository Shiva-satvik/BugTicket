from fastapi import Depends, HTTPException, status

from app.auth.dependencies import get_current_user
from app.database.connection import get_connection


def get_user_roles(employee_id: str) -> list[str]:
    """
    Retrieve all roles assigned to an employee.
    """

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT r.role_code
        FROM roles r
        INNER JOIN user_roles ur
            ON r.role_id = ur.role_id
        WHERE ur.employee_id = ?
          AND r.is_active = 1
        """,
        (employee_id,),
    )

    roles = [row["role_code"] for row in cursor.fetchall()]

    connection.close()

    return roles


def require_roles(*allowed_roles: str):
    """
    Create a FastAPI dependency that allows only
    users having at least one of the specified roles.
    """

    def role_checker(
        current_user: dict = Depends(get_current_user),
    ):
        employee_id = current_user["employee_id"]

        user_roles = get_user_roles(employee_id)

        if not user_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User has no assigned role.",
            )

        if not any(role in user_roles for role in allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this resource.",
            )

        return {
            **current_user,
            "roles": user_roles,
        }

    return role_checker
