import random
from datetime import datetime, timedelta

from app.database.connection import get_connection

# ============================================================
# STATUS FLOW
# ============================================================

STATUS_FLOWS = {
    "OPEN": [
        ["OPEN"],
    ],
    "IN_PROGRESS": [
        ["OPEN", "IN_PROGRESS"],
    ],
    "PENDING": [
        ["OPEN", "IN_PROGRESS", "PENDING"],
    ],
    "RESOLVED": [
        ["OPEN", "IN_PROGRESS", "RESOLVED"],
        ["OPEN", "IN_PROGRESS", "PENDING", "IN_PROGRESS", "RESOLVED"],
    ],
    "CLOSED": [
        ["OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED"],
        ["OPEN", "IN_PROGRESS", "PENDING", "IN_PROGRESS", "RESOLVED", "CLOSED"],
    ],
}


# ============================================================
# HISTORY COMMENTS
# ============================================================

COMMENTS = {
    "OPEN": [
        "Ticket created and awaiting investigation.",
        "Issue reported by employee.",
        "Ticket submitted for support review.",
    ],
    "IN_PROGRESS": [
        "Ticket assigned and investigation started.",
        "Support team started investigating the issue.",
        "Issue analysis is currently in progress.",
        "Development team is investigating the reported issue.",
    ],
    "PENDING": [
        "Waiting for additional information.",
        "Waiting for approval from the responsible team.",
        "Issue placed on hold pending clarification.",
        "Waiting for external system response.",
    ],
    "RESOLVED": [
        "Issue resolved after investigation.",
        "Fix applied and issue successfully resolved.",
        "Root cause identified and corrective action completed.",
        "Resolution applied and validated.",
    ],
    "CLOSED": [
        "Resolution verified and ticket closed.",
        "User confirmed resolution and ticket was closed.",
        "Ticket closure completed after validation.",
    ],
}


# ============================================================
# PRIORITY CHANGE COMMENTS
# ============================================================

PRIORITY_COMMENTS = [
    "Priority updated based on business impact.",
    "Priority increased due to operational impact.",
    "Priority reviewed by support team.",
    "Priority adjusted after investigation.",
]


# ============================================================
# HELPER
# ============================================================


def generate_history_time(created_at, step_number):

    created_datetime = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")

    return created_datetime + timedelta(hours=step_number * random.randint(2, 12))


# ============================================================
# CREATE TICKET HISTORY
# ============================================================


def seed_ticket_history():

    connection = get_connection()
    cursor = connection.cursor()

    # --------------------------------------------------------
    # Get all tickets
    # --------------------------------------------------------

    cursor.execute("""
        SELECT
            ticket_id,
            created_by,
            assigned_to,
            status,
            priority,
            created_at
        FROM tickets
        ORDER BY ticket_id
    """)

    tickets = cursor.fetchall()

    if not tickets:
        connection.close()

        raise ValueError("No tickets found. Seed tickets before creating history.")

    history_records = []

    # --------------------------------------------------------
    # Process every ticket
    # --------------------------------------------------------

    for ticket in tickets:

        ticket_id = ticket["ticket_id"]

        created_by = ticket["created_by"]

        assigned_to = ticket["assigned_to"]

        final_status = ticket["status"]

        final_priority = ticket["priority"]

        created_at = ticket["created_at"]

        # ----------------------------------------------------
        # Select status flow
        # ----------------------------------------------------

        possible_flows = STATUS_FLOWS.get(final_status, [["OPEN"]])

        status_flow = random.choice(possible_flows)

        # ----------------------------------------------------
        # Current status
        # ----------------------------------------------------

        old_status = None

        # ----------------------------------------------------
        # Generate status history
        # ----------------------------------------------------

        for index, new_status in enumerate(status_flow):

            # ------------------------------------------------
            # First record
            # ------------------------------------------------

            if index == 0:

                changed_by = created_by

            else:

                changed_by = assigned_to if assigned_to else created_by

            changed_at = generate_history_time(created_at, index + 1)

            comment = random.choice(COMMENTS.get(new_status, COMMENTS["OPEN"]))

            # ------------------------------------------------
            # Priority
            # ------------------------------------------------

            old_priority = None
            new_priority = None

            if index == 0:

                new_priority = final_priority

            elif random.random() < 0.20:

                old_priority = final_priority

                new_priority = random.choice(["LOW", "MEDIUM", "HIGH", "URGENT"])

                comment = random.choice(PRIORITY_COMMENTS)

            history_records.append(
                (
                    ticket_id,
                    changed_by,
                    old_status,
                    new_status,
                    old_priority,
                    new_priority,
                    comment,
                    changed_at.strftime("%Y-%m-%d %H:%M:%S"),
                )
            )

            old_status = new_status

        # ----------------------------------------------------
        # Add an occasional additional priority update
        # ----------------------------------------------------

        if random.random() < 0.25:

            changed_by = assigned_to if assigned_to else created_by

            changed_at = generate_history_time(created_at, len(status_flow) + 1)

            history_records.append(
                (
                    ticket_id,
                    changed_by,
                    final_status,
                    final_status,
                    final_priority,
                    final_priority,
                    random.choice(PRIORITY_COMMENTS),
                    changed_at.strftime("%Y-%m-%d %H:%M:%S"),
                )
            )

    # --------------------------------------------------------
    # Insert history
    # --------------------------------------------------------

    cursor.executemany(
        """
        INSERT INTO ticket_history (
            ticket_id,
            changed_by,
            old_status,
            new_status,
            old_priority,
            new_priority,
            comment,
            changed_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
        history_records,
    )

    connection.commit()
    connection.close()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    seed_ticket_history()
    print("Ticket history seeded successfully.")
