import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  AlertCircle,
  ArrowUpRight,
  BarChart3,
  Bot,
  CheckCircle2,
  Clock3,
  FileClock,
  FilePlus2,
  Gauge,
  Plus,
  RefreshCw,
  ShieldCheck,
  Ticket,
} from "lucide-react";

import { NavLink, useNavigate } from "react-router-dom";

import {
  analyticsApi,
  enterpriseTicketApi,
  errorMessage,
} from "../api/services";

import {
  objectOrEmpty,
  safeArray,
  fmt,
  firstDefined,
  firstName,
  getUserName,
} from "../utils";

import {
  PageHeader,
  LoadingPanel,
  EmptyState,
  TicketTable,
} from "../components/Common.jsx";
import CreateTicketModal from "../components/CreateTicketModal.jsx";


function validDate(value) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function isoDate(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function isoWeekRange(year, week) {
  // ISO week 1 is the week containing January 4.
  const jan4 = new Date(year, 0, 4);
  const monday = new Date(jan4);
  monday.setDate(jan4.getDate() - ((jan4.getDay() + 6) % 7) + (week - 1) * 7);
  const sunday = new Date(monday);
  sunday.setDate(monday.getDate() + 6);
  return { start: monday, end: sunday };
}

function getTimelineRange(item, rawPeriod) {
  const start = validDate(
    item.start_date ?? item.startDate ?? item.period_start ?? item.periodStart ?? item.from ?? item.start
  );
  const end = validDate(
    item.end_date ?? item.endDate ?? item.period_end ?? item.periodEnd ?? item.to ?? item.end
  );
  if (start && end) return { start, end };

  const dateFromItem = validDate(item.date ?? item.created_at ?? item.timestamp);
  if (dateFromItem) {
    const monday = new Date(dateFromItem);
    monday.setHours(0, 0, 0, 0);
    monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7));
    const sunday = new Date(monday);
    sunday.setDate(monday.getDate() + 6);
    sunday.setHours(23, 59, 59, 999);
    return { start: monday, end: sunday };
  }

  const weekMatch = String(rawPeriod).match(/W\s*(\d{1,2})/i);
  if (weekMatch) {
    const year = Number(item.year ?? item.iso_year ?? item.isoYear) || new Date().getFullYear();
    const range = isoWeekRange(year, Number(weekMatch[1]));
    range.start.setHours(0, 0, 0, 0);
    range.end.setHours(23, 59, 59, 999);
    return range;
  }
  return null;
}

export default function Dashboard({ user }) {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [stats, setStats] = useState({});
  const [timeline, setTimeline] = useState([]);
  const [tickets, setTickets] = useState([]);
  const [scope, setScope] = useState("");
  const [createModalOpen, setCreateModalOpen] = useState(false);

  // Normalize role values safely; the API may return roles as strings or objects.
  const normalizedRoles = [
    ...(Array.isArray(user?.roles) ? user.roles : []),
    ...(user?.role ? [user.role] : []),
  ].map((role) =>
    String(typeof role === "object" ? (role?.name || role?.role || "") : role)
      .trim()
      .toUpperCase()
  );

  const canCreate = normalizedRoles.some((role) =>
    ["ADMIN", "MANAGER", "DEVELOPER", "SUPPORT", "EMPLOYEE"].includes(role)
  );

  const load = useCallback(async (quiet = false) => {
    if (quiet) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    setError("");

    try {
      const results = await Promise.allSettled([
        analyticsApi.getDashboard(),
        analyticsApi.getTimeline("weekly", 8),
        enterpriseTicketApi.getAll({
          sort_by: "created_at",
          sort_order: "desc",
        }),
      ]);

      // Dashboard statistics
      if (results[0].status === "fulfilled") {
        const data = objectOrEmpty(results[0].value.data);

        setStats(objectOrEmpty(data.statistics));
        setScope(data.scope || "");
      } else {
        setError(
          errorMessage(
            results[0].reason,
            "Dashboard statistics could not be loaded.",
          ),
        );
      }

      // Ticket activity timeline
      if (results[1].status === "fulfilled") {
        const data = objectOrEmpty(results[1].value.data);

        setTimeline(
          safeArray(data.timeline ?? data.items ?? data.data ?? data.periods),
        );
      }

      // Recent tickets
      if (results[2].status === "fulfilled") {
        const data = results[2].value.data;
        setTickets(safeArray(data?.tickets ?? data?.items ?? data));
      }

    } catch (err) {
      setError(errorMessage(err, "Unable to load the dashboard."));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Extract statistics returned by the backend
  const total = firstDefined(stats, [
    "total_tickets",
    "total",
    "tickets_total",
    "all_tickets",
  ]);

  const open = firstDefined(stats, ["open_tickets", "open", "open_count"]);

  const progress = firstDefined(stats, [
    "in_progress_tickets",
    "in_progress",
    "in_progress_count",
  ]);

  const resolved = firstDefined(stats, [
    "resolved_tickets",
    "resolved",
    "closed_tickets",
    "closed",
  ]);

  // Dashboard statistic cards
  const cards = [
    {
      label: "Total tickets",
      value: total,
      icon: Ticket,
      tone: "violet",
      foot: "Tickets in your access scope",
    },
    {
      label: "Open tickets",
      value: open,
      icon: Activity,
      tone: "blue",
      foot: "Awaiting action",
    },
    {
      label: "In progress",
      value: progress,
      icon: Clock3,
      tone: "amber",
      foot: "Currently being worked on",
    },
    {
      label: "Resolved",
      value: resolved,
      icon: CheckCircle2,
      tone: "green",
      foot: "Completed tickets",
    },
  ];

  return (
    <>
      <PageHeader
        eyebrow="YOUR WORKSPACE"
        title={`Good to see you, ${firstName(getUserName(user))}.`}
        description="Here’s what’s happening across your support workspace."
        action={
          <button
            className="button button-secondary"
            onClick={() => load(true)}
            disabled={refreshing}
          >
            <RefreshCw size={16} className={refreshing ? "spin" : ""} />

            {refreshing ? "Refreshing" : "Refresh"}
          </button>
        }
      />

      {error && (
        <div className="alert alert-warning">
          <AlertCircle size={17} />
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        <LoadingPanel label="Loading your workspace…" />
      ) : (
        <>
          {/* Workspace summary */}
          <div className="welcome-strip">
            <div className="welcome-symbol">
              <Gauge size={22} />
            </div>

            <div>
              <b>Your workspace at a glance</b>
              <p>
                Analytics are scoped according to your assigned role and
                department.
              </p>
            </div>

            <span className="scope-pill">
              <ShieldCheck size={14} />
              {scope || "Authorized view"}
            </span>
          </div>

          {/* Statistics */}
          <div className="stat-grid">
            {cards.map(({ label, value, icon: Icon, tone, foot }) => {
              const statusFilter = {
                "Open tickets": "OPEN",
                "In progress": "IN_PROGRESS",
                "Resolved": "RESOLVED",
              }[label];
              const destination = statusFilter
                ? `/tickets?status=${encodeURIComponent(statusFilter)}`
                : "/tickets";

              return (
                <button
                  type="button"
                  className="stat-card stat-card-button"
                  key={label}
                  onClick={() => navigate(destination)}
                  aria-label={`View ${label.toLowerCase()}`}
                  title={`View ${label.toLowerCase()}`}
                >
                  <span className="stat-top">
                    <span>{label}</span>
                    <span className={`stat-icon ${tone}`}>
                      <Icon size={18} />
                    </span>
                  </span>
                  <span className="stat-value">
                    {value === undefined ? "—" : fmt(value)}
                  </span>
                  <span className="stat-foot">
                    <span className="stat-foot-dot" />
                    {foot}
                  </span>
                  <span className="stat-card-action">View tickets <ArrowUpRight size={14} /></span>
                </button>
              );
            })}
          </div>

          {/* Dashboard charts and actions */}
          <div className="dashboard-grid">
            <section className="panel trend-panel">
              <div className="panel-heading">
                <div>
                  <h2>Ticket activity</h2>
                  <p>Recent weekly ticket trend</p>
                </div>

                <span className="period-badge">Last 8 periods</span>
              </div>

              {timeline.length ? (
                <div className="mini-chart dashboard-mini-chart" aria-label="Recent weekly ticket activity">
                  {timeline.map((item, index) => {
                    const value = Math.max(0, Number(
                      item.count ?? item.total ?? item.ticket_count ?? item.value ?? 0,
                    ) || 0);
                    const max = Math.max(1, ...timeline.map((entry) => Number(
                      entry.count ?? entry.total ?? entry.ticket_count ?? entry.value ?? 0,
                    ) || 0));
                    const rawPeriod = String(item.label ?? item.period ?? item.date ?? "");
                    const weekMatch = rawPeriod.match(/W\d+/i);
                    const periodLabel = weekMatch?.[0]?.toUpperCase() || rawPeriod.slice(-5) || `Week ${index + 1}`;

                    const timelineRange = getTimelineRange(item, rawPeriod);
                    const analyticsUrl = (() => {
                      const params = new URLSearchParams({ period: "weekly", focusLabel: `Tickets · ${periodLabel}` });
                      if (timelineRange) {
                        params.set("focusStart", isoDate(timelineRange.start));
                        params.set("focusEnd", isoDate(timelineRange.end));
                        params.set("year", String(timelineRange.start.getFullYear()));
                        params.set("month", String(timelineRange.start.getMonth()));
                      } else {
                        // Preserve the chosen period even if the backend timeline omits dates.
                        params.set("focusCount", String(value));
                        params.set("focusPeriod", rawPeriod || periodLabel);
                      }
                      return `/analytics?${params.toString()}`;
                    })();

                    return (
                      <button
                        type="button"
                        className="chart-column dashboard-chart-column"
                        key={item.period ?? item.label ?? item.date ?? index}
                        onClick={() => navigate(analyticsUrl)}
                        title={`View the tickets for ${periodLabel} (${value} tickets)`}
                        aria-label={`View tickets for ${periodLabel}, ${value} tickets in Analytics`}
                      >
                        <span className="dashboard-chart-count">{value.toLocaleString()}</span>
                        <span className="chart-bar-wrap dashboard-chart-bar-wrap" aria-hidden="true">
                          <span
                            className="chart-bar dashboard-chart-bar"
                            style={{ height: `${value === 0 ? 0 : Math.max(8, (value / max) * 100)}%` }}
                          />
                        </span>
                        <span className="dashboard-chart-period">{periodLabel}</span>
                      </button>
                    );
                  })}
                </div>
              ) : (
                <EmptyState
                  icon={BarChart3}
                  title="No timeline data yet"
                  body="Ticket activity will appear here when the API returns timeline records."
                />
              )}
            </section>

            {/* Quick actions */}
            <section className="panel quick-panel">
              <div className="panel-heading">
                <div>
                  <h2>Quick actions</h2>
                  <p>Move work forward</p>
                </div>
              </div>

              <div className="quick-actions">
                {canCreate && (
                  <button type="button" onClick={() => setCreateModalOpen(true)} className="quick-action">
                    <span className="quick-action-icon violet">
                      <FilePlus2 size={19} />
                    </span>
                    <span>
                      <b>Create a ticket</b>
                      <small>Log an ERP issue or request</small>
                    </span>
                    <ArrowUpRight size={17} />
                  </button>
                )}

                <NavLink to="/ai-analysis" className="quick-action">
                  <span className="quick-action-icon blue">
                    <Bot size={19} />
                  </span>

                  <span>
                    <b>Analyze with AI</b>
                    <small>Get triage and resolution guidance</small>
                  </span>

                  <ArrowUpRight size={17} />
                </NavLink>

                <NavLink to="/analytics" className="quick-action">
                  <span className="quick-action-icon green">
                    <BarChart3 size={19} />
                  </span>

                  <span>
                    <b>View analytics</b>
                    <small>Explore ticket trends</small>
                  </span>

                  <ArrowUpRight size={17} />
                </NavLink>
              </div>
            </section>
          </div>

          {/* Recent tickets */}
          <section className="panel recent-panel">
            <div className="panel-heading">
              <div>
                <h2>Recent tickets</h2>
                <p>Latest tickets visible to your account</p>
              </div>

              <NavLink to="/tickets" className="text-link">
                View all tickets
                <ArrowUpRight size={15} />
              </NavLink>
            </div>

            {tickets.length ? (
              <TicketTable
                tickets={tickets.slice(0, 5)}
                onView={(ticket) => navigate("/tickets", { state: { ticketToOpen: ticket } })}
              />
            ) : (
              <EmptyState
                icon={FileClock}
                title="No tickets to show"
                body="Create a ticket to start tracking work in BugPilot."
                action={canCreate ? (
                  <button type="button" className="button button-primary button-small" onClick={() => setCreateModalOpen(true)}>
                    <Plus size={15} /> Create ticket
                  </button>
                ) : null}
              />
            )}
          </section>

        </>
      )}
      {createModalOpen && (
        <CreateTicketModal
          user={user}
          onClose={() => setCreateModalOpen(false)}
          onCreated={() => load(true)}
        />
      )}
    </>
  );
}
