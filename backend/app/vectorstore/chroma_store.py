
from pathlib import Path
from typing import Any

import chromadb

from app.embeddings.embedding_model import (
    create_embedding,
    create_embeddings,
)

# --------------------------------------------------
# Configuration
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHROMA_PATH = PROJECT_ROOT / "vector_db"
COLLECTION_NAME = "bug_tickets"

CHROMA_PATH.mkdir(parents=True, exist_ok=True)

client = chromadb.PersistentClient(path=str(CHROMA_PATH))

collection = client.get_or_create_collection(
    name=COLLECTION_NAME,
    metadata={"hnsw:space": "cosine"},
)


# --------------------------------------------------
# Validation
# --------------------------------------------------

def _validate_batch(
    ids: list[str],
    documents: list[str],
    metadatas: list[dict[str, Any]],
) -> None:
    if not ids:
        raise ValueError("At least one ticket ID is required.")

    if not (len(ids) == len(documents) == len(metadatas)):
        raise ValueError(
            "IDs, documents, and metadata must have equal lengths."
        )

    if any(not str(value).strip() for value in ids):
        raise ValueError("Ticket IDs cannot be empty.")

    if len(set(str(value).strip() for value in ids)) != len(ids):
        raise ValueError("Duplicate ticket IDs are not allowed.")

    if any(
        not isinstance(document, str) or not document.strip()
        for document in documents
    ):
        raise ValueError("Documents must be non-empty strings.")

    if any(not isinstance(metadata, dict) for metadata in metadatas):
        raise ValueError("Every metadata item must be a dictionary.")


# --------------------------------------------------
# Insert or update multiple tickets
# --------------------------------------------------

def add_tickets(
    ids: list[str],
    documents: list[str],
    metadatas: list[dict[str, Any]],
) -> int:
    """Generate embeddings and insert or update ticket records."""
    _validate_batch(ids, documents, metadatas)

    cleaned_ids = [str(ticket_id).strip() for ticket_id in ids]
    cleaned_documents = [document.strip() for document in documents]

    cleaned_metadatas = [
        {
            str(key): value
            for key, value in metadata.items()
            if value is not None
            and isinstance(value, (str, int, float, bool))
        }
        for metadata in metadatas
    ]

    embeddings = create_embeddings(cleaned_documents)

    if not embeddings or len(embeddings) != len(cleaned_documents):
        raise ValueError(
            "Embedding generation did not return one embedding per document."
        )

    collection.upsert(
        ids=cleaned_ids,
        documents=cleaned_documents,
        embeddings=embeddings,
        metadatas=cleaned_metadatas,
    )

    return len(cleaned_ids)


# --------------------------------------------------
# Insert or update one ticket
# --------------------------------------------------

def upsert_ticket(
    ticket_id: int | str,
    document: str,
    metadata: dict[str, Any],
) -> None:
    """Insert or update one ticket's vector."""
    add_tickets(
        ids=[f"ticket_{ticket_id}"],
        documents=[document],
        metadatas=[metadata],
    )


# --------------------------------------------------
# Delete a ticket
# --------------------------------------------------

def delete_ticket(ticket_id: int | str) -> None:
    """Delete a ticket's vector from ChromaDB."""
    collection.delete(ids=[f"ticket_{ticket_id}"])


# --------------------------------------------------
# Semantic search
# --------------------------------------------------

def search_tickets(
    query: str,
    k: int = 5,
    where: dict | None = None,
) -> dict:
    """Return the most semantically similar historical tickets."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Search query cannot be empty.")

    if not isinstance(k, int) or isinstance(k, bool) or k <= 0:
        raise ValueError("k must be a positive integer.")

    total = collection.count()

    if total == 0:
        return {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }

    query_embedding = create_embedding(query.strip())

    if not query_embedding:
        raise ValueError("Query embedding generation failed.")

    options = {
        "query_embeddings": [query_embedding],
        "n_results": min(k, total),
        "include": ["documents", "metadatas", "distances"],
    }

    if where:
        options["where"] = where

    return collection.query(**options)


# --------------------------------------------------
# Collection information
# --------------------------------------------------

def get_collection_count() -> int:
    """Return the number of vectors stored in ChromaDB."""
    return collection.count()
