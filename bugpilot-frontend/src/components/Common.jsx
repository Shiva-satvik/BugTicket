import { useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";

import {
  Activity,
  AlertCircle,
  ArrowUpRight,
  BarChart3,
  Bot,
  CheckCircle2,
  ChevronDown,
  Clock3,
  FileClock,
  FilePlus2,
  Gauge,
  LayoutDashboard,
  LogOut,
  Menu,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  Sun,
  Moon,
  ShieldCheck,
  Ticket,
  UserRound,
  Users,
} from "lucide-react";

import {
  initials,
  fmt,
  getTicketId,
  getTicketTitle,
  getStatus,
  getUserName,
  safeArray,
} from "../utils";

/* =========================================================
   SIDEBAR
========================================================= */

export function Sidebar({ open, onNavigate, user }) {
  const roleNames = [
    ...(Array.isArray(user?.roles) ? user.roles : []),
    ...(user?.role ? [user.role] : []),
  ].map((role) => String(typeof role === "object" ? (role.name || role.role || "") : role).toUpperCase());
  const isAdmin = roleNames.includes("ADMIN");

  const groups = [
    {
      label: "WORKSPACE",
      items: [
        {
          to: "/",
          label: "Dashboard",
          icon: LayoutDashboard,
          end: true,
        },
        {
          to: "/tickets",
          label: "Ticket management",
          icon: Ticket,
        },
        {
          to: "/ai-analysis",
          label: "AI ticket analysis",
          icon: Bot,
        },
      ],
    },
    {
      label: "INSIGHTS",
      items: [
        {
          to: "/analytics",
          label: "Analytics & trends",
          icon: BarChart3,
        },
      ],
    },
    ...(isAdmin ? [{
      label: "ADMINISTRATION",
      items: [
        {
          to: "/employees",
          label: "Employees",
          icon: Users,
        },
      ],
    }] : []),
  ];

  return (
    <aside className={`sidebar ${open ? "sidebar-open" : ""}`}>
      <NavLink to="/" onClick={onNavigate} className="brand-lockup">
        <span className="brand-mark">
          <Bot size={21} />
        </span>

        <span>
          bugpilot<span className="brand-dot">.</span>
        </span>
      </NavLink>

      <div className="workspace-switch">
        <div className="workspace-icon">BP</div>

        <div className="workspace-copy">
          <b>Enterprise workspace</b>
          <small>ERP Operations</small>
        </div>

        <ChevronDown size={15} />
      </div>

      <nav className="sidebar-nav">
        {groups.map((group) => (
          <div className="nav-group" key={group.label}>
            <div className="nav-label">{group.label}</div>

            {group.items.map(({ to, label, icon: Icon, end }) => (
              <NavLink
                end={end}
                onClick={onNavigate}
                key={to}
                to={to}
                className={({ isActive }) =>
                  `nav-link ${isActive ? "nav-link-active" : ""}`
                }
              >
                <Icon size={18} />

                <span>{label}</span>

                {label === "Ticket management" && (
                  <span className="nav-arrow">›</span>
                )}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>

      <div className="sidebar-spacer" />

      <NavLink to="/profile" onClick={onNavigate} className="sidebar-user">
        <div className="avatar">{initials(getUserName(user))}</div>

        <div className="sidebar-user-copy">
          <b>{getUserName(user)}</b>

          <small>
            {user?.designation || user?.roles?.[0] || "Workspace member"}
          </small>
        </div>

        <Settings2 size={17} />
      </NavLink>
    </aside>
  );
}

/* =========================================================
   TOPBAR
========================================================= */

export function Topbar({ user, onMenu, onLogout, theme = "light", onToggleTheme }) {
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchValue, setSearchValue] = useState("");
  const location = useLocation();
  const navigate = useNavigate();

  const breadcrumbLabels = {
    "/": "Dashboard",
    "/tickets": "Ticket management",
    "/tickets/new": "Create ticket",
    "/ai-analysis": "AI ticket analysis",
    "/analytics": "Analytics & trends",
    "/profile": "Your profile",
    "/employees": "Employees",
  };
  const breadcrumb = breadcrumbLabels[location.pathname] || "Dashboard";

  function submitSearch(event) {
    if (event.key === "Enter" && searchValue.trim()) {
      event.preventDefault();
      navigate(`/tickets?q=${encodeURIComponent(searchValue.trim())}`);
      setSearchOpen(false);
    }
  }

  return (
    <header className="topbar">
      <button
        className="icon-button mobile-menu"
        aria-label="Toggle navigation"
        onClick={onMenu}
      >
        <Menu size={20} />
      </button>

      <div className="breadcrumb">
        <span>Workspace</span>
        <span className="crumb-slash">/</span>
        <b>{breadcrumb}</b>
      </div>

      <div className="topbar-actions">
        <div className={`top-search ${searchOpen ? "top-search-open" : ""}`}>
          <Search size={17} />

          <input
            aria-label="Search tickets"
            placeholder="Search tickets…"
            value={searchValue}
            onChange={(event) => setSearchValue(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                setSearchValue("");
                setSearchOpen(false);
              } else {
                submitSearch(event);
              }
            }}
            onFocus={() => setSearchOpen(true)}
          />

          <kbd>⌘ K</kbd>
        </div>

        <button
          className="icon-button search-mobile"
          aria-label="Search"
          onClick={() => setSearchOpen((value) => !value)}
        >
          <Search size={19} />
        </button>

        <span className="topbar-divider" />

        <button
          className="icon-button"
          title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          onClick={onToggleTheme}
        >
          {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
        </button>

        <div className="topbar-user">
          <div className="avatar avatar-small">
            {initials(getUserName(user))}
          </div>

          <div>
            <b>{getUserName(user)}</b>

            <small>
              {user?.department_id
                ? `Department ${user.department_id}`
                : "Signed in"}
            </small>
          </div>
        </div>

        <button
          className="icon-button"
          title="Sign out"
          aria-label="Sign out"
          onClick={onLogout}
        >
          <LogOut size={18} />
        </button>
      </div>
    </header>
  );
}

/* =========================================================
   PAGE HEADER
========================================================= */

export function PageHeader({ eyebrow, title, description, action }) {
  return (
    <div className="page-header">
      <div>
        <div className="eyebrow">{eyebrow}</div>

        <h1>{title}</h1>

        <p>{description}</p>
      </div>

      {action}
    </div>
  );
}

/* =========================================================
   TICKET TABLE
========================================================= */

export function TicketTable({ tickets = [], showDescription = false, onView }) {
  const ticketList = safeArray(tickets);

  if (ticketList.length === 0) {
    return (
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Ticket</th>
              <th>Status</th>
              <th>Priority</th>
              <th>Severity</th>
              <th>Updated</th>
              {onView && <th>Action</th>}
            </tr>
          </thead>

          <tbody>
            <tr>
              <td colSpan={onView ? 6 : 5}>No tickets available.</td>
            </tr>
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            <th>Ticket</th>
            <th>Status</th>
            <th>Priority</th>
            <th>Severity</th>
            <th>Updated</th>
            {onView && <th>Action</th>}
          </tr>
        </thead>

        <tbody>
          {ticketList.map((ticket, index) => {
            const id = getTicketId(ticket);

            return (
              <tr key={id === "—" ? index : id}>
                <td>
                  <div className="ticket-cell">
                    <span className="ticket-id">
                      {ticket.ticket_code || `#${id}`}
                    </span>

                    <b>{getTicketTitle(ticket)}</b>

                    {showDescription && ticket.description && (
                      <small>{ticket.description}</small>
                    )}
                  </div>
                </td>

                <td>
                  <StatusBadge status={getStatus(ticket)} />
                </td>

                <td>
                  <PriorityBadge value={ticket.priority} />
                </td>

                <td>{fmt(ticket.severity)}</td>

                <td className="muted-cell">
                  {fmt(ticket.updated_at || ticket.created_at)}
                </td>
                {onView && (
                  <td>
                    <button type="button" className="table-action" onClick={() => onView(ticket)}>
                      View details
                    </button>
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/* =========================================================
   STATUS BADGE
========================================================= */

export function StatusBadge({ status }) {
  const key = String(status || "OPEN").toLowerCase();

  const label = key.replaceAll("_", " ");

  const cls = ["resolved", "closed", "done"].includes(key)
    ? "green"
    : ["in_progress", "in progress"].includes(key)
      ? "blue"
      : ["blocked", "critical"].includes(key)
        ? "red"
        : "amber";

  return (
    <span className={`status-badge ${cls}`}>
      <span />
      {label}
    </span>
  );
}

/* =========================================================
   PRIORITY BADGE
========================================================= */

export function PriorityBadge({ value }) {
  const priority = String(value || "MEDIUM").toLowerCase();

  const cls =
    priority === "urgent" || priority === "critical" || priority === "high"
      ? "priority-high"
      : priority === "low"
        ? "priority-low"
        : "priority-medium";

  return (
    <span className={`priority-badge ${cls}`}>{fmt(value || "MEDIUM")}</span>
  );
}

/* =========================================================
   EMPTY STATE
========================================================= */

export function EmptyState({ icon: Icon, title, body, action }) {
  return (
    <div className="empty-state">
      <div className="empty-icon">{Icon && <Icon size={22} />}</div>

      <h3>{title}</h3>

      <p>{body}</p>

      {action}
    </div>
  );
}

/* =========================================================
   LOADING PANEL
========================================================= */

export function LoadingPanel({ label = "Loading..." }) {
  return (
    <div className="loading-panel">
      <span className="spinner spinner-dark" />

      <span>{label}</span>
    </div>
  );
}

/* =========================================================
   RESULT BLOCK
========================================================= */

export function ResultBlock({ title, body }) {
  const content =
    typeof body === "string" && body.trim()
      ? body
      : "No information returned for this field.";

  return (
    <div className="result-block">
      <h3>{title}</h3>

      <p>{content}</p>
    </div>
  );
}
