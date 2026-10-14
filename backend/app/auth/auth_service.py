from app.database.connection import get_connection
from app.auth.password import verify_password
from app.auth.jwt_handler import create_access_token


def authenticate_user(username: str, password: str):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            employee_id,
            username,
            full_name,
            email,
            password_hash,
            department_id,
            designation,
            is_active
        FROM users
        WHERE username = ?
    """,
        (username,),
    )

    user = cursor.fetchone()
    connection.close()

    if user is None:
        return None

    if not user["is_active"]:
        return None

    if not verify_password(password, user["password_hash"]):
        return None

    token_data = {"employee_id": user["employee_id"], "username": user["username"]}

    access_token = create_access_token(token_data)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "employee_id": user["employee_id"],
        "username": user["username"],
        "full_name": user["full_name"],
        "email": user["email"],
        "department_id": user["department_id"],
        "designation": user["designation"],
    }
