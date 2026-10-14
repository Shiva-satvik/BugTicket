import random
from datetime import datetime, timedelta

from app.database.connection import get_connection

# ============================================================
# TICKET CONFIGURATION
# ============================================================

TICKET_COUNT = 1000


# ============================================================
# TICKET SCENARIOS
# ============================================================

TICKET_SCENARIOS = [
    # --------------------------------------------------------
    # PAYROLL
    # --------------------------------------------------------
    {
        "module": "Payroll",
        "category": "Payroll Processing",
        "issue_type": "Batch Failure",
        "titles": [
            "Payroll batch failed during processing",
            "Monthly payroll batch processing failed",
            "Payroll run stopped with processing error",
            "Payroll batch failed for multiple employees",
        ],
        "descriptions": [
            "The monthly payroll batch failed during processing and several employee records were not completed.",
            "Payroll processing stopped unexpectedly during the calculation stage.",
            "The payroll batch returned an error and requires investigation before rerunning.",
            "Several payroll records were left unprocessed after the payroll batch failed.",
        ],
        "resolution": [
            "Identified the failed records, corrected the processing issue and reran the payroll batch successfully.",
            "The batch error was corrected and the payroll was reprocessed after validation.",
            "Failed records were reviewed, corrected and successfully reconciled.",
        ],
    },
    {
        "module": "Payroll",
        "category": "Salary Processing",
        "issue_type": "Salary Not Credited",
        "titles": [
            "Employee salary not credited",
            "Salary payment missing for employee",
            "Payroll completed but salary not credited",
            "Employee payment showing pending",
        ],
        "descriptions": [
            "Payroll shows the employee as processed but the salary payment has not been credited.",
            "An employee reported that the expected salary payment was not received.",
            "Salary processing completed but the payment status is still pending.",
            "Employee salary payment appears to have been rejected or delayed.",
        ],
        "resolution": [
            "Payment status and reconciliation response were reviewed and the payment was reprocessed.",
            "The payment response was reviewed and the issue was resolved after reconciliation.",
            "The payroll inclusion and payment status were verified and the transaction was corrected.",
        ],
    },
    {
        "module": "Payroll",
        "category": "Payroll Validation",
        "issue_type": "Validation Error",
        "titles": [
            "Payroll validation failed",
            "Unexpected net salary validation error",
            "Payroll validation showing incorrect deduction",
            "Employee payroll record failed validation",
        ],
        "descriptions": [
            "Payroll validation identified an unexpected value in the employee salary calculation.",
            "An employee payroll record failed validation because of an incorrect deduction.",
            "The payroll validation process reported an inconsistent salary component.",
            "Payroll validation detected an unexpected net salary value.",
        ],
        "resolution": [
            "The salary components were corrected and payroll validation completed successfully.",
            "The incorrect deduction was corrected and the record was revalidated.",
            "The employee payroll record was corrected and successfully included in the payroll run.",
        ],
    },
    # --------------------------------------------------------
    # BANK ACCOUNT
    # --------------------------------------------------------
    {
        "module": "Employee Banking",
        "category": "Bank Account",
        "issue_type": "Validation Failure",
        "titles": [
            "Employee bank account validation failed",
            "Bank account change request rejected",
            "Employee banking details failed validation",
            "Bank account update remains in exception",
        ],
        "descriptions": [
            "An employee bank account change request failed validation and remains in exception state.",
            "The employee banking update could not be validated successfully.",
            "A bank account change request contains conflicting information and requires review.",
            "The banking details update failed during validation.",
        ],
        "resolution": [
            "The required banking information was corrected and the request was successfully validated.",
            "The request was reviewed, corrected and moved forward after validation.",
            "The conflicting information was resolved and the banking update was approved.",
        ],
    },
    # --------------------------------------------------------
    # VENDOR INVOICE
    # --------------------------------------------------------
    {
        "module": "Accounts Payable",
        "category": "Vendor Invoice",
        "issue_type": "Amount Mismatch",
        "titles": [
            "Vendor invoice amount mismatch",
            "Invoice total does not match expected amount",
            "Vendor invoice requires exception review",
            "Invoice amount differs from purchase details",
        ],
        "descriptions": [
            "The vendor invoice amount does not match the expected payable amount.",
            "An invoice was placed in exception because the total amount differs from the expected value.",
            "Invoice quantity, pricing or tax values require review before payment.",
            "The invoice amount mismatch is preventing payment processing.",
        ],
        "resolution": [
            "The invoice values were reviewed and corrected after clarification from the responsible team.",
            "The invoice was corrected and successfully moved forward for processing.",
            "The mismatch was resolved and the invoice passed validation.",
        ],
    },
    {
        "module": "Accounts Payable",
        "category": "Vendor Invoice",
        "issue_type": "Duplicate Invoice",
        "titles": [
            "Potential duplicate vendor invoice",
            "Duplicate invoice detected",
            "Vendor invoice appears to be duplicated",
            "Duplicate payable requires review",
        ],
        "descriptions": [
            "The system identified a potential duplicate vendor invoice.",
            "A second invoice with the same invoice reference was detected.",
            "The invoice appears to duplicate an existing payable transaction.",
            "A duplicate invoice warning was generated during invoice processing.",
        ],
        "resolution": [
            "The duplicate was confirmed and the second payable was prevented.",
            "The invoice was held for review and the duplicate transaction was cancelled.",
            "The existing payable was confirmed and the duplicate invoice was rejected.",
        ],
    },
    {
        "module": "Accounts Payable",
        "category": "Vendor Invoice",
        "issue_type": "Posting Failure",
        "titles": [
            "Vendor invoice posting failed",
            "Invoice posting error in ERP",
            "Invoice failed during financial posting",
            "Accounts payable posting failed",
        ],
        "descriptions": [
            "The vendor invoice failed while posting to the financial system.",
            "Invoice posting returned an ERP processing error.",
            "The invoice could not be posted to the accounting period.",
            "A vendor invoice encountered a posting failure.",
        ],
        "resolution": [
            "The posting error was identified and corrected before retrying the invoice.",
            "The affected invoice was corrected and successfully posted.",
            "The posting issue was resolved and the invoice was successfully processed.",
        ],
    },
    # --------------------------------------------------------
    # VENDOR PAYMENT
    # --------------------------------------------------------
    {
        "module": "Vendor Payments",
        "category": "Payment Processing",
        "issue_type": "Payment Failure",
        "titles": [
            "Vendor payment failed",
            "Payment batch returned bank rejection",
            "Vendor payment processing failed",
            "Payment transaction requires reprocessing",
        ],
        "descriptions": [
            "A vendor payment failed during processing and returned a bank response error.",
            "The payment batch contains a failed transaction requiring investigation.",
            "Vendor payment processing returned an error during bank submission.",
            "The payment transaction was rejected and requires correction.",
        ],
        "resolution": [
            "The payment response was reviewed, the cause was corrected and the payment was reprocessed.",
            "The beneficiary information was corrected and the payment was successfully reprocessed.",
            "The payment failure was resolved after validation and reconciliation.",
        ],
    },
    # --------------------------------------------------------
    # EXPENSES
    # --------------------------------------------------------
    {
        "module": "Expense Reimbursement",
        "category": "Employee Expenses",
        "issue_type": "Claim Rejection",
        "titles": [
            "Employee expense claim rejected",
            "Expense reimbursement claim requires correction",
            "Expense claim rejected due to missing receipt",
            "Expense reimbursement requires manager approval",
        ],
        "descriptions": [
            "An employee expense reimbursement claim was rejected during review.",
            "The submitted expense claim is missing required supporting information.",
            "The expense claim requires additional documentation before approval.",
            "The reimbursement request could not proceed because the required approval was missing.",
        ],
        "resolution": [
            "The employee provided the required information and the claim was resubmitted.",
            "The missing documentation was provided and the claim was approved.",
            "The required manager approval was obtained and the claim moved to reimbursement.",
        ],
    },
    # --------------------------------------------------------
    # PROCUREMENT
    # --------------------------------------------------------
    {
        "module": "Procurement",
        "category": "Purchase Order",
        "issue_type": "PO Mismatch",
        "titles": [
            "Purchase order mismatch with invoice",
            "Invoice price differs from PO",
            "Purchase order validation failed",
            "PO and invoice values do not match",
        ],
        "descriptions": [
            "The invoice unit price differs from the approved purchase order price.",
            "The purchase order and invoice values do not match.",
            "The invoice could not pass PO validation because of a pricing difference.",
            "A mismatch was identified between the approved purchase order and invoice.",
        ],
        "resolution": [
            "The purchase order and invoice were reviewed and the discrepancy was resolved.",
            "The invoice was corrected after confirmation of the approved purchase order value.",
            "The pricing mismatch was resolved and invoice processing continued.",
        ],
    },
    {
        "module": "Procurement",
        "category": "Goods Receipt",
        "issue_type": "Receipt Mismatch",
        "titles": [
            "Goods receipt quantity mismatch",
            "Invoice quantity exceeds received quantity",
            "Goods receipt missing for invoice",
            "Incorrect goods receipt blocking invoice",
        ],
        "descriptions": [
            "The invoiced quantity exceeds the accepted goods receipt quantity.",
            "A required goods receipt is missing for the invoice.",
            "The goods receipt quantity does not match the vendor invoice.",
            "An incorrect goods receipt is preventing invoice processing.",
        ],
        "resolution": [
            "The goods receipt was corrected and invoice processing resumed.",
            "The received quantity was updated after confirmation from the responsible team.",
            "The missing goods receipt was created and the invoice moved forward.",
        ],
    },
    # --------------------------------------------------------
    # FINANCE PERIOD CLOSE
    # --------------------------------------------------------
    {
        "module": "Finance Controlling",
        "category": "Period Close",
        "issue_type": "Interface Failure",
        "titles": [
            "ERP finance interface failed during period close",
            "Finance interface processing failed",
            "ERP to finance interface error",
            "Period close interface requires investigation",
        ],
        "descriptions": [
            "An ERP-to-finance interface failed during the period close process.",
            "The finance interface returned an error and affected transactions were not posted.",
            "An interface failure is preventing completion of period close activities.",
            "The period close process identified a failed financial interface.",
        ],
        "resolution": [
            "The interface error was investigated and the affected transactions were successfully processed.",
            "The failed interface was corrected and the transaction range was reconciled.",
            "The interface issue was resolved and period close processing continued.",
        ],
    },
    {
        "module": "Finance Controlling",
        "category": "Period Close",
        "issue_type": "Reconciliation Issue",
        "titles": [
            "Sub-ledger and general ledger reconciliation mismatch",
            "Finance reconciliation mismatch",
            "Unposted transactions identified during period close",
            "Period close reconciliation issue",
        ],
        "descriptions": [
            "A mismatch was identified during sub-ledger and general-ledger reconciliation.",
            "Unposted transactions were identified during the finance period close.",
            "The reconciliation process identified transactions requiring investigation.",
            "Finance period close cannot be completed until the reconciliation issue is resolved.",
        ],
        "resolution": [
            "The affected transactions were reviewed and reconciliation was completed.",
            "The unposted transactions were processed and the ledger balances were reconciled.",
            "The reconciliation discrepancy was investigated and resolved.",
        ],
    },
    # --------------------------------------------------------
    # ACCESS / SECURITY
    # --------------------------------------------------------
    {
        "module": "Finance Systems & Information Security",
        "category": "Access Management",
        "issue_type": "Access Issue",
        "titles": [
            "User unable to access finance module",
            "Finance system access denied",
            "User role does not provide required access",
            "ERP finance permission issue",
        ],
        "descriptions": [
            "A user is unable to access the required finance system module.",
            "The user receives an access denied message when opening the finance module.",
            "The assigned role does not provide the expected permission.",
            "A recent role change appears to have affected finance system access.",
        ],
        "resolution": [
            "The user's role and required permissions were reviewed and corrected.",
            "The access configuration was corrected after verifying the user's authorization.",
            "The required permission was assigned following the approved access process.",
        ],
    },
]


# ============================================================
# RANDOM DATA HELPERS
# ============================================================

SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

PRIORITIES = ["LOW", "MEDIUM", "HIGH", "URGENT"]

STATUS_WEIGHTS = [
    ("OPEN", 15),
    ("IN_PROGRESS", 20),
    ("PENDING", 10),
    ("RESOLVED", 35),
    ("CLOSED", 20),
]


def weighted_status():
    values = []

    for status, weight in STATUS_WEIGHTS:
        values.extend([status] * weight)

    return random.choice(values)


def random_date():

    # Historical tickets distributed across approximately
    # the previous 12 months.

    today = datetime.now()

    days_back = random.randint(1, 365)

    date_value = today - timedelta(days=days_back)

    hour = random.randint(8, 18)
    minute = random.randint(0, 59)

    return date_value.replace(hour=hour, minute=minute, second=0, microsecond=0)


def get_department_id(cursor, department_code):

    cursor.execute(
        """
        SELECT department_id
        FROM departments
        WHERE department_code = ?
    """,
        (department_code,),
    )

    row = cursor.fetchone()

    if row:
        return row["department_id"]

    return None


def get_users_by_department(cursor, department_id):

    cursor.execute(
        """
        SELECT employee_id
        FROM users
        WHERE department_id = ?
        AND is_active = 1
    """,
        (department_id,),
    )

    return [row["employee_id"] for row in cursor.fetchall()]


# ============================================================
# CREATE TICKET CODE
# ============================================================


def generate_ticket_code(number):

    return f"BP-2026-{number:06d}"


# ============================================================
# SEED TICKETS
# ============================================================


def seed_tickets():

    connection = get_connection()
    cursor = connection.cursor()

    # --------------------------------------------------------
    # Get departments
    # --------------------------------------------------------

    department_map = {}

    cursor.execute("""
        SELECT department_id, department_code
        FROM departments
    """)

    for row in cursor.fetchall():
        department_map[row["department_code"]] = row["department_id"]

    # --------------------------------------------------------
    # Get users
    # --------------------------------------------------------

    cursor.execute("""
        SELECT employee_id, department_id
        FROM users
        WHERE is_active = 1
    """)

    all_users = cursor.fetchall()

    if not all_users:
        connection.close()
        raise ValueError("No users found. Seed users before creating tickets.")

    users_by_department = {}

    for user in all_users:

        department_id = user["department_id"]

        if department_id not in users_by_department:
            users_by_department[department_id] = []

        users_by_department[department_id].append(user["employee_id"])

    # --------------------------------------------------------
    # Generate tickets
    # --------------------------------------------------------

    tickets = []

    for ticket_number in range(1, TICKET_COUNT + 1):

        scenario = random.choice(TICKET_SCENARIOS)

        module = scenario["module"]

        # ----------------------------------------------------
        # Map module to department
        # ----------------------------------------------------

        module_department_map = {
            "Payroll": "FIN",
            "Employee Banking": "FIN",
            "Accounts Payable": "FIN",
            "Vendor Payments": "FIN",
            "Expense Reimbursement": "FIN",
            "Finance Controlling": "FIN",
            "Procurement": "PRC",
            "Finance Systems & Information Security": "IT",
        }

        department_code = module_department_map.get(module, "SYS")

        department_id = department_map.get(department_code)

        if department_id is None:
            continue

        department_users = users_by_department.get(department_id, [])

        if not department_users:
            continue

        # ----------------------------------------------------
        # Create user
        # ----------------------------------------------------

        created_by = random.choice(department_users)

        # ----------------------------------------------------
        # Assigned user
        # ----------------------------------------------------

        assigned_to = None

        if random.random() < 0.85:
            assigned_to = random.choice(department_users)

        # ----------------------------------------------------
        # Status
        # ----------------------------------------------------

        status = weighted_status()

        # ----------------------------------------------------
        # Priority / Severity
        # ----------------------------------------------------

        severity = random.choice(SEVERITIES)

        priority = random.choice(PRIORITIES)

        # Critical issues should normally have
        # higher priority.

        if severity == "CRITICAL":
            priority = random.choice(["HIGH", "URGENT"])

        # ----------------------------------------------------
        # Dates
        # ----------------------------------------------------

        created_at = random_date()

        updated_at = created_at + timedelta(hours=random.randint(1, 96))

        assigned_at = None

        if assigned_to:
            assigned_at = created_at + timedelta(hours=random.randint(1, 12))

        resolved_at = None
        closed_at = None

        if status in ["RESOLVED", "CLOSED"]:

            resolved_at = created_at + timedelta(hours=random.randint(4, 120))

            if status == "CLOSED":

                closed_at = resolved_at + timedelta(hours=random.randint(2, 48))

        # ----------------------------------------------------
        # Resolution
        # ----------------------------------------------------

        resolution = None
        resolution_notes = None

        if status in ["RESOLVED", "CLOSED"]:

            resolution = random.choice(scenario["resolution"])

            resolution_notes = (
                "Issue investigated and resolution " "was applied after validation."
            )

        # ----------------------------------------------------
        # Embedding status
        # ----------------------------------------------------

        embedding_status = "COMPLETED"

        if random.random() < 0.08:
            embedding_status = "PENDING"

        last_embedded_at = None

        embedding_version = None

        if embedding_status == "COMPLETED":

            last_embedded_at = (
                updated_at - timedelta(minutes=random.randint(5, 1440))
            ).strftime("%Y-%m-%d %H:%M:%S")

            embedding_version = "v1"

        # ----------------------------------------------------
        # AI-created ticket
        # ----------------------------------------------------

        created_by_ai = 0

        if random.random() < 0.10:
            created_by_ai = 1

        # ----------------------------------------------------
        # Ticket text
        # ----------------------------------------------------

        title = random.choice(scenario["titles"])

        description = random.choice(scenario["descriptions"])

        ticket_code = generate_ticket_code(ticket_number)

        tickets.append(
            (
                ticket_code,
                title,
                description,
                created_by,
                assigned_to,
                department_id,
                module,
                scenario["category"],
                scenario["issue_type"],
                severity,
                priority,
                status,
                resolution,
                resolution_notes,
                created_at.strftime("%Y-%m-%d %H:%M:%S"),
                updated_at.strftime("%Y-%m-%d %H:%M:%S"),
                (assigned_at.strftime("%Y-%m-%d %H:%M:%S") if assigned_at else None),
                (resolved_at.strftime("%Y-%m-%d %H:%M:%S") if resolved_at else None),
                (closed_at.strftime("%Y-%m-%d %H:%M:%S") if closed_at else None),
                embedding_status,
                last_embedded_at,
                embedding_version,
                created_by_ai,
            )
        )

    # --------------------------------------------------------
    # Insert tickets
    # --------------------------------------------------------

    cursor.executemany(
        """
        INSERT OR IGNORE INTO tickets (
            ticket_code,
            title,
            description,
            created_by,
            assigned_to,
            department_id,
            module,
            category,
            issue_type,
            severity,
            priority,
            status,
            resolution,
            resolution_notes,
            created_at,
            updated_at,
            assigned_at,
            resolved_at,
            closed_at,
            embedding_status,
            last_embedded_at,
            embedding_version,
            created_by_ai
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
    """,
        tickets,
    )

    connection.commit()
    connection.close()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    seed_tickets()
    print("Historical tickets seeded successfully.")
