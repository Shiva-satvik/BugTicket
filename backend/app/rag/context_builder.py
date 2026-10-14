import re
import sqlite3
from pathlib import Path
from app.database.connection import DATABASE_PATH
from app.retrieval.keyword_search import keyword_search

STOP_WORDS = {
    "the", "and", "for", "with", "from", "that", "this", "when", "what", "where",
    "into", "have", "has", "was", "were", "are", "been", "being", "after", "before",
    "user", "users", "issue", "ticket", "error", "please", "unable", "cannot", "could",
    "would", "should", "will", "does", "not", "but", "their", "they", "them", "about",
}


def _terms(text: str) -> list[str]:
    return [w for w in dict.fromkeys(re.findall(r"[a-zA-Z0-9]+", (text or "").lower())) if len(w) > 2 and w not in STOP_WORDS]


def _financial_documents(query: str, related_ticket_ids: list[int], limit: int = 4) -> list[dict]:
    """Retrieve active finance SOPs/policies using lexical relevance and existing ticket-document links."""
    terms = _terms(query)
    connection = sqlite3.connect(str(DATABASE_PATH), timeout=20)
    connection.row_factory = sqlite3.Row
    try:
        docs = [dict(row) for row in connection.execute(
            "SELECT document_id, document_code, title, document_type, module, content, source, version "
            "FROM financial_documents WHERE is_active = 1"
        ).fetchall()]
        linked_scores = {}
        if related_ticket_ids:
            placeholders = ",".join("?" for _ in related_ticket_ids)
            rows = connection.execute(
                f"SELECT document_id, MAX(COALESCE(relevance_score, 0)) AS score FROM ticket_documents "
                f"WHERE ticket_id IN ({placeholders}) GROUP BY document_id", related_ticket_ids
            ).fetchall()
            linked_scores = {int(row["document_id"]): float(row["score"] or 0) for row in rows}
        ranked = []
        for doc in docs:
            title = (doc.get("title") or "").lower()
            module = (doc.get("module") or "").lower()
            content = (doc.get("content") or "").lower()
            code = (doc.get("document_code") or "").lower()
            title_hits = sum(1 for term in terms if term in title)
            module_hits = sum(1 for term in terms if term in module)
            content_hits = sum(1 for term in terms if term in content)
            linked = linked_scores.get(int(doc["document_id"]), 0.0)
            score = title_hits * 3 + module_hits * 2 + content_hits + linked * 2
            if score > 0:
                doc["retrieval_score"] = round(score, 3)
                doc["linked_ticket_score"] = linked
                ranked.append(doc)
        ranked.sort(key=lambda d: (d["retrieval_score"], d.get("version") or ""), reverse=True)
        return ranked[:limit]
    finally:
        connection.close()


def build_rag_context_with_diagnostics(query: str, k: int = 5) -> tuple[str, dict]:
    """Retrieve historical tickets and finance documents; keep partial retrieval alive if Chroma is unavailable."""
    if not query or not query.strip():
        raise ValueError("RAG context cannot be built from an empty query.")
    if k <= 0:
        raise ValueError("k must be greater than zero.")

    keyword_results, semantic_results = [], []
    keyword_error = semantic_error = None
    try:
        keyword_results = keyword_search(query.strip(), k=k) or []
    except Exception as exc:
        keyword_error = f"{type(exc).__name__}: {exc}"
    try:
        # Import lazily so keyword + financial-document retrieval still works
        # if the optional Chroma/embedding dependencies are unavailable.
        from app.retrieval.semantic_search import semantic_search
        semantic_results = semantic_search(query.strip(), k=k) or []
    except Exception as exc:
        semantic_error = f"{type(exc).__name__}: {exc}"

    combined = {}
    for rank, row in enumerate(keyword_results):
        code = str(row.get("ticket_code") or "").strip()
        if not code:
            continue
        combined.setdefault(code, {"ticket_code": code, "ticket_id": row.get("ticket_id"), "document": "", "metadata": {}, "keyword_rank": None, "semantic_rank": None, "semantic_distance": None})
        item = combined[code]
        item["keyword_rank"] = rank + 1
        item["document"] = (
            f"Title: {row.get('title') or ''}\nDescription: {row.get('description') or ''}\n"
            f"Module: {row.get('module') or ''}\nCategory: {row.get('category') or ''}\n"
            f"Severity: {row.get('severity') or ''}\nStatus: {row.get('status') or ''}\n"
            f"Resolution: {row.get('resolution') or 'No recorded resolution.'}"
        )
        item["metadata"] = {"ticket_id": row.get("ticket_id"), "ticket_code": code, "module": row.get("module") or "", "category": row.get("category") or "", "severity": row.get("severity") or "", "status": row.get("status") or ""}
    for rank, row in enumerate(semantic_results):
        meta = row.get("metadata") or {}
        code = str(meta.get("ticket_code") or row.get("ticket_code") or "").strip()
        if not code:
            continue
        combined.setdefault(code, {"ticket_code": code, "ticket_id": meta.get("ticket_id"), "document": "", "metadata": dict(meta), "keyword_rank": None, "semantic_rank": None, "semantic_distance": None})
        item = combined[code]
        item["semantic_rank"] = rank + 1
        item["semantic_distance"] = row.get("distance")
        if row.get("document") and (not item.get("document") or item.get("document") == "Historical ticket details are not available."):
            item["document"] = str(row["document"])
        if not item.get("metadata"):
            item["metadata"] = dict(meta)

    for item in combined.values():
        # Reciprocal-rank fusion: combines both sources without pretending the ranks are calibrated probabilities.
        item["hybrid_score"] = (1 / (60 + item["keyword_rank"]) if item["keyword_rank"] else 0) + (1 / (60 + item["semantic_rank"]) if item["semantic_rank"] else 0)
    tickets = sorted(combined.values(), key=lambda x: x["hybrid_score"], reverse=True)[:k]
    ticket_blocks = []
    for i, item in enumerate(tickets, 1):
        meta = item.get("metadata") or {}
        distance = item.get("semantic_distance")
        ticket_blocks.append(
            f"HISTORICAL TICKET {i}\nTicket Code: {item['ticket_code']}\n"
            f"Ticket ID: {item.get('ticket_id') or meta.get('ticket_id') or 'Unknown'}\n"
            f"Module: {meta.get('module') or 'Not specified'}\nCategory: {meta.get('category') or 'Not specified'}\n"
            f"Severity: {meta.get('severity') or 'Not specified'}\nStatus: {meta.get('status') or 'Not specified'}\n"
            f"Semantic Distance: {distance if distance is not None else 'Not available'}\n"
            f"Retrieved By: {', '.join(x for x, yes in [('keyword', bool(item.get('keyword_rank'))), ('semantic', bool(item.get('semantic_rank')))] if yes)}\n"
            f"Details and resolution:\n{item.get('document') or 'Historical ticket details are unavailable.'}"
        )
    related_ids = []
    for item in tickets:
        try:
            related_ids.append(int(item.get("ticket_id") or item.get("metadata", {}).get("ticket_id")))
        except (TypeError, ValueError):
            pass
    document_error = None
    try:
        documents = _financial_documents(query, related_ids, limit=4)
    except Exception as exc:
        documents = []
        document_error = f"{type(exc).__name__}: {exc}"
    document_blocks = []
    for i, doc in enumerate(documents, 1):
        document_blocks.append(
            f"FINANCIAL DOCUMENT {i}\nDocument Code: {doc.get('document_code')}\n"
            f"Title: {doc.get('title')}\nType: {doc.get('document_type') or 'Document'}\n"
            f"Module: {doc.get('module') or 'Not specified'}\nSource: {doc.get('source') or 'Not specified'}\n"
            f"Version: {doc.get('version') or 'Not specified'}\n"
            f"Retrieved Relevance: {doc.get('retrieval_score')}\nContent:\n{doc.get('content') or ''}"
        )
    sections = []
    if ticket_blocks:
        sections.append("RETRIEVED HISTORICAL TICKETS\n\n" + ("\n\n" + "=" * 70 + "\n\n").join(ticket_blocks))
    else:
        sections.append("RETRIEVED HISTORICAL TICKETS\nNo matching historical tickets were retrieved.")
    if document_blocks:
        sections.append("RETRIEVED FINANCIAL SOPs AND POLICIES\n\n" + "\n\n".join(document_blocks))
    else:
        sections.append("RETRIEVED FINANCIAL SOPs AND POLICIES\nNo relevant active financial document matched this query or its retrieved tickets.")
    vector_count = None
    try:
        from app.vectorstore.chroma_store import get_collection_count
        vector_count = int(get_collection_count())
    except Exception:
        pass
    semantic_status = "failed" if semantic_error else ("empty" if vector_count == 0 else "ok")
    if semantic_status == "empty" and not semantic_error:
        semantic_error = "Chroma collection is empty. Run `python -m app.vectorstore.index_tickets` to index historical tickets."
    diagnostics = {
        "ticket_count": len(tickets),
        "vector_count": vector_count,
        "ticket_sources": [{"ticket_code": x["ticket_code"], "module": (x.get("metadata") or {}).get("module", ""), "category": (x.get("metadata") or {}).get("category", ""), "retrieved_by": [name for name, yes in [("keyword", bool(x.get("keyword_rank"))), ("semantic", bool(x.get("semantic_rank")))] if yes], "semantic_distance": x.get("semantic_distance")} for x in tickets],
        "financial_document_count": len(documents),
        "financial_document_sources": [{"document_code": d.get("document_code"), "title": d.get("title"), "module": d.get("module"), "source": d.get("source"), "version": d.get("version")} for d in documents],
        "keyword_search": "ok" if keyword_error is None else "failed",
        "semantic_search": semantic_status,
        "financial_document_search": "ok" if document_error is None else "failed",
        "keyword_error": keyword_error,
        "semantic_error": semantic_error,
        "financial_document_error": document_error,
    }
    return "\n\n".join(sections), diagnostics


def build_rag_context(query: str, k: int = 5) -> str:
    """Backward-compatible context-only interface used by the standalone RAG utility."""
    return build_rag_context_with_diagnostics(query, k)[0]
