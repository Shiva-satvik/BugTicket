from pathlib import Path
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
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
                      u.is_active, u.last_login_at, u.photo_url
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
# PROFILE PHOTO
# ============================================================

PROFILE_PHOTO_DIR = Path(__file__).resolve().parents[2] / "uploads" / "profile_photos"
MAX_PROFILE_PHOTO_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {
    "image/jpeg": (".jpg", lambda data: data.startswith(b"\xff\xd8\xff")),
    "image/png": (".png", lambda data: data.startswith(b"\x89PNG\r\n\x1a\n")),
    "image/webp": (".webp", lambda data: len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"),
}


@router.put("/profile/photo")
async def upload_profile_photo(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Save a validated profile image for the authenticated user."""
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=415, detail="Use a JPG, PNG, or WebP image.")

    image_bytes = await request.body()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="The uploaded image is empty.")
    if len(image_bytes) > MAX_PROFILE_PHOTO_BYTES:
        raise HTTPException(status_code=413, detail="Profile photos must be 5 MB or smaller.")
    extension, validator = ALLOWED_IMAGE_TYPES[content_type]
    if not validator(image_bytes):
        raise HTTPException(status_code=415, detail="The file contents do not match the selected image type.")

    employee_id = str(current_user["employee_id"])
    filename = f"{uuid.uuid4().hex}{extension}"
    PROFILE_PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    destination = PROFILE_PHOTO_DIR / filename
    destination.write_bytes(image_bytes)
    photo_url = f"/uploads/profile_photos/{filename}"

    from app.database.connection import get_connection
    connection = get_connection()
    old_photo_url = None
    try:
        row = connection.execute("SELECT photo_url FROM users WHERE employee_id = ?", (employee_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="User account was not found.")
        old_photo_url = row["photo_url"]
        connection.execute(
            "UPDATE users SET photo_url = ?, updated_at = CURRENT_TIMESTAMP WHERE employee_id = ?",
            (photo_url, employee_id),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        destination.unlink(missing_ok=True)
        raise
    finally:
        connection.close()

    _remove_old_photo(old_photo_url, photo_url)
    return {"photo_url": photo_url}


@router.delete("/profile/photo")
def remove_profile_photo(current_user: dict = Depends(get_current_user)):
    from app.database.connection import get_connection
    connection = get_connection()
    old_photo_url = None
    try:
        row = connection.execute("SELECT photo_url FROM users WHERE employee_id = ?", (current_user["employee_id"],)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="User account was not found.")
        old_photo_url = row["photo_url"]
        connection.execute(
            "UPDATE users SET photo_url = NULL, updated_at = CURRENT_TIMESTAMP WHERE employee_id = ?",
            (current_user["employee_id"],),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    _remove_old_photo(old_photo_url, None)
    return {"photo_url": None}


def _remove_old_photo(old_photo_url: str | None, new_photo_url: str | None) -> None:
    if not old_photo_url or old_photo_url == new_photo_url:
        return
    prefix = "/uploads/profile_photos/"
    if not old_photo_url.startswith(prefix):
        return
    candidate = (PROFILE_PHOTO_DIR / old_photo_url[len(prefix):]).resolve()
    try:
        candidate.relative_to(PROFILE_PHOTO_DIR.resolve())
    except ValueError:
        return
    candidate.unlink(missing_ok=True)


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
