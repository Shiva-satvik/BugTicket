import random

from app.database.connection import get_connection

# ============================================================
# DOCUMENT RELEVANCE BY TICKET MODULE
# ============================================================

MODULE_DOCUMENTS = {
    "Payroll": [("FD-001", 0.90), ("FD-002", 0.75), ("FD-008", 0.60)],
    "Employee Banking": [("FD-002", 0.95), ("FD-001", 0.65), ("FD-008", 0.85)],
    "Accounts Payable": [("FD-003", 0.95), ("FD-006", 0.85), ("FD-004", 0.70)],
    "Vendor Payments": [("FD-004", 0.95), ("FD-003", 0.70), ("FD-008", 0.65)],
    "Expense Reimbursement": [("FD-005", 0.95), ("FD-008", 0.55)],
    "Procurement": [("FD-006", 0.95), ("FD-003", 0.70)],
    "Finance Controlling": [("FD-007", 0.95), ("FD-008", 0.70)],
    "Finance Systems & Information Security": [("FD-008", 0.98)],
}


# ============================================================
# MAP TICKETS TO DOCUMENTS
# ============================================================


def seed_ticket_documents():

    connection = get_connection()
    cursor = connection.cursor()

    # --------------------------------------------------------
    # Get documents
    # --------------------------------------------------------

    cursor.execute("""
        SELECT
            document_id,
            document_code
        FROM financial_documents
        WHERE is_active = 1
    """)

    documents = {row["document_code"]: row["document_id"] for row in cursor.fetchall()}

    # --------------------------------------------------------
    # Get tickets
    # --------------------------------------------------------

    cursor.execute("""
        SELECT
            ticket_id,
            module
        FROM tickets
    """)

    tickets = cursor.fetchall()

    if not tickets:
        connection.close()

        raise ValueError(
            "No tickets found. Seed tickets before "
            "creating ticket-document mappings."
        )

    mappings = []

    # --------------------------------------------------------
    # Process tickets
    # --------------------------------------------------------

    for ticket in tickets:

        ticket_id = ticket["ticket_id"]

        module = ticket["module"]

        possible_documents = MODULE_DOCUMENTS.get(module, [])

        if not possible_documents:
            continue

        # ----------------------------------------------------
        # Primary document
        # ----------------------------------------------------

        primary_document_code, primary_score = possible_documents[0]

        if primary_document_code in documents:

            mappings.append(
                (ticket_id, documents[primary_document_code], primary_score)
            )

        # ----------------------------------------------------
        # Optional secondary documents
        # ----------------------------------------------------

        for document_code, base_score in possible_documents[1:]:

            # Not every ticket needs every related document.
            if random.random() < 0.45:

                if document_code not in documents:
                    continue

                # Add slight randomness so relevance scores
                # don't look artificially identical.

                score = round(
                    max(0.50, min(0.95, base_score + random.uniform(-0.08, 0.05))), 3
                )

                mappings.append((ticket_id, documents[document_code], score))

    # --------------------------------------------------------
    # Insert mappings
    # --------------------------------------------------------

    cursor.executemany(
        """
        INSERT OR IGNORE INTO ticket_documents (
            ticket_id,
            document_id,
            relevance_score
        )
        VALUES (?, ?, ?)
    """,
        mappings,
    )

    connection.commit()
    connection.close()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    seed_ticket_documents()
    print("Ticket-document mappings seeded successfully.")
