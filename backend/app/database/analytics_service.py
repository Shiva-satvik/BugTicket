from app.database.connection import get_connection


# --------------------------------------------------
# Role-Based Visibility
# --------------------------------------------------

def _build_visibility_scope(
    employee_id: str,
    roles: list[str],
    department_id: int | None,
) -> tuple[str, list]:
    """Match analytics visibility to enterprise-ticket authorization rules."""
    normalized_roles = {role.upper() for role in roles}
    if "ADMIN" in normalized_roles:
        return "", []
    if normalized_roles.intersection({"MANAGER", "VIEWER"}):
        if department_id is None:
            raise ValueError("Department could not be determined.")
        return " AND t.department_id = ?", [department_id]
    if normalized_roles.intersection({"DEVELOPER", "SUPPORT"}):
        return " AND (t.created_by = ? OR t.assigned_to = ?)", [employee_id, employee_id]
    return " AND t.created_by = ?", [employee_id]


def get_dashboard_statistics(
    employee_id: str,
    roles: list[str],
    department_id: int | None,
) -> dict:
    """Return dashboard statistics within the user's access scope."""

    scope_sql, scope_params = _build_visibility_scope(
        employee_id,
        roles,
        department_id,
    )

    query = """
        SELECT
            COUNT(*) AS total_tickets,

            COALESCE(
                SUM(CASE WHEN t.status IN ('OPEN', 'PENDING')
                    THEN 1 ELSE 0 END), 0
            ) AS open_tickets,

            COALESCE(
                SUM(CASE WHEN t.status = 'IN_PROGRESS'
                    THEN 1 ELSE 0 END), 0
            ) AS in_progress_tickets,

            COALESCE(
                SUM(CASE WHEN t.status = 'RESOLVED'
                    THEN 1 ELSE 0 END), 0
            ) AS resolved_tickets,

            COALESCE(
                SUM(CASE WHEN t.status = 'CLOSED'
                    THEN 1 ELSE 0 END), 0
            ) AS closed_tickets,

            COALESCE(
                SUM(CASE WHEN t.severity = 'CRITICAL'
                    THEN 1 ELSE 0 END), 0
            ) AS critical_tickets,

            COALESCE(
                SUM(CASE WHEN t.priority = 'HIGH'
                    THEN 1 ELSE 0 END), 0
            ) AS high_priority_tickets,

            COALESCE(
                SUM(CASE WHEN t.priority = 'CRITICAL'
                    THEN 1 ELSE 0 END), 0
            ) AS critical_priority_tickets

        FROM tickets t
        WHERE 1 = 1
    """ + scope_sql

    connection = get_connection()

    try:
        cursor = connection.cursor()
        cursor.execute(query, tuple(scope_params))
        row = cursor.fetchone()

        return dict(row)

    finally:
        connection.close()


# --------------------------------------------------
# Daily, Weekly, and Monthly Timeline
# --------------------------------------------------

def get_ticket_timeline(
    employee_id: str,
    roles: list[str],
    department_id: int | None,
    period: str = "daily",
    limit: int = 30,
) -> dict:
    """
    Group tickets by creation date.

    Supported periods: daily, weekly, monthly.
    """

    period = period.lower()

    period_formats = {
        "daily": "%Y-%m-%d",
        "weekly": "%Y-W%W",
        "monthly": "%Y-%m",
    }

    if period not in period_formats:
        raise ValueError(
            "Period must be daily, weekly, or monthly."
        )

    if not 1 <= limit <= 365:
        raise ValueError("Limit must be between 1 and 365.")

    date_format = period_formats[period]

    scope_sql, scope_params = _build_visibility_scope(
        employee_id,
        roles,
        department_id,
    )

    query = f"""
        SELECT
            strftime('{date_format}', t.created_at) AS period,
            COUNT(*) AS ticket_count
        FROM tickets t
        WHERE t.created_at IS NOT NULL
        {scope_sql}
        GROUP BY strftime('{date_format}', t.created_at)
        ORDER BY period DESC
        LIMIT ?
    """

    connection = get_connection()

    try:
        cursor = connection.cursor()
        cursor.execute(
            query,
            tuple(scope_params + [limit]),
        )

        rows = [dict(row) for row in cursor.fetchall()]
        rows.reverse()

        return {
            "period_type": period,
            "count": len(rows),
            "timeline": rows,
        }

    finally:
        connection.close()


# --------------------------------------------------
# Ticket Breakdown Analytics
# --------------------------------------------------

def get_ticket_breakdowns(
    employee_id: str,
    roles: list[str],
    department_id: int | None,
) -> dict:
    """
    Return ticket distributions by department, status,
    severity, and priority within the user's access scope.
    """

    scope_sql, scope_params = _build_visibility_scope(
        employee_id,
        roles,
        department_id,
    )

    connection = get_connection()

    try:
        cursor = connection.cursor()
        results = {}

        # ------------------------------------------
        # Department Breakdown
        # ------------------------------------------

        department_query = """
            SELECT
                d.department_id AS id,
                d.department_name AS label,
                COUNT(t.ticket_id) AS ticket_count
            FROM tickets t
            INNER JOIN departments d
                ON t.department_id = d.department_id
            WHERE 1 = 1
        """ + scope_sql + """
            GROUP BY d.department_id, d.department_name
            ORDER BY ticket_count DESC, d.department_name ASC
        """

        cursor.execute(
            department_query,
            tuple(scope_params),
        )

        results["by_department"] = [
            dict(row) for row in cursor.fetchall()
        ]

        # ------------------------------------------
        # Status, Severity, and Priority
        # ------------------------------------------

        breakdown_columns = {
            "by_status": "t.status",
            "by_severity": "t.severity",
            "by_priority": "t.priority",
        }

        for key, column in breakdown_columns.items():
            query = f"""
                SELECT
                    {column} AS label,
                    COUNT(*) AS ticket_count
                FROM tickets t
                WHERE 1 = 1
                {scope_sql}
                GROUP BY {column}
                ORDER BY ticket_count DESC, {column} ASC
            """

            cursor.execute(query, tuple(scope_params))

            results[key] = [
                dict(row) for row in cursor.fetchall()
            ]

        return results

    finally:
        connection.close()