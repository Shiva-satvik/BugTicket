import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  AlertCircle,
  BarChart3,
  CalendarDays,
  ChevronDown,
  Clock3,
  RefreshCw,
  ShieldCheck,
  X,
} from "lucide-react";

import {
  analyticsApi,
  enterpriseTicketApi,
  errorMessage,
} from "../api/services";

import {
  objectOrEmpty,
  safeArray,
  fmt,
  getTicketId,
  getTicketTitle,
  getStatus,
} from "../utils";

import {
  PageHeader,
  LoadingPanel,
  EmptyState,
  TicketTable,
} from "../components/Common.jsx";

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const PERIOD_OPTIONS = [
  { value: "daily", label: "Day" },
  { value: "weekly", label: "Week" },
  { value: "monthly", label: "Month" },
];

function ticketDate(ticket) {
  const raw =
    ticket?.created_at ??
    ticket?.createdAt ??
    ticket?.created_on ??
    ticket?.created ??
    ticket?.opened_at ??
    ticket?.date;
  if (!raw) return null;
  const date = new Date(raw);
  return Number.isNaN(date.getTime()) ? null : date;
}

function startOfDay(date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

function endOfDay(date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate(), 23, 59, 59, 999);
}

function buildBuckets(period, year, month) {
  if (period === "monthly") {
    return MONTHS.map((label, index) => {
      const start = new Date(year, index, 1);
      const end = new Date(year, index + 1, 0, 23, 59, 59, 999);
      return { key: `${year}-${String(index + 1).padStart(2, "0")}`, label: label.slice(0, 3), detail: `${label} ${year}`, start, end };
    });
  }

  const monthStart = new Date(year, month, 1);
  const monthEnd = new Date(year, month + 1, 0);
  const dayCount = monthEnd.getDate();

  if (period === "daily") {
    return Array.from({ length: dayCount }, (_, index) => {
      const day = index + 1;
      const start = new Date(year, month, day);
      return {
        key: `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`,
        label: String(day).padStart(2, "0"),
        detail: start.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" }),
        start,
        end: endOfDay(start),
      };
    });
  }

  const buckets = [];
  for (let firstDay = 1; firstDay <= dayCount; firstDay += 7) {
    const lastDay = Math.min(firstDay + 6, dayCount);
    const start = new Date(year, month, firstDay);
    const end = endOfDay(new Date(year, month, lastDay));
    buckets.push({
      key: `${year}-${String(month + 1).padStart(2, "0")}-week-${firstDay}`,
      label: `${firstDay}–${lastDay}`,
      detail: `${MONTHS[month]} ${firstDay}–${lastDay}, ${year}`,
      start,
      end,
    });
  }
  return buckets;
}

function inRange(date, start, end) {
  return date && date >= start && date <= end;
}

export default function AnalyticsPage() {
  const now = new Date();
  const [searchParams] = useSearchParams();
  const focusStartParam = searchParams.get("focusStart");
  const focusEndParam = searchParams.get("focusEnd");
  const focusLabelParam = searchParams.get("focusLabel");
  const requestedPeriod = searchParams.get("period");
  const initialYear = Number(searchParams.get("year")) || now.getFullYear();
  const initialMonthParam = searchParams.get("month");
  const initialMonth = initialMonthParam === null ? Number.NaN : Number(initialMonthParam);
  const [period, setPeriod] = useState(["daily", "weekly", "monthly"].includes(requestedPeriod) ? requestedPeriod : "monthly");
  const [selectedMonth, setSelectedMonth] = useState(Number.isInteger(initialMonth) && initialMonth >= 0 && initialMonth <= 11 ? initialMonth : now.getMonth());
  const [selectedYear, setSelectedYear] = useState(initialYear);
  const [dashboard, setDashboard] = useState({});
  const [breakdowns, setBreakdowns] = useState({});
  const [access, setAccess] = useState({});
  const [tickets, setTickets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [ticketLoadWarning, setTicketLoadWarning] = useState("");
  const [selectedBucket, setSelectedBucket] = useState(null);
  const [selectedTicket, setSelectedTicket] = useState(null);
  const [ticketHistory, setTicketHistory] = useState([]);
  const [ticketDetailLoading, setTicketDetailLoading] = useState(false);
  const [ticketDetailError, setTicketDetailError] = useState("");

  const load = useCallback(async (quiet = false) => {
    if (quiet) setRefreshing(true);
    else setLoading(true);

    setError("");
    setTicketLoadWarning("");

    const results = await Promise.allSettled([
      analyticsApi.getDashboard(),
      analyticsApi.getBreakdowns(),
      analyticsApi.getAccessAnalytics(),
      enterpriseTicketApi.getAll({ sort_by: "created_at", sort_order: "desc" }),
    ]);

    if (results[0].status === "fulfilled") {
      const data = objectOrEmpty(results[0].value.data);
      setDashboard(objectOrEmpty(data.statistics));
    } else {
      setError(errorMessage(results[0].reason, "Analytics summary could not be loaded."));
    }

    if (results[1].status === "fulfilled") {
      setBreakdowns(objectOrEmpty(results[1].value.data?.breakdowns));
    } else {
      setBreakdowns({});
    }

    if (results[2].status === "fulfilled") {
      setAccess(objectOrEmpty(results[2].value.data));
    } else {
      setAccess({});
    }

    if (results[3].status === "fulfilled") {
      const data = results[3].value.data;
      setTickets(safeArray(data?.tickets ?? data?.items ?? data?.data ?? data));
    } else {
      setTickets([]);
      setTicketLoadWarning(
        errorMessage(results[3].reason, "Ticket records could not be loaded. Chart bars cannot open ticket details until the ticket endpoint is available.")
      );
    }

    setLoading(false);
    setRefreshing(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!selectedBucket) return undefined;
    const onKeyDown = (event) => {
      if (event.key === "Escape") setSelectedBucket(null);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [selectedBucket]);

  const datedTickets = useMemo(
    () => tickets.map((ticket) => ({ ticket, date: ticketDate(ticket) })).filter((item) => item.date),
    [tickets]
  );

  const buckets = useMemo(
    () => buildBuckets(period, selectedYear, selectedMonth),
    [period, selectedYear, selectedMonth]
  );

  const chartData = useMemo(
    () => buckets.map((bucket) => ({
      ...bucket,
      tickets: datedTickets.filter(({ date }) => inRange(date, bucket.start, bucket.end)).map(({ ticket }) => ticket),
      count: datedTickets.filter(({ date }) => inRange(date, bucket.start, bucket.end)).length,
    })),
    [buckets, datedTickets]
  );

  // When arriving from a dashboard chart, automatically open the exact date range
  // represented by the clicked bar, with the matching ticket records in the modal.
  useEffect(() => {
    if (loading || !focusStartParam || !focusEndParam) return;
    const start = new Date(`${focusStartParam}T00:00:00`);
    const end = new Date(`${focusEndParam}T23:59:59.999`);
    if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || start > end) return;
    const matchingTickets = datedTickets
      .filter(({ date }) => inRange(date, start, end))
      .map(({ ticket }) => ticket);
    setSelectedBucket({
      key: `dashboard-${focusStartParam}-${focusEndParam}`,
      label: focusLabelParam || "Dashboard ticket activity",
      detail: focusLabelParam || `${start.toLocaleDateString()} – ${end.toLocaleDateString()}`,
      start,
      end,
      tickets: matchingTickets,
      count: matchingTickets.length,
    });
  }, [loading, focusStartParam, focusEndParam, focusLabelParam, datedTickets]);

  const maxCount = Math.max(1, ...chartData.map((item) => item.count));
  const years = useMemo(() => {
    const ticketYears = datedTickets.map(({ date }) => date.getFullYear());
    return [...new Set([now.getFullYear(), ...ticketYears, now.getFullYear() - 1, now.getFullYear() - 2])].sort((a, b) => b - a);
  }, [datedTickets, now]);

  const selectedTickets = selectedBucket?.tickets ?? [];
  const summaryCards = Object.entries(dashboard)
    .filter(([, value]) => typeof value === "number")
    .slice(0, 4);

  const breakdownEntries = Object.entries(breakdowns).filter(
    ([, value]) => Array.isArray(value) || (value !== null && typeof value === "object")
  );

  const chartTitle = period === "monthly"
    ? `Monthly ticket volume · ${selectedYear}`
    : `${period === "daily" ? "Daily" : "Weekly"} ticket volume · ${MONTHS[selectedMonth]} ${selectedYear}`;

  async function openTicketDetails(ticket) {
    setSelectedTicket(ticket);
    setTicketHistory([]);
    setTicketDetailError("");
    setTicketDetailLoading(true);

    const id = getTicketId(ticket);
    if (!id || id === "—") {
      setTicketDetailError("This ticket does not include a usable ticket ID.");
      setTicketDetailLoading(false);
      return;
    }

    const results = await Promise.allSettled([
      enterpriseTicketApi.getById(id),
      enterpriseTicketApi.getHistory(id),
    ]);

    if (results[0].status === "fulfilled") {
      setSelectedTicket(results[0].value.data?.ticket ?? results[0].value.data);
    } else {
      setTicketDetailError(errorMessage(results[0].reason, "Could not load the latest ticket details. Showing the available ticket summary instead."));
    }

    if (results[1].status === "fulfilled") {
      const payload = results[1].value.data;
      setTicketHistory(safeArray(payload?.history ?? payload?.items ?? payload?.events ?? payload));
    }

    setTicketDetailLoading(false);
  }

  useEffect(() => {
    if (!selectedTicket) return undefined;
    const onKeyDown = (event) => {
      if (event.key === "Escape") setSelectedTicket(null);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [selectedTicket]);

  const detailFields = selectedTicket ? [
    ["Ticket ID", selectedTicket.ticket_code || selectedTicket.ticket_number || getTicketId(selectedTicket)],
    ["Status", getStatus(selectedTicket)],
    ["Priority", selectedTicket.priority],
    ["Severity", selectedTicket.severity],
    ["Module", selectedTicket.module || selectedTicket.category],
    ["Created", selectedTicket.created_at || selectedTicket.createdAt || selectedTicket.created_on],
    ["Updated", selectedTicket.updated_at || selectedTicket.updatedAt],
    ["Assigned to", selectedTicket.assignee_name || selectedTicket.assigned_to || selectedTicket.assignee],
    ["Reported by", selectedTicket.reporter_name || selectedTicket.created_by_name || selectedTicket.created_by],
  ].filter(([, value]) => value !== undefined && value !== null && value !== "") : [];

  return (
    <>
      <PageHeader
        eyebrow="INSIGHTS"
        title="Analytics & trends"
        description="Explore ticket activity, review historical patterns, and open the tickets behind any data point."
        action={
          <button type="button" className="button button-secondary" onClick={() => load(true)} disabled={refreshing}>
            <RefreshCw size={16} className={refreshing ? "spin" : ""} />
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>
        }
      />

      {error && <div className="alert alert-warning"><AlertCircle size={17} /><span>{error}</span></div>}

      <section className="analytics-control-panel panel">
        <div className="analytics-control-copy">
          <span className="analytics-control-icon"><CalendarDays size={19} /></span>
          <div>
            <h2>Reporting period</h2>
            <p>Choose a time scale and date range for your ticket activity.</p>
          </div>
        </div>
        <div className="analytics-filters">
          <label className="analytics-select-wrap">
            <span>View by</span>
            <span className="analytics-select">
              <select value={period} onChange={(event) => setPeriod(event.target.value)}>
                {PERIOD_OPTIONS.map((option) => <option value={option.value} key={option.value}>{option.label}</option>)}
              </select>
              <ChevronDown size={15} />
            </span>
          </label>

          {period !== "monthly" && (
            <label className="analytics-select-wrap">
              <span>Month</span>
              <span className="analytics-select">
                <select value={selectedMonth} onChange={(event) => setSelectedMonth(Number(event.target.value))}>
                  {MONTHS.map((month, index) => <option value={index} key={month}>{month}</option>)}
                </select>
                <ChevronDown size={15} />
              </span>
            </label>
          )}

          <label className="analytics-select-wrap">
            <span>Year</span>
            <span className="analytics-select">
              <select value={selectedYear} onChange={(event) => setSelectedYear(Number(event.target.value))}>
                {years.map((year) => <option value={year} key={year}>{year}</option>)}
              </select>
              <ChevronDown size={15} />
            </span>
          </label>

          <span className="scope-pill"><ShieldCheck size={14} /> Scope: {access.scope || "Authorized"}</span>
        </div>
      </section>

      {loading ? <LoadingPanel label="Loading analytics…" /> : (
        <>
          {summaryCards.length > 0 && (
            <div className="stat-grid analytics-stats">
              {summaryCards.map(([key, value], index) => (
                <div className="stat-card" key={key}>
                  <div className="stat-top">
                    <span>{key.replaceAll("_", " ")}</span>
                    <span className={`stat-icon ${["violet", "blue", "amber", "green"][index]}`}><BarChart3 size={18} /></span>
                  </div>
                  <div className="stat-value">{fmt(value)}</div>
                  <div className="stat-foot"><span className="stat-foot-dot" />Workspace total</div>
                </div>
              ))}
            </div>
          )}

          <section className="panel analytics-chart-panel analytics-chart-modern">
            <div className="analytics-chart-heading">
              <div>
                <span className="eyebrow">TICKET ACTIVITY</span>
                <h2>{chartTitle}</h2>
                <p>Select any bar to see the tickets created during that period.</p>
              </div>
              <div className="analytics-chart-total">
                <span>Tickets in chart</span>
                <strong>{chartData.reduce((sum, bucket) => sum + bucket.count, 0).toLocaleString()}</strong>
              </div>
            </div>

            {ticketLoadWarning && <div className="alert alert-warning"><AlertCircle size={17} /><span>{ticketLoadWarning}</span></div>}

            {chartData.length > 0 ? (
              <div className={`analytics-bars-scroll ${period === "daily" ? "analytics-bars-daily" : ""}`}>
                <div className="analytics-bars">
                  {chartData.map((bucket) => {
                    const height = bucket.count === 0 ? 3 : Math.max(7, (bucket.count / maxCount) * 100);
                    return (
                      <button
                        type="button"
                        className="analytics-bar-column"
                        key={bucket.key}
                        onClick={() => setSelectedBucket(bucket)}
                        title={`View ${bucket.count} ticket(s) for ${bucket.detail}`}
                        aria-label={`View ${bucket.count} tickets for ${bucket.detail}`}
                      >
                        <span className="analytics-bar-count">{bucket.count}</span>
                        <span className="analytics-bar-track">
                          <span className={`analytics-bar-fill ${bucket.count ? "" : "analytics-bar-empty"}`} style={{ height: `${height}%` }} />
                        </span>
                        <span className="analytics-bar-label">{bucket.label}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            ) : (
              <EmptyState icon={BarChart3} title="No ticket activity" body="No chart periods are available for this selection." />
            )}

            <div className="analytics-chart-footer">
              <span><span className="analytics-legend-dot" /> Tickets created in each period</span>
              <span>{tickets.length.toLocaleString()} ticket records loaded</span>
            </div>
          </section>

          {breakdownEntries.length > 0 && (
            <section className="panel analytics-breakdowns">
              <div className="panel-heading">
                <div><h2>Ticket breakdowns</h2><p>Additional grouped data returned by your analytics service.</p></div>
              </div>
              <div className="breakdown-grid">
                {breakdownEntries.map(([key, value]) => (
                  <div className="breakdown-card" key={key}>
                    <h3>{key.replaceAll("_", " ")}</h3>
                    {Array.isArray(value)
                      ? value.slice(0, 8).map((item, index) => (
                        <div className="breakdown-row" key={index}>
                          <span>{fmt(item.label ?? item.name ?? item.status ?? item.category ?? item.key ?? `Item ${index + 1}`)}</span>
                          <b>{fmt(item.count ?? item.total ?? item.value ?? item.ticket_count)}</b>
                        </div>
                      ))
                      : Object.entries(objectOrEmpty(value)).slice(0, 8).map(([name, item]) => (
                        <div className="breakdown-row" key={name}>
                          <span>{name.replaceAll("_", " ")}</span>
                          <b>{fmt(item !== null && typeof item === "object" ? (item.count ?? item.total) : item)}</b>
                        </div>
                      ))}
                  </div>
                ))}
              </div>
            </section>
          )}
        </>
      )}

      {selectedBucket && (
        <div className="analytics-ticket-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setSelectedBucket(null);
        }}>
          <section className="analytics-ticket-modal" role="dialog" aria-modal="true" aria-labelledby="analytics-ticket-title">
            <header className="analytics-ticket-modal-header">
              <div>
                <span className="eyebrow">PERIOD DETAILS</span>
                <h2 id="analytics-ticket-title">{selectedBucket.detail}</h2>
                <p>{selectedTickets.length} ticket{selectedTickets.length === 1 ? "" : "s"} created in this period</p>
              </div>
              <button type="button" className="icon-button" onClick={() => setSelectedBucket(null)} aria-label="Close ticket list"><X size={19} /></button>
            </header>

            {selectedTickets.length ? (
              <TicketTable tickets={selectedTickets} showDescription onView={openTicketDetails} />
            ) : (
              <EmptyState icon={Clock3} title="No tickets in this period" body="There are no ticket records with a creation date in this time range." />
            )}

            <footer className="analytics-ticket-modal-footer">
              <span>Results follow your authorized ticket scope.</span>
              <button type="button" className="button button-secondary" onClick={() => setSelectedBucket(null)}>Close</button>
            </footer>
          </section>
        </div>
      )}

      {selectedTicket && (
        <div
          className="analytics-ticket-backdrop analytics-ticket-detail-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setSelectedTicket(null);
          }}
        >
          <section className="analytics-ticket-modal analytics-ticket-detail-modal" role="dialog" aria-modal="true" aria-labelledby="analytics-detail-title">
            <header className="analytics-ticket-modal-header">
              <div>
                <span className="eyebrow">TICKET DETAILS</span>
                <h2 id="analytics-detail-title">{getTicketTitle(selectedTicket)}</h2>
                <p>{selectedTicket.ticket_code || `#${getTicketId(selectedTicket)}`} · {getStatus(selectedTicket)}</p>
              </div>
              <button type="button" className="icon-button" onClick={() => setSelectedTicket(null)} aria-label="Close ticket details"><X size={19} /></button>
            </header>

            {ticketDetailLoading && <div className="analytics-detail-loading"><span className="spinner spinner-dark" /> Loading full ticket details…</div>}
            {ticketDetailError && <div className="alert alert-warning"><AlertCircle size={17} /><span>{ticketDetailError}</span></div>}

            <div className="analytics-ticket-detail-grid">
              {detailFields.map(([label, value]) => (
                <div className="analytics-ticket-detail-field" key={label}>
                  <span>{label}</span>
                  <strong>{label === "Created" || label === "Updated"
                    ? (value ? new Date(value).toLocaleString() : "—")
                    : fmt(value)}</strong>
                </div>
              ))}
            </div>

            <section className="analytics-ticket-description">
              <h3>Description</h3>
              <p>{selectedTicket.description || selectedTicket.problem || selectedTicket.ticket || selectedTicket.details || "No description was provided for this ticket."}</p>
            </section>

            {selectedTicket.resolution && (
              <section className="analytics-ticket-description">
                <h3>Resolution</h3>
                <p>{selectedTicket.resolution}</p>
              </section>
            )}

            <section className="analytics-ticket-history">
              <div className="analytics-ticket-history-heading">
                <h3>Ticket history</h3>
                <span>{ticketHistory.length} event{ticketHistory.length === 1 ? "" : "s"}</span>
              </div>
              {ticketHistory.length ? (
                <div className="analytics-history-list">
                  {ticketHistory.map((event, index) => (
                    <article className="analytics-history-item" key={event.id || event.event_id || index}>
                      <span className="analytics-history-marker" />
                      <div>
                        <strong>{event.action || event.event || event.title || event.status || "Ticket updated"}</strong>
                        <p>{event.description || event.comment || event.message || event.details || event.new_value || "Ticket activity recorded."}</p>
                        <small>{event.created_at || event.timestamp || event.changed_at
                          ? new Date(event.created_at || event.timestamp || event.changed_at).toLocaleString()
                          : "Timestamp unavailable"}
                          {(event.actor_name || event.changed_by_name || event.user_name) ? ` · ${event.actor_name || event.changed_by_name || event.user_name}` : ""}
                        </small>
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="analytics-ticket-history-empty">{ticketDetailLoading ? "Loading history…" : "No history events were returned for this ticket."}</p>
              )}
            </section>

            <footer className="analytics-ticket-modal-footer">
              <span>Ticket visibility follows your account permissions.</span>
              <button type="button" className="button button-secondary" onClick={() => setSelectedTicket(null)}>Back to period</button>
            </footer>
          </section>
        </div>
      )}
    </>
  );
}
