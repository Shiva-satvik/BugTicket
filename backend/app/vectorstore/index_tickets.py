
from app.embeddings.ticket_embedding_service import (
    DB_PATH,
    EMBEDDING_VERSION,
    ensure_tracking_columns,
    get_connection,
    sync_pending_ticket_embeddings,
)


def index_tickets(batch_limit: int = 100) -> dict:
    """
    Index existing tickets and reconcile pending or outdated embeddings.

    Processes a bounded batch per iteration and stops when no further
    successful progress can be made.
    """

    if batch_limit <= 0:
        raise ValueError("batch_limit must be greater than zero.")

    connection = get_connection()

    try:
        ensure_tracking_columns(connection)

        # A project ZIP may include SQLite rows marked embedded but not include
        # the persistent Chroma files. If Chroma is empty, re-index all source tickets.
        from app.vectorstore.chroma_store import get_collection_count
        collection_count = get_collection_count()
        if collection_count == 0:
            connection.execute("UPDATE tickets SET embedding_status = 'pending'")
        else:
            connection.execute(
                """
                UPDATE tickets
                SET embedding_status = 'pending'
                WHERE embedding_status IS NULL
                   OR embedding_status NOT IN ('embedded', 'failed')
                """
            )
        connection.commit()

    finally:
        connection.close()

    total_selected = 0
    total_succeeded = 0
    total_failed = 0
    first_batch = True

    while True:
        # Retry failed rows once during an explicit indexing run. If they fail
        # again, leave them marked failed and continue indexing other pending
        # tickets rather than repeatedly selecting the same failures forever.
        summary = sync_pending_ticket_embeddings(
            limit=batch_limit,
            retry_failed=first_batch,
        )
        first_batch = False

        selected = summary["selected"]
        succeeded = summary["succeeded"]
        failed = len(summary["failed"])

        total_selected += selected
        total_succeeded += succeeded
        total_failed += failed

        print(
            f"Batch: selected={selected}, "
            f"succeeded={succeeded}, failed={failed}"
        )

        # No remaining eligible tickets.
        if selected == 0:
            break

        # Prevent endless retries when a batch cannot make progress.
        if succeeded == 0:
            break

    result = {
        "selected": total_selected,
        "succeeded": total_succeeded,
        "failed": total_failed,
        "embedding_version": EMBEDDING_VERSION,
    }

    print("Embedding indexing summary:", result)

    return result


if __name__ == "__main__":
    index_tickets()
