from datetime import datetime
from app.database.connection import get_connection


VALID_STATUSES = {"PENDING", "OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED"}
VALID_PRIORITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL", "URGENT"}
VALID_SEVERITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
ALLOWED_SORT_COLUMNS = {
    "created_at": "t.created_at",
    "updated_at": "t.updated_at",
    "priority": "t.priority",
    "severity": "t.severity",
    "status": "t.status",
    "ticket_code": "t.ticket_code",
}


def create_ticket(
    title: str,
    description: str,
    created_by: str,
    department_id: int,
    module: str | None = None,
    category: str | None = None,
    issue_type: str | None = None,
    severity: str = "MEDIUM",
    priority: str = "MEDIUM",
):
    title = title.strip()
    description = description.strip()
    severity = severity.upper()
    priority = priority.upper()

    if not title or not description:
        return {"error": "Ticket title and description are required."}
    if severity not in VALID_SEVERITIES:
        return {"error": "Invalid severity."}
    if priority not in VALID_PRIORITIES:
        return {"error": "Invalid priority."}

    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT employee_id, department_id, is_active FROM users WHERE employee_id = ?",
            (created_by,),
        )
        creator = cursor.fetchone()
        if creator is None or not creator["is_active"]:
            return {"error": "Creator not found or inactive."}

        cursor.execute(
            "SELECT department_id FROM departments WHERE department_id = ? AND is_active = 1",
            (department_id,),
        )
        if cursor.fetchone() is None:
            return {"error": "Department not found or inactive."}

        year = datetime.now().year
        prefix = f"BP-{year}-"
        cursor.execute(
            """SELECT COALESCE(MAX(CAST(SUBSTR(ticket_code, 9) AS INTEGER)), 0)
               AS max_sequence
               FROM tickets WHERE ticket_code LIKE ?""",
            (f"{prefix}%",),
        )
        sequence = cursor.fetchone()["max_sequence"] + 1
        ticket_code = f"{prefix}{sequence:06d}"

        cursor.execute(
            """INSERT INTO tickets (
                ticket_code, title, description, created_by, department_id,
                module, category, issue_type, severity, priority
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ticket_code, title, description, created_by, department_id,
                module, category, issue_type, severity, priority,
            ),
        )
        ticket_id = cursor.lastrowid
        cursor.execute(
            """INSERT INTO ticket_history
               (ticket_id, changed_by, old_status, new_status, comment)
               VALUES (?, ?, NULL, 'OPEN', 'Ticket created')""",
            (ticket_id, created_by),
        )
        connection.commit()
        return {"ticket_id": ticket_id, "ticket_code": ticket_code}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def get_all_tickets(
    status: str | None = None,
    priority: str | None = None,
    severity: str | None = None,
    department_id: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    created_by: str | None = None,
    assigned_to: str | None = None,
    scope_department_id: int | None = None,
):
    if sort_by not in ALLOWED_SORT_COLUMNS:
        raise ValueError("Invalid sort field.")
    normalized_order = sort_order.lower()
    if normalized_order not in {"asc", "desc"}:
        raise ValueError("Sort order must be asc or desc.")

    connection = get_connection()
    try:
        query = """
            SELECT t.ticket_id, t.ticket_code, t.title, t.description,
                   t.created_by, creator.full_name AS created_by_name,
                   t.assigned_to, assignee.full_name AS assigned_to_name,
                   t.department_id, d.department_name, t.module, t.category,
                   t.issue_type, t.severity, t.priority, t.status,
                   t.resolution, t.resolution_notes, t.created_at, t.updated_at,
                   t.assigned_at, t.resolved_at, t.closed_at, t.embedding_status,
                   t.last_embedded_at, t.embedding_version, t.created_by_ai
            FROM tickets t
            INNER JOIN users creator ON t.created_by = creator.employee_id
            LEFT JOIN users assignee ON t.assigned_to = assignee.employee_id
            INNER JOIN departments d ON t.department_id = d.department_id
            WHERE 1 = 1
        """
        params = []

        for value, column in (
            (status, "t.status"),
            (priority, "t.priority"),
            (severity, "t.severity"),
        ):
            if value is not None:
                query += f" AND {column} = ?"
                params.append(value.upper())

        if department_id is not None:
            query += " AND t.department_id = ?"
            params.append(department_id)
        if start_date is not None:
            query += " AND date(t.created_at) >= date(?)"
            params.append(start_date)
        if end_date is not None:
            query += " AND date(t.created_at) <= date(?)"
            params.append(end_date)

        # Mandatory visibility scope; user-supplied filters cannot widen access.
        if created_by is not None:
            query += " AND t.created_by = ?"
            params.append(created_by)
        if assigned_to is not None:
            query += " AND t.assigned_to = ?"
            params.append(assigned_to)
        if scope_department_id is not None:
            query += " AND t.department_id = ?"
            params.append(scope_department_id)

        query += (
            f" ORDER BY {ALLOWED_SORT_COLUMNS[sort_by]} "
            f"{normalized_order.upper()}, t.ticket_id DESC"
        )
        cursor = connection.cursor()
        cursor.execute(query, tuple(params))
        return [dict(row) for row in cursor.fetchall()]
    finally:
        connection.close()


def get_ticket_by_id(ticket_id: int):
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            """SELECT t.ticket_id, t.ticket_code, t.title, t.description,
                      t.created_by, creator.full_name AS created_by_name,
                      t.assigned_to, assignee.full_name AS assigned_to_name,
                      t.department_id, d.department_name, t.module, t.category,
                      t.issue_type, t.severity, t.priority, t.status,
                      t.resolution, t.resolution_notes, t.created_at, t.updated_at,
                      t.assigned_at, t.resolved_at, t.closed_at, t.embedding_status,
                      t.last_embedded_at, t.embedding_version, t.created_by_ai
               FROM tickets t
               INNER JOIN users creator ON t.created_by = creator.employee_id
               LEFT JOIN users assignee ON t.assigned_to = assignee.employee_id
               INNER JOIN departments d ON t.department_id = d.department_id
               WHERE t.ticket_id = ?""",
            (ticket_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        connection.close()


def assign_ticket(ticket_id: int, assigned_to: str, changed_by: str):
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT ticket_id, department_id, status FROM tickets WHERE ticket_id = ?",
            (ticket_id,),
        )
        ticket = cursor.fetchone()
        if ticket is None:
            return {"error": "Ticket not found."}

        cursor.execute(
            """SELECT employee_id, department_id FROM users
               WHERE employee_id = ? AND is_active = 1""",
            (assigned_to,),
        )
        assignee = cursor.fetchone()
        if assignee is None:
            return {"error": "Assignee not found or inactive."}

        cursor.execute(
            "SELECT employee_id FROM users WHERE employee_id = ? AND is_active = 1",
            (changed_by,),
        )
        if cursor.fetchone() is None:
            return {"error": "Acting user not found or inactive."}

        cursor.execute(
            """UPDATE tickets SET assigned_to = ?, assigned_at = CURRENT_TIMESTAMP,
               updated_at = CURRENT_TIMESTAMP WHERE ticket_id = ?""",
            (assigned_to, ticket_id),
        )
        cursor.execute(
            """INSERT INTO ticket_history (ticket_id, changed_by, comment)
               VALUES (?, ?, ?)""",
            (ticket_id, changed_by, f"Ticket assigned to employee {assigned_to}"),
        )
        connection.commit()
        return {
            "message": "Ticket assigned successfully.",
            "ticket_id": ticket_id,
            "assigned_to": assigned_to,
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def update_ticket(
    ticket_id: int,
    changed_by: str,
    status: str | None = None,
    priority: str | None = None,
    severity: str | None = None,
    resolution: str | None = None,
    resolution_notes: str | None = None,
):
    if status is not None and status not in VALID_STATUSES:
        return {"error": "Invalid status."}
    if priority is not None and priority not in VALID_PRIORITIES:
        return {"error": "Invalid priority."}
    if severity is not None and severity not in VALID_SEVERITIES:
        return {"error": "Invalid severity."}
    if all(v is None for v in (status, priority, severity, resolution, resolution_notes)):
        return {"error": "No ticket changes provided."}

    transitions = {
        "PENDING": {"OPEN", "IN_PROGRESS"},
        "OPEN": {"IN_PROGRESS"},
        "IN_PROGRESS": {"OPEN", "RESOLVED"},
        "RESOLVED": {"IN_PROGRESS", "CLOSED"},
        "CLOSED": set(),
    }

    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            """SELECT status, priority, severity, resolution, resolution_notes
               FROM tickets WHERE ticket_id = ?""",
            (ticket_id,),
        )
        ticket = cursor.fetchone()
        if ticket is None:
            return {"error": "Ticket not found."}

        old_status = ticket["status"]
        old_priority = ticket["priority"]
        new_status = status if status is not None else old_status
        new_priority = priority if priority is not None else old_priority

        if status is not None and status != old_status:
            if status not in transitions[old_status]:
                return {"error": f"Status transition from {old_status} to {status} is not allowed."}
        if status == "RESOLVED" and not (
            (resolution and resolution.strip()) or
            (ticket["resolution"] and ticket["resolution"].strip())
        ):
            return {"error": "A resolution description is required before resolving a ticket."}
        if status == "CLOSED" and old_status != "RESOLVED":
            return {"error": "Only resolved tickets can be closed."}

        updates, values = [], []
        if status is not None:
            updates.append("status = ?")
            values.append(status)
        if priority is not None:
            updates.append("priority = ?")
            values.append(priority)
        if severity is not None:
            updates.append("severity = ?")
            values.append(severity)
        if resolution is not None:
            updates.append("resolution = ?")
            values.append(resolution)
        if resolution_notes is not None:
            updates.append("resolution_notes = ?")
            values.append(resolution_notes)

        if status == "RESOLVED":
            updates.append("resolved_at = CURRENT_TIMESTAMP")
        elif status == "CLOSED":
            updates.append("closed_at = CURRENT_TIMESTAMP")
        elif status in {"OPEN", "IN_PROGRESS"}:
            updates.extend(["resolved_at = NULL", "closed_at = NULL"])

        updates.append("updated_at = CURRENT_TIMESTAMP")
        values.append(ticket_id)
        cursor.execute(
            f"UPDATE tickets SET {', '.join(updates)} WHERE ticket_id = ?",
            tuple(values),
        )

        changes = []
        if old_status != new_status:
            changes.append(f"Status: {old_status} -> {new_status}")
        if old_priority != new_priority:
            changes.append(f"Priority: {old_priority} -> {new_priority}")
        if severity is not None and severity != ticket["severity"]:
            changes.append(f"Severity updated to {severity}")
        if resolution is not None and resolution != ticket["resolution"]:
            changes.append("Resolution description updated")
        if resolution_notes is not None and resolution_notes != ticket["resolution_notes"]:
            changes.append("Resolution notes updated")

        if changes:
            cursor.execute(
                """INSERT INTO ticket_history
                   (ticket_id, changed_by, old_status, new_status,
                    old_priority, new_priority, comment)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    ticket_id, changed_by,
                    old_status if old_status != new_status else None,
                    new_status if old_status != new_status else None,
                    old_priority if old_priority != new_priority else None,
                    new_priority if old_priority != new_priority else None,
                    "; ".join(changes),
                ),
            )

        connection.commit()
        return {
            "message": "Ticket updated successfully.",
            "ticket_id": ticket_id,
            "status": new_status,
            "priority": new_priority,
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def get_ticket_history(ticket_id: int):
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT ticket_id FROM tickets WHERE ticket_id = ?", (ticket_id,))
        if cursor.fetchone() is None:
            return None
        cursor.execute(
            """SELECT th.history_id, th.ticket_id, t.ticket_code, th.changed_by,
                      u.full_name AS changed_by_name, th.old_status, th.new_status,
                      th.old_priority, th.new_priority, th.comment, th.changed_at
               FROM ticket_history th
               INNER JOIN users u ON th.changed_by = u.employee_id
               INNER JOIN tickets t ON th.ticket_id = t.ticket_id
               WHERE th.ticket_id = ?
               ORDER BY th.changed_at DESC, th.history_id DESC""",
            (ticket_id,),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        connection.close()


def get_user_ticket_context(employee_id: str):
    """Return a user's department and active roles for route-level authorization."""
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            """SELECT employee_id, department_id, is_active
               FROM users WHERE employee_id = ?""",
            (employee_id,),
        )
        user = cursor.fetchone()
        if user is None:
            return None
        cursor.execute(
            """SELECT r.role_code FROM roles r
               INNER JOIN user_roles ur ON ur.role_id = r.role_id
               WHERE ur.employee_id = ? AND r.is_active = 1""",
            (employee_id,),
        )
        return {
            "employee_id": user["employee_id"],
            "department_id": user["department_id"],
            "is_active": bool(user["is_active"]),
            "roles": [row["role_code"] for row in cursor.fetchall()],
        }
    finally:
        connection.close()

def delete_ticket(ticket_id: int, deleted_by: str):
    """
    Delete a ticket and its history from SQLite.
    The caller must enforce authorization before invoking this function.
    """

    if ticket_id <= 0:
        return {"error": "Ticket ID must be greater than 0."}

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT ticket_id, ticket_code
            FROM tickets
            WHERE ticket_id = ?
            """,
            (ticket_id,),
        )

        ticket = cursor.fetchone()

        if ticket is None:
            return {"error": "Ticket not found."}

        cursor.execute(
            """
            SELECT employee_id
            FROM users
            WHERE employee_id = ? AND is_active = 1
            """,
            (deleted_by,),
        )

        if cursor.fetchone() is None:
            return {"error": "Acting user not found or inactive."}

        # Remove dependent history before deleting the ticket.
        cursor.execute(
            "DELETE FROM ticket_history WHERE ticket_id = ?",
            (ticket_id,),
        )

        cursor.execute(
            "DELETE FROM tickets WHERE ticket_id = ?",
            (ticket_id,),
        )

        connection.commit()

        return {
            "message": "Ticket deleted successfully.",
            "ticket_id": ticket_id,
            "ticket_code": ticket["ticket_code"],
        }

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()
