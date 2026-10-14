import { useCallback, useEffect, useMemo, useState } from "react";

import { AlertCircle, Bot, Plus, RefreshCw, Search, Ticket } from "lucide-react";

import { useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { enterpriseTicketApi, errorMessage, ticketApi } from "../api/services";
import CreateTicketModal from "../components/CreateTicketModal.jsx";

import { safeArray, getTicketId, getTicketTitle, getStatus } from "../utils";

import {
  PageHeader,
  TicketTable,
  EmptyState,
  LoadingPanel,
} from "../components/Common.jsx";

export default function TicketsPage({ user }) {
  const roles = (user?.roles || []).map((role) => String(role).toUpperCase());
  const canCreate = roles.some((role) => ["ADMIN", "MANAGER", "DEVELOPER", "SUPPORT", "EMPLOYEE"].includes(role));
  const [tickets, setTickets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [searchParams, setSearchParams] = useSearchParams();
  const [query, setQuery] = useState(searchParams.get("q") || "");
  const [status, setStatus] = useState(searchParams.get("status") || "ALL");
  const [view, setView] = useState("enterprise");
  const [selected, setSelected] = useState(null);
  const [history, setHistory] = useState([]);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  async function openTicket(ticket) {
    setSelected(ticket);
    setHistory([]);
    setDetailError("");
    setDetailLoading(true);
    try {
      const id = getTicketId(ticket);
      if (view === "enterprise") {
        const [detailResult, historyResult] = await Promise.allSettled([
          enterpriseTicketApi.getById(id),
          enterpriseTicketApi.getHistory(id),
        ]);
        if (detailResult.status === "fulfilled") {
          setSelected(detailResult.value.data);
        } else {
          setDetailError(errorMessage(detailResult.reason, "Could not load ticket details."));
        }
        if (historyResult.status === "fulfilled") {
          const payload = historyResult.value.data;
          setHistory(safeArray(payload?.history ?? payload?.items ?? payload));
        }
      } else {
        const detailResult = await ticketApi.getById(id);
        setSelected(detailResult.data);
      }
    } catch (err) {
      setDetailError(errorMessage(err, "Could not load ticket details."));
    } finally {
      setDetailLoading(false);
    }
  }

  function analyzeSelected() {
    if (!selected) return;
    const ticketText = selected.description || selected.ticket || selected.problem || "";
    const ticketTitle = selected.title || selected.summary || "";
    setSelected(null);
    navigate("/ai-analysis", {
      state: { ticketText, ticketTitle },
    });
  }

  // Load tickets from the selected API
  const load = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      const response =
        view === "enterprise"
          ? await enterpriseTicketApi.getAll({
              sort_by: "created_at",
              sort_order: "desc",
            })
          : await ticketApi.getAll();

      const data = response.data;

      setTickets(safeArray(data?.tickets ?? data?.items ?? data));
    } catch (err) {
      setError(errorMessage(err, "Tickets could not be loaded."));
      setTickets([]);
    } finally {
      setLoading(false);
    }
  }, [view]);

  useEffect(() => {
    load();
  }, [load]);

  // Open a ticket passed from the dashboard's Recent tickets table.
  useEffect(() => {
    const ticketToOpen = location.state?.ticketToOpen;
    if (!loading && ticketToOpen) {
      openTicket(ticketToOpen);
      navigate(`${location.pathname}${location.search}`, {
        replace: true,
        state: null,
      });
    }
    // openTicket intentionally runs once for the navigation state, then the state is cleared.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, location.state]);

  useEffect(() => {
    setQuery(searchParams.get("q") || "");
    setStatus(searchParams.get("status") || "ALL");
  }, [searchParams]);

  function updateQuery(value) {
    setQuery(value);
    const next = new URLSearchParams(searchParams);
    if (value.trim()) next.set("q", value.trim());
    else next.delete("q");
    setSearchParams(next, { replace: true });
  }

  function updateStatus(value) {
    setStatus(value);
    const next = new URLSearchParams(searchParams);
    if (value === "ALL") next.delete("status");
    else next.set("status", value);
    setSearchParams(next, { replace: true });
  }

  // Search and filter tickets
  const filtered = useMemo(() => {
    return tickets.filter((ticket) => {
      const searchableText = [
        getTicketId(ticket),
        getTicketTitle(ticket),
        ticket?.description,
        ticket?.problem,
        ticket?.summary,
        ticket?.ticket_code,
        ticket?.category,
        ticket?.module,
        ticket?.priority,
        ticket?.severity,
        ticket?.status,
        ticket?.created_by_name,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();

      const matchesQuery = searchableText.includes(query.trim().toLowerCase());
      const normalizedStatus = String(getStatus(ticket) || "")
        .trim()
        .toUpperCase()
        .replace(/[\s-]+/g, "_");
      const matchesStatus =
        status === "ALL" ||
        normalizedStatus === status ||
        (status === "RESOLVED" && normalizedStatus === "CLOSED") ||
        (status === "OPEN" && normalizedStatus === "PENDING");

      return matchesQuery && matchesStatus;
    });
  }, [tickets, query, status]);

  return (
    <>
      <PageHeader
        eyebrow="WORK MANAGEMENT"
        title="Ticket management"
        description="Review, filter, and create ERP support tickets."
        action={canCreate ? (
          <button type="button" onClick={() => setCreateModalOpen(true)} className="button button-primary">
            <Plus size={17} />
            Create ticket
          </button>
        ) : null}
      />

      <section className="panel">
        {/* Search and filter controls */}
        <div className="ticket-toolbar">
          <div className="segmented">
            <button
              type="button"
              className={view === "enterprise" ? "segment-active" : ""}
              onClick={() => setView("enterprise")}
            >
              Enterprise tickets
            </button>

            <button
              type="button"
              className={view === "ai" ? "segment-active" : ""}
              onClick={() => setView("ai")}
            >
              AI analyses
            </button>
          </div>

          <div className="ticket-filters">
            <div className="filter-search">
              <Search size={16} />

              <input
                type="search"
                value={query}
                onChange={(event) => updateQuery(event.target.value)}
                placeholder="Search tickets"
                aria-label="Search tickets"
              />
            </div>

            <select
              aria-label="Filter tickets by status"
              value={status}
              onChange={(event) => updateStatus(event.target.value)}
            >
              <option value="ALL">All statuses</option>
              <option value="PENDING">Pending</option>
              <option value="OPEN">Open</option>
              <option value="IN_PROGRESS">In progress</option>
              <option value="RESOLVED">Resolved</option>
              <option value="CLOSED">Closed</option>
            </select>

            <button
              type="button"
              className="icon-button border-button"
              onClick={load}
              disabled={loading}
              title="Refresh tickets"
              aria-label="Refresh tickets"
            >
              <RefreshCw size={16} className={loading ? "spin" : ""} />
            </button>
          </div>
        </div>

        {/* API errors */}
        {error && (
          <div className="alert alert-warning">
            <AlertCircle size={17} />
            <span>{error}</span>
          </div>
        )}

        {/* Ticket results */}
        {loading ? (
          <LoadingPanel label="Loading tickets…" />
        ) : filtered.length > 0 ? (
          <TicketTable tickets={filtered} showDescription onView={openTicket} />
        ) : (
          <EmptyState
            icon={Ticket}
            title="No matching tickets"
            body={
              tickets.length > 0
                ? "Try another search term or status filter."
                : "There are no tickets visible to your account yet."
            }
            action={canCreate ? (
              <button type="button" className="button button-primary button-small" onClick={() => setCreateModalOpen(true)}>
                <Plus size={15} /> Create ticket
              </button>
            ) : null}
          />
        )}
      </section>

      {createModalOpen && (
        <CreateTicketModal
          user={user}
          onClose={() => setCreateModalOpen(false)}
          onCreated={() => load()}
        />
      )}

      {selected && (
        <div className="modal-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setSelected(null);
        }}>
          <section className="ticket-modal panel" role="dialog" aria-modal="true" aria-labelledby="ticket-detail-title">
            <div className="panel-heading">
              <div>
                <div className="eyebrow">TICKET DETAILS</div>
                <h2 id="ticket-detail-title">{selected.title || selected.summary || selected.ticket_code || "Ticket"}</h2>
                <p>{selected.ticket_code || `Ticket #${selected.ticket_id ?? selected.id ?? "—"}`}</p>
              </div>
              <button type="button" className="icon-button border-button" onClick={() => setSelected(null)} aria-label="Close ticket details">×</button>
            </div>
            {detailLoading && <div className="loading-panel"><span className="spinner spinner-dark" /> Loading ticket details…</div>}
            {detailError && <div className="alert alert-warning"><AlertCircle size={16}/><span>{detailError}</span></div>}
            <div className="ticket-detail-grid">
              <div><small>Status</small><b>{String(selected.status || "ANALYZED").replaceAll("_", " ")}</b></div>
              <div><small>Priority</small><b>{selected.priority || "—"}</b></div>
              <div><small>Severity</small><b>{selected.severity || "—"}</b></div>
              <div><small>Department</small><b>{selected.department_name || selected.department_id || "—"}</b></div>
              <div><small>Created by</small><b>{selected.created_by_name || selected.created_by || "—"}</b></div>
              <div><small>Created</small><b>{selected.created_at ? new Date(selected.created_at).toLocaleString() : "—"}</b></div>
            </div>
            <div className="ticket-description-block">
              <h3>Description / reported issue</h3>
              <p>{selected.description || selected.ticket || selected.problem || "No description was returned."}</p>
            </div>
            {selected.suggested_resolution && <div className="ticket-description-block"><h3>Suggested resolution</h3><p>{selected.suggested_resolution}</p></div>}
            {view === "enterprise" && (
              <div className="ticket-history-block">
                <h3>History & timeline</h3>
                {history.length ? history.map((entry) => (
                  <div className="history-entry" key={entry.history_id || `${entry.changed_at}-${entry.comment}`}>
                    <span className="history-dot" />
                    <div><b>{entry.comment || `${entry.old_status || "Ticket"} → ${entry.new_status || "updated"}`}</b><small>{entry.changed_by_name || entry.changed_by || "System"} · {entry.changed_at ? new Date(entry.changed_at).toLocaleString() : "—"}</small></div>
                  </div>
                )) : <p className="muted-cell">No additional history events are available.</p>}
              </div>
            )}
            <div className="modal-actions">
              <button type="button" className="button button-secondary" onClick={analyzeSelected}>
                <Bot size={16}/> Analyze this ticket
              </button>
              <button type="button" className="button button-primary" onClick={() => setSelected(null)}>Done</button>
            </div>
          </section>
        </div>
      )}
    </>
  );
}
