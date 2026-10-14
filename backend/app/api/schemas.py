from typing import Any
from pydantic import BaseModel, Field

# ============================================================
# REQUEST
# ============================================================


class TicketRequest(BaseModel):
    """
    Request body for submitting a software bug or ERP issue.
    """

    ticket: str = Field(
        ...,
        min_length=5,
        description=("Software bug or issue reported by the user."),
    )


# ============================================================
# ANALYSIS RESPONSE
# ============================================================


class TicketAnalysisResponse(BaseModel):
    """
    Complete BugPilot analysis returned after processing
    a ticket.
    """

    id: int

    ticket: str

    summary: str

    category: str

    module: str

    problem: str

    keywords: list[str]

    analysis: str

    historical_evidence: str

    severity: str

    priority: str

    likely_cause: str

    suggested_resolution: str

    missing_information: list[str]

    confidence_score: float = Field(
        ...,
        ge=0,
        le=100,
        description="BugPilot confidence percentage.",
    )

    confidence_level: str = Field(
        ...,
        description="Confidence level: Low, Medium, or High.",
    )

    confidence_reason: str
    retrieval_diagnostics: dict[str, Any] = Field(default_factory=dict)
    llm_status: str = "unknown"
    llm_error: str = ""
    analysis_mode: str = "unknown"


# ============================================================
# TICKET HISTORY ITEM
# ============================================================


class TicketHistoryItem(BaseModel):
    """
    Lightweight representation used for ticket history.
    """

    id: int

    ticket: str

    summary: str

    category: str

    module: str

    severity: str

    priority: str

    confidence_score: float = Field(
        ...,
        ge=0,
        le=100,
    )

    confidence_level: str

    created_at: str


# ============================================================
# TICKET HISTORY RESPONSE
# ============================================================


class TicketHistoryResponse(BaseModel):
    """
    Response containing previously analyzed tickets.
    """

    count: int = Field(
        ...,
        ge=0,
    )

    tickets: list[TicketHistoryItem]
