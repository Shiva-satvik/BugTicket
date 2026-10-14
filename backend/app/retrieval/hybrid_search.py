from app.retrieval.keyword_search import keyword_search
from app.retrieval.semantic_search import semantic_search


def hybrid_search(query: str, k: int = 5) -> list[dict]:
    """
    Combine keyword and semantic search results.

    The hybrid score is based on rank from both retrieval methods.

    Semantic distance is preserved separately because downstream
    components such as the Confidence Agent may use it as
    supporting evidence.

    Returns:
        A list of the top-k combined historical ticket results.
    """

    # ============================================================
    # INPUT VALIDATION
    # ============================================================

    if not query or not query.strip():
        raise ValueError("Hybrid search cannot be performed with an empty query.")

    if k <= 0:
        raise ValueError("The number of search results (k) must be greater than 0.")

    query = query.strip()

    # ============================================================
    # RUN BOTH RETRIEVAL METHODS
    # ============================================================

    keyword_results = keyword_search(
        query=query,
        k=k,
    )

    semantic_results = semantic_search(
        query=query,
        k=k,
    )

    combined = {}

    # ============================================================
    # KEYWORD SEARCH RESULTS
    # ============================================================

    for rank, result in enumerate(
        keyword_results or [],
        start=0,
    ):

        if not isinstance(result, dict):
            continue

        ticket_code = str(
            result.get(
                "ticket_code",
                "",
            )
        ).strip()

        if not ticket_code:
            continue

        if ticket_code not in combined:

            combined[ticket_code] = {
                "ticket_code": ticket_code,
                "keyword_score": 0,
                "semantic_score": 0,
                "semantic_distance": None,
                "document": None,
                "metadata": {},
            }

        # --------------------------------------------------------
        # Rank-based keyword score
        # --------------------------------------------------------

        combined[ticket_code]["keyword_score"] = k - rank

        # --------------------------------------------------------
        # Build document from keyword result
        # --------------------------------------------------------

        title = str(
            result.get(
                "title",
                "Not available",
            )
        ).strip()

        description = str(
            result.get(
                "description",
                "Not available",
            )
        ).strip()

        module = str(
            result.get(
                "module",
                "Not specified",
            )
        ).strip()

        category = str(
            result.get(
                "category",
                "Not specified",
            )
        ).strip()

        severity = str(
            result.get(
                "severity",
                "Not specified",
            )
        ).strip()

        status = str(
            result.get(
                "status",
                "Not specified",
            )
        ).strip()

        resolution = str(
            result.get(
                "resolution",
                "Not available",
            )
        ).strip()

        combined[ticket_code]["document"] = (
            f"Title: {title}\n\n"
            f"Description: {description}\n\n"
            f"Module: {module}\n\n"
            f"Category: {category}\n\n"
            f"Severity: {severity}\n\n"
            f"Status: {status}\n\n"
            f"Resolution: {resolution}"
        )

        # --------------------------------------------------------
        # Metadata
        # --------------------------------------------------------

        combined[ticket_code]["metadata"] = {
            "ticket_id": result.get("ticket_id"),
            "ticket_code": ticket_code,
            "module": module,
            "category": category,
            "severity": severity,
            "status": status,
        }

    # ============================================================
    # SEMANTIC SEARCH RESULTS
    # ============================================================

    for rank, result in enumerate(
        semantic_results or [],
        start=0,
    ):

        if not isinstance(result, dict):
            continue

        metadata = result.get("metadata") or {}

        ticket_code = str(
            metadata.get(
                "ticket_code",
                result.get(
                    "ticket_code",
                    "",
                ),
            )
        ).strip()

        if not ticket_code:
            continue

        if ticket_code not in combined:

            combined[ticket_code] = {
                "ticket_code": ticket_code,
                "keyword_score": 0,
                "semantic_score": 0,
                "semantic_distance": None,
                "document": None,
                "metadata": {},
            }

        # --------------------------------------------------------
        # Rank-based semantic score
        # --------------------------------------------------------

        combined[ticket_code]["semantic_score"] = k - rank

        # --------------------------------------------------------
        # Preserve actual semantic distance
        # --------------------------------------------------------

        distance = result.get("distance")

        if distance is not None:

            try:
                distance = float(distance)

            except (TypeError, ValueError):
                distance = None

        combined[ticket_code]["semantic_distance"] = distance

        # --------------------------------------------------------
        # Preserve semantic document
        # --------------------------------------------------------

        semantic_document = str(
            result.get(
                "document",
                "",
            )
        ).strip()

        if combined[ticket_code]["document"] is None and semantic_document:

            combined[ticket_code]["document"] = semantic_document

        # --------------------------------------------------------
        # Preserve metadata
        # --------------------------------------------------------

        if not combined[ticket_code]["metadata"]:

            combined[ticket_code]["metadata"] = dict(metadata)

        else:

            # Fill missing metadata without overwriting
            # information already obtained from keyword search.

            existing_metadata = combined[ticket_code]["metadata"]

            for key, value in metadata.items():

                if (
                    key not in existing_metadata
                    or existing_metadata[key] is None
                    or existing_metadata[key] == ""
                ):
                    existing_metadata[key] = value

    # ============================================================
    # COMBINE RESULTS
    # ============================================================

    results = []

    for ticket in combined.values():

        keyword_score = ticket.get(
            "keyword_score",
            0,
        )

        semantic_score = ticket.get(
            "semantic_score",
            0,
        )

        hybrid_score = keyword_score + semantic_score

        ticket["hybrid_score"] = hybrid_score

        # Make sure downstream code always receives
        # a metadata dictionary.

        if not ticket.get("metadata"):
            ticket["metadata"] = {"ticket_code": ticket["ticket_code"]}

        # Make sure the document is never None.

        if ticket.get("document") is None:

            ticket["document"] = "Historical ticket details " "are not available."

        results.append(ticket)

    # ============================================================
    # SORT BY HYBRID SCORE
    # ============================================================

    results.sort(
        key=lambda item: item.get(
            "hybrid_score",
            0,
        ),
        reverse=True,
    )

    # ============================================================
    # RETURN TOP-K RESULTS
    # ============================================================

    return results[:k]
