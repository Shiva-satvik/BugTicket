import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import Dashboard from "./pages/Dashboard.jsx";
import LoginPage from "./pages/Login.jsx";
import TicketsPage from "./pages/Tickets.jsx";
import CreateTicketPage from "./pages/CreateTicket.jsx";
import AIAnalysisPage from "./pages/AIAnalysis.jsx";
import AnalyticsPage from "./pages/Analytics.jsx";
import ProfilePage from "./pages/Profile.jsx";
import EmployeesPage from "./pages/Employees.jsx";

import { Sidebar, Topbar } from "./components/Common.jsx";

const STORAGE_KEY = "bugpilot_user";
const THEME_KEY = "bugpilot_theme_v3";
const SIDEBAR_KEY = "bugpilot_sidebar_collapsed";

function readUser() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored ? JSON.parse(stored) : null;
  } catch {
    return null;
  }
}

function readTheme() {
  try {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    /* storage unavailable */
  }
  // Follow the operating-system preference on first visit.
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function readCollapsed() {
  try {
    return localStorage.getItem(SIDEBAR_KEY) === "1";
  } catch {
    return false;
  }
}

function App() {
  const [user, setUser] = useState(readUser);

  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(readCollapsed);
  const [theme, setTheme] = useState(readTheme);

  // Apply the theme to <html> so every screen (including login) is themed.
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch {
      /* ignore */
    }
  }, [theme]);

  // Remember the sidebar state between visits.
  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_KEY, sidebarCollapsed ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, [sidebarCollapsed]);

  // Ctrl/⌘ + B toggles the sidebar; Escape closes the mobile drawer.
  useEffect(() => {
    function onKeyDown(event) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "b") {
        event.preventDefault();
        setSidebarCollapsed((value) => !value);
      }
      if (event.key === "Escape") setSidebarOpen(false);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  // Refresh the authenticated user's information.
  useEffect(() => {
    const token =
      localStorage.getItem("bugpilot_token") ||
      localStorage.getItem("bugpilot_access_token") ||
      localStorage.getItem("access_token") ||
      localStorage.getItem("token");

    if (!user || !token) return;

    import("./api/services")
      .then(({ authApi }) => authApi.me())
      .then(({ data }) => {
        const refreshed = { ...user, ...(data || {}) };
        setUser(refreshed);
        localStorage.setItem(STORAGE_KEY, JSON.stringify(refreshed));
      })
      .catch(() => {
        // Preserve the current session if the refresh request fails.
      });

    // Refresh when a user session first becomes available (including after login).
  }, [user?.employee_id]);

  function toggleTheme() {
    setTheme((value) => (value === "light" ? "dark" : "light"));
  }

  // Handle successful login.
  function handleLogin(userData) {
    setUser(userData);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(userData));
  }

  // Clear the local session on logout.
  function handleLogout() {
    setUser(null);

    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem("bugpilot_token");
    localStorage.removeItem("bugpilot_access_token");
    localStorage.removeItem("access_token");
    localStorage.removeItem("token");
  }

  // Show login when no user session exists.
  if (!user) {
    return <LoginPage onLogin={handleLogin} theme={theme} onToggleTheme={toggleTheme} />;
  }

  // Determine whether the current user has administrator access.
  const roles = [
    ...(Array.isArray(user?.roles) ? user.roles : []),
    ...(user?.role ? [user.role] : []),
  ];

  const isAdmin = roles.some((role) => {
    const roleName = typeof role === "object" ? role?.name || role?.role || "" : role;
    return String(roleName).toUpperCase() === "ADMIN";
  });

  return (
    <div className="app-shell" data-theme={theme}>
      <Sidebar
        user={user}
        open={sidebarOpen}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed((value) => !value)}
        onNavigate={() => setSidebarOpen(false)}
      />

      <div className="app-main">
        <Topbar
          user={user}
          onMenu={() => setSidebarOpen((open) => !open)}
          onLogout={handleLogout}
          theme={theme}
          onToggleTheme={toggleTheme}
        />

        <main className="page-content">
          <Routes>
            <Route path="/" element={<Dashboard user={user} />} />
            <Route path="/tickets" element={<TicketsPage user={user} />} />
            <Route path="/tickets/new" element={<CreateTicketPage user={user} />} />
            <Route path="/ai-analysis" element={<AIAnalysisPage user={user} />} />
            <Route path="/analytics" element={<AnalyticsPage user={user} />} />
            <Route path="/profile" element={<ProfilePage user={user} onUserUpdated={(updatedUser) => {
              const refreshed = { ...user, ...updatedUser };
              setUser(refreshed);
              localStorage.setItem(STORAGE_KEY, JSON.stringify(refreshed));
            }} />} />
            <Route
              path="/employees"
              element={isAdmin ? <EmployeesPage user={user} /> : <Navigate to="/" replace />}
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

export default App;
