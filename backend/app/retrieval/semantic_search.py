from app.vectorstore.chroma_store import search_tickets


def semantic_search(query: str, k: int = 5) -> list[dict]:
    """
    Find historically similar tickets using semantic similarity.

    Returns the document, metadata, and Chroma distance
    for each retrieved ticket.
    """

    # ============================================================
    # INPUT VALIDATION
    # ============================================================

    if not isinstance(query, str) or not query.strip():
        raise ValueError("Semantic search query must be a non-empty string.")

    if not isinstance(k, int) or isinstance(k, bool) or k <= 0:
        raise ValueError("The number of semantic search results (k) must be a positive integer.")

    # ============================================================
    # CHROMA SEARCH
    # ============================================================

    results = search_tickets(
        query=query.strip(),
        k=k,
    )

    if not results:
        return []

    # ============================================================
    # EXTRACT CHROMA RESULTS
    # ============================================================

    documents = results.get("documents") or [[]]
    metadatas = results.get("metadatas") or [[]]
    distances = results.get("distances") or [[]]

    documents = documents[0] if documents else []
    metadatas = metadatas[0] if metadatas else []
    distances = distances[0] if distances else []

    # ============================================================
    # NORMALIZE RESULT LENGTHS
    # ============================================================

    result_count = min(
        len(documents),
        len(metadatas),
        len(distances),
    )

    matches = []

    # ============================================================
    # BUILD STANDARDIZED RESULTS
    # ============================================================

    for index in range(result_count):

        document = documents[index]
        metadata = metadatas[index]
        distance = distances[index]

        if document is None:
            document = ""

        if metadata is None:
            metadata = {}

        # Normalize distance so downstream code receives
        # either a float or None.

        if distance is not None:

            try:
                distance = float(distance)

            except (TypeError, ValueError):
                distance = None

        matches.append(
            {
                "document": str(document),
                "metadata": dict(metadata),
                "distance": distance,
            }
        )

    return matches
