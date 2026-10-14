from app.database.connection import get_connection

# ============================================================
# FINANCIAL DOCUMENTS / SOP KNOWLEDGE BASE
# ============================================================

FINANCIAL_DOCUMENTS = [
    {
        "document_code": "FD-001",
        "title": "Payroll Processing Standard Operating Procedure",
        "document_type": "SOP",
        "module": "Payroll",
        "version": "2.1",
        "source": "Finance & Payroll",
        "content": """
Purpose:
Defines the controlled process for monthly payroll preparation,
validation, approval, processing, and reconciliation.

Payroll Calendar:
1. Payroll inputs freeze on the 20th unless Finance approves an exception.
2. Calculation occurs between the 21st and 24th.
3. Validation and exception review must finish before submission.
4. Normal salary processing targets the last working day.

Required Validation:
Validate active status, bank details, salary components, deductions,
attendance, leave, joiners, exits, duplicates, and unexpected net salary values.

Payroll Batch Failure:
Do not manually mark a failed batch complete.
Capture batch ID and error, identify failed records, correct the cause,
validate, rerun, and reconcile the successful batch.

Salary Not Credited:
Verify successful payroll inclusion, masked bank details,
bank response/reconciliation status, and whether payment was rejected,
pending, or reversed.

Do not store full bank numbers in support tickets.

Controls:
Payroll changes must be traceable to user and timestamp.
Manual adjustments require an approved reason and evidence.
""",
    },
    {
        "document_code": "FD-002",
        "title": "Employee Bank Account Change and Validation Policy",
        "document_type": "Policy",
        "module": "Employee Banking",
        "version": "1.4",
        "source": "Finance & HR",
        "content": """
Purpose:
Controls employee bank-account updates used for salary payments.

Change Request:
Bank changes must originate from an authenticated employee or HR workflow
and be reviewed before payroll cutoff.

Validation:
Validate required fields, bank identifiers, employee association where
supported, duplicate or conflicting details, and effective date.

Payroll Cutoff:
Changes after payroll input freeze normally apply to the next cycle unless
an authorized exception is approved.

Failed Validation:
A failed validation must remain in exception state until corrected.
It must not be silently accepted.

Security:
Never place full bank numbers, passwords, OTPs, card data,
or authentication tokens in tickets or logs.

Use masked identifiers.
""",
    },
    {
        "document_code": "FD-003",
        "title": "Vendor Invoice Processing SOP",
        "document_type": "SOP",
        "module": "Accounts Payable",
        "version": "3.0",
        "source": "Accounts Payable",
        "content": """
Invoice Validation:
Validate vendor, purchase order, invoice number and date, tax,
quantity, unit price, total, duplicate invoice number,
and required approval.

Amount Mismatch:
Place the invoice in exception status.
Do not release payment.

Compare quantity, unit price, tax, discount, and freight.
Obtain clarification or approval.

Duplicate Invoice:
Potential duplicates must be held for review before creating
a second payable.

Posting Failure:
Capture invoice ID, posting period, error message, and affected entity.
Retry only after correcting the cause.
""",
    },
    {
        "document_code": "FD-004",
        "title": "Vendor Payment Processing SOP",
        "document_type": "SOP",
        "module": "Vendor Payments",
        "version": "2.2",
        "source": "Treasury & Accounts Payable",
        "content": """
Pre-Payment Checks:
Verify that the invoice is approved, the vendor is active,
beneficiary details are validated, there is no blocking exception,
and the payment amount matches the approved payable.

Failed Payment:
Record payment batch and bank response code.

Determine whether the failure is caused by:
- beneficiary data
- bank rejection
- authorization
- technical processing

Correct the cause, revalidate, and reprocess.

Duplicate Payment Prevention:
Never reprocess only because a user reports non-receipt.

First verify payment status and bank reconciliation.
""",
    },
    {
        "document_code": "FD-005",
        "title": "Employee Expense Reimbursement Policy",
        "document_type": "Policy",
        "module": "Expense Reimbursement",
        "version": "2.0",
        "source": "Finance",
        "content": """
Eligible business expenses require:
- date
- purpose
- category
- amount/currency
- supporting receipt where required

Claims require designated manager approval and may require
Finance review.

Rejections must contain a reason.

Common rejection reasons include:
- missing receipt
- unsupported category
- duplicate claim
- policy limit exceeded
- missing approval

Approved claims enter the next eligible reimbursement run.

Employees should not submit duplicates while a payment is pending.
""",
    },
    {
        "document_code": "FD-006",
        "title": "Purchase Order and Goods Receipt Policy",
        "document_type": "Policy",
        "module": "Procurement",
        "version": "1.8",
        "source": "Procurement & Finance",
        "content": """
Where applicable, invoices are checked against:

- Purchase Order
- Goods Receipt or Service Confirmation
- Vendor Invoice

If invoiced quantity exceeds accepted receipt quantity,
enter exception handling.

If invoice unit price differs from approved PO price,
block payment until reviewed.

Missing or incorrect goods receipts must be corrected before
Finance releases the invoice.
""",
    },
    {
        "document_code": "FD-007",
        "title": "Finance Period Close SOP",
        "document_type": "SOP",
        "module": "Finance Controlling",
        "version": "2.5",
        "source": "Finance Controlling",
        "content": """
Close activities include:

- posting completeness
- failed interfaces
- unposted transactions
- sub-ledger/general-ledger reconciliation
- open exceptions
- approved adjustments

Every failed ERP-to-finance interface must be investigated before close.

Capture:
- interface name
- run ID
- timestamp
- error code
- affected transaction range

Late postings require authorization and traceability through
the close-exception process.
""",
    },
    {
        "document_code": "FD-008",
        "title": "Financial Data Access and Audit Policy",
        "document_type": "Policy",
        "module": "Finance Systems & Information Security",
        "version": "1.9",
        "source": "Finance Systems & Information Security",
        "content": """
Least Privilege:
Users receive only financial-system access required for their responsibilities.

Audit Trail:
Create, update, approval, cancellation, and payment actions must be
attributable to an authenticated user.

Sensitive Data:
Tickets and logs must not contain:
- full bank numbers
- passwords
- OTPs
- card information
- authentication tokens
- unnecessary personal data

Access Issues:
Confirm:
- role
- required permission
- approval
- recent role changes

Escalate inconsistencies.

Audit Requests:
Never modify or delete audit records to resolve a ticket.
Preserve evidence and follow the approved audit process.
""",
    },
]


# ============================================================
# SEED FINANCIAL DOCUMENTS
# ============================================================


def seed_financial_documents():

    connection = get_connection()
    cursor = connection.cursor()

    for document in FINANCIAL_DOCUMENTS:

        cursor.execute(
            """
            INSERT OR IGNORE INTO financial_documents (
                document_code,
                title,
                document_type,
                module,
                content,
                source,
                version,
                is_active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        """,
            (
                document["document_code"],
                document["title"],
                document["document_type"],
                document["module"],
                document["content"].strip(),
                document["source"],
                document["version"],
            ),
        )

    connection.commit()
    connection.close()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    seed_financial_documents()
    print("Financial documents seeded successfully.")
