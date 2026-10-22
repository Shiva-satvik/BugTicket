import { useEffect, useRef, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";

import {
  BarChart3,
  ChevronDown,
  ChevronsLeft,
  ChevronsRight,
  LayoutDashboard,
  LogOut,
  Menu,
  Moon,
  Search,
  Sparkles,
  Sun,
  Ticket,
  UserCog,
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

function absolutePhotoUrl(photoUrl) {
  if (!photoUrl) return "";
  if (/^https?:\/\//i.test(photoUrl)) return photoUrl;
  const base = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
  return `${base}${photoUrl.startsWith("/") ? photoUrl : `/${photoUrl}`}`;
}

/* =========================================================
   SIDEBAR
   - Collapses to a 76px icon rail with hover tooltips
   - Floating edge handle (always reachable, never overlaps)
   - Becomes an overlay drawer with a scrim on mobile
========================================================= */

export function Sidebar({ open, collapsed = false, onToggleCollapse, onNavigate, user }) {
  const roleNames = [
    ...(Array.isArray(user?.roles) ? user.roles : []),
    ...(user?.role ? [user.role] : []),
  ].map((role) => String(typeof role === "object" ? (role.name || role.role || "") : role).toUpperCase());
  const isAdmin = roleNames.includes("ADMIN");

  const groups = [
    {
      label: "MAIN MENU",
      items: [
        { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
        { to: "/tickets", label: "Ticket management", icon: Ticket },
        { to: "/ai-analysis", label: "AI ticket analysis", icon: Sparkles },
      ],
    },
    {
      label: "INSIGHTS",
      items: [{ to: "/analytics", label: "Analytics & trends", icon: BarChart3 }],
    },
    ...(isAdmin
      ? [{
          label: "ADMINISTRATION",
          items: [{ to: "/employees", label: "Employees", icon: Users }],
        }]
      : []),
  ];

  const firstRole = (() => {
    const role = Array.isArray(user?.roles) ? user.roles[0] : user?.role;
    return typeof role === "object" ? role?.name || role?.role : role;
  })();

  return (
    <>
      {open && <div className="sidebar-scrim" onClick={onNavigate} aria-hidden="true" />}

      <aside
        className={`sidebar ${open ? "sidebar-open" : ""} ${collapsed ? "sidebar-collapsed" : ""}`}
        aria-label="Primary navigation"
      >
        <button
          type="button"
          className="sidebar-collapse-toggle"
          onClick={onToggleCollapse}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!collapsed}
          title={`${collapsed ? "Expand" : "Collapse"} sidebar  (Ctrl+B)`}
        >
          {collapsed ? <ChevronsRight size={14} /> : <ChevronsLeft size={14} />}
        </button>

        <div className="sidebar-brand-row">
          <NavLink to="/" onClick={onNavigate} className="brand-lockup" title="BugPilot home">
            <span className="brand-mark">
              <Sparkles size={19} />
            </span>
            <span>
              BugPilot<span className="brand-dot">.</span>
            </span>
          </NavLink>
        </div>

        <div className="workspace-switch" title="ERP Operations · Support console">
          <div className="workspace-icon">BP</div>
          <div className="workspace-copy">
            <b>ERP Operations</b>
            <small>Support console</small>
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
                  data-tip={label}
                  aria-label={label}
                  className={({ isActive }) => `nav-link ${isActive ? "nav-link-active" : ""}`}
                >
                  <Icon size={19} strokeWidth={1.9} />
                  <span className="nav-link-label">{label}</span>
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <div className="sidebar-spacer" />

        <NavLink to="/profile" onClick={onNavigate} className="sidebar-user" title={getUserName(user)}>
          <div className="avatar">{user?.photo_url ? <img src={absolutePhotoUrl(user.photo_url)} alt="" className="avatar-photo" style={{ width: "100%", height: "100%", objectFit: "cover", borderRadius: "inherit" }} /> : initials(getUserName(user))}</div>

          <div className="sidebar-user-copy">
            <b>{getUserName(user)}</b>
            <small>{user?.designation || firstRole || "Team member"}</small>
          </div>

          <UserCog size={17} />
        </NavLink>
      </aside>
    </>
  );
}

/* =========================================================
   TOPBAR
========================================================= */

export function Topbar({ user, onMenu, onLogout, theme = "light", onToggleTheme }) {
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchValue, setSearchValue] = useState("");
  const searchRef = useRef(null);
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
  const isMac = typeof navigator !== "undefined" && /mac/i.test(navigator.platform || "");

  // Ctrl/⌘ + K focuses search
  useEffect(() => {
    function onKeyDown(event) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setSearchOpen(true);
        searchRef.current?.focus();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  function submitSearch(event) {
    event.preventDefault();
    const query = searchValue.trim();
    if (query) {
      navigate(`/tickets?q=${encodeURIComponent(query)}`);
      setSearchOpen(false);
      searchRef.current?.blur();
    }
  }

  return (
    <header className="topbar">
      <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
        <button className="icon-button mobile-menu" aria-label="Toggle navigation" onClick={onMenu}>
          <Menu size={20} />
        </button>

        <div className="breadcrumb">
          <span className="crumb-root">BugPilot</span>
          <span className="crumb-slash">/</span>
          <b>{breadcrumb}</b>
        </div>
      </div>

      <div className="topbar-actions">
        <form
          className={`top-search ${searchOpen ? "top-search-open" : ""}`}
          role="search"
          aria-label="Search tickets"
          onSubmit={submitSearch}
        >
          <span className="top-search-icon"><Search size={16} /></span>

          <input
            ref={searchRef}
            aria-label="Search tickets"
            placeholder="Search tickets…"
            value={searchValue}
            onChange={(event) => setSearchValue(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                setSearchValue("");
                setSearchOpen(false);
                event.currentTarget.blur();
              }
            }}
            onFocus={() => setSearchOpen(true)}
            onBlur={() => setSearchOpen(false)}
          />

          {searchValue ? (
            <button
              type="button"
              className="top-search-clear"
              aria-label="Clear search"
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => setSearchValue("")}
            >
              ×
            </button>
          ) : (
            <kbd>{isMac ? "⌘" : "Ctrl"} K</kbd>
          )}
        </form>

        <button
          className="icon-button search-mobile"
          aria-label="Search"
          onClick={() => {
            setSearchOpen((value) => !value);
            setTimeout(() => searchRef.current?.focus(), 0);
          }}
        >
          <Search size={19} />
        </button>

        <span className="topbar-divider" />

        <button
          className="icon-button theme-toggle"
          title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          onClick={onToggleTheme}
        >
          {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
        </button>

        <NavLink to="/profile" className="topbar-user" title="Your profile">
          <div className="avatar avatar-small">{user?.photo_url ? <img src={absolutePhotoUrl(user.photo_url)} alt="" className="avatar-photo" style={{ width: "100%", height: "100%", objectFit: "cover", borderRadius: "inherit" }} /> : initials(getUserName(user))}</div>
          <div>
            <b>{getUserName(user)}</b>
            <small>
              {user?.department_name || (user?.department_id ? `Department ${user.department_id}` : "Signed in")}
            </small>
          </div>
        </NavLink>

        <button className="icon-button" title="Sign out" aria-label="Sign out" onClick={onLogout}>
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

function formatWhen(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return fmt(value);
  return date.toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function TicketTable({ tickets = [], showDescription = false, onView }) {
  const ticketList = safeArray(tickets);

  const head = (
    <thead>
      <tr>
        <th>Ticket</th>
        <th>Status</th>
        <th>Severity</th>
        <th>Updated</th>
        {onView && <th>Action</th>}
      </tr>
    </thead>
  );

  if (ticketList.length === 0) {
    return (
      <div className="table-scroll">
        <table className="data-table">
          {head}
          <tbody>
            <tr>
              <td colSpan={onView ? 5 : 4}>No tickets available.</td>
            </tr>
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div className="table-scroll">
      <table className="data-table">
        {head}
        <tbody>
          {ticketList.map((ticket, index) => {
            const id = getTicketId(ticket);

            return (
              <tr key={id === "—" ? index : id}>
                <td>
                  <div className="ticket-cell">
                    <span className="ticket-id">{ticket.ticket_code || `#${id}`}</span>
                    <b>{getTicketTitle(ticket)}</b>
                    {showDescription && ticket.description && <small>{ticket.description}</small>}
                  </div>
                </td>

                <td><StatusBadge status={getStatus(ticket)} /></td>
                  <td style={{ textTransform: "capitalize" }}>{String(fmt(ticket.severity)).toLowerCase()}</td>
                <td className="muted-cell">{formatWhen(ticket.updated_at || ticket.created_at)}</td>

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
    typeof body === "string" && body.trim() ? body : "No information returned for this field.";

  return (
    <div className="result-block">
      <h3>{title}</h3>
      <p>{content}</p>
    </div>
  );
}
