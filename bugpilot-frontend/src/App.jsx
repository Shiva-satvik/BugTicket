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
import "./App.css";

const STORAGE_KEY = "bugpilot_user";

function readUser() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored ? JSON.parse(stored) : null;
  } catch {
    return null;
  }
}

function App() {
  const [user, setUser] = useState(readUser);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [theme, setTheme] = useState(() => localStorage.getItem("bugpilot_theme") || "light");

  useEffect(() => {
    localStorage.setItem("bugpilot_theme", theme);
  }, [theme]);

  useEffect(() => {
    const token = localStorage.getItem("bugpilot_token");
    if (!user || !token) return;
    import("./api/services").then(({ authApi }) => {
      authApi.me().then(({ data }) => {
        const refreshed = { ...user, ...(data || {}) };
        setUser(refreshed);
        localStorage.setItem(STORAGE_KEY, JSON.stringify(refreshed));
      }).catch(() => {});
    });
  // Refresh once per stored session; login itself also fetches /auth/me.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleLogin(userData) {
    setUser(userData);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(userData));
  }

  function handleLogout() {
    setUser(null);
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem("bugpilot_token");
    localStorage.removeItem("bugpilot_access_token");
    localStorage.removeItem("access_token");
    localStorage.removeItem("token");
  }

  if (!user) {
    return <LoginPage onLogin={handleLogin} />;
  }

  return (
    <div className="app-shell" data-theme={theme}>
      <Sidebar
        user={user}
        open={sidebarOpen}
        onNavigate={() => setSidebarOpen(false)}
      />

      <div className="app-main">
        <Topbar
          user={user}
          onMenu={() => setSidebarOpen((open) => !open)}
          onLogout={handleLogout}
          theme={theme}
          onToggleTheme={() => setTheme((value) => value === "light" ? "dark" : "light")}
        />

        <main className="page-content">
          <Routes>
            <Route path="/" element={<Dashboard user={user} />} />

            <Route path="/tickets" element={<TicketsPage user={user} />} />

            <Route
              path="/tickets/new"
              element={<CreateTicketPage user={user} />}
            />

            <Route
              path="/ai-analysis"
              element={<AIAnalysisPage user={user} />}
            />

            <Route path="/analytics" element={<AnalyticsPage user={user} />} />

            <Route path="/profile" element={<ProfilePage user={user} />} />

            <Route
              path="/employees"
              element={
                ([
                  ...(Array.isArray(user?.roles) ? user.roles : []),
                  ...(user?.role ? [user.role] : []),
                ].some((role) =>
                  String(typeof role === "object" ? (role.name || role.role || "") : role).toUpperCase() === "ADMIN"
                ))
                  ? <EmployeesPage user={user} />
                  : <Navigate to="/" replace />
              }
            />

            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

export default App;
