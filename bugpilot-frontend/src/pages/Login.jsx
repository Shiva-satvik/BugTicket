import { useState } from "react";

import {
  ArrowRight,
  BarChart3,
  Eye,
  EyeOff,
  LockKeyhole,
  Moon,
  ShieldCheck,
  Sparkles,
  Sun,
  AlertCircle,
  UserRound,
} from "lucide-react";

import { authApi, errorMessage } from "../api/services";

export default function LoginPage({ onLogin, theme = "light", onToggleTheme }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");

    if (!username.trim() || !password) {
      setError("Please enter your username and password.");
      return;
    }

    setLoading(true);

    try {
      const response = await authApi.login({
        username: username.trim(),
        password,
      });

      const data = response?.data ?? response;

      const token = data?.access_token ?? data?.token ?? data?.accessToken;

      if (!token) {
        throw new Error("The login response did not contain an authentication token.");
      }

      // Store the token using the key expected by the app.
      localStorage.setItem("bugpilot_token", token);

      // Fetch the canonical user profile and role assignments after login.
      let userData = data.user ?? data;
      try {
        const profileResponse = await authApi.me();
        userData = { ...userData, ...(profileResponse?.data || {}) };
      } catch {
        // Login can still proceed if an older backend does not expose /auth/me.
      }

      if (typeof onLogin === "function") {
        await onLogin(userData);
      }
    } catch (err) {
      setError(
        errorMessage(
          err,
          err?.response?.data?.detail ||
            err?.message ||
            "Login failed. Check your credentials and try again.",
        ),
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-page">
      {/* Branding panel */}
      <section className="login-brand-panel">
        <div className="login-brand">
          <div className="login-logo">
            <Sparkles size={22} />
          </div>
          <span>BugPilot</span>
        </div>

        <div className="login-intro">
          <span className="login-eyebrow">
            <Sparkles size={14} />
            AI-POWERED TICKET INTELLIGENCE
          </span>

          <h1>
            Resolve issues.
            <br />
            <span>Move forward.</span>
          </h1>

          <p>
            Intelligent ticket analysis, historical issue discovery, and
            context-aware resolution suggestions for your team.
          </p>
        </div>

        <div className="login-features">
          <div className="login-feature">
            <div className="login-feature-icon">
              <ShieldCheck size={20} />
            </div>
            <div>
              <strong>Secure access</strong>
              <p>Role-based access for your team</p>
            </div>
          </div>

          <div className="login-feature">
            <div className="login-feature-icon">
              <BarChart3 size={20} />
            </div>
            <div>
              <strong>Actionable insights</strong>
              <p>Understand ticket trends and priorities</p>
            </div>
          </div>
        </div>

        <p className="login-footer">BugPilot · Intelligent Enterprise Support</p>
      </section>

      {/* Login form */}
      <section className="login-form-panel">
        {onToggleTheme && (
          <button
            type="button"
            className="icon-button theme-toggle login-theme-toggle"
            onClick={onToggleTheme}
            aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
            title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          >
            {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
          </button>
        )}

        <div className="login-form-container">
          <div className="login-mobile-brand">
            <div className="login-logo">
              <Sparkles size={21} />
            </div>
            <span>BugPilot</span>
          </div>

          <div className="login-heading">
            <span className="login-welcome">WELCOME BACK</span>
            <h2>Sign in to BugPilot</h2>
            <p>Enter your credentials to access BugPilot.</p>
          </div>

          <form onSubmit={handleSubmit} className="login-form">
            {error && (
              <div className="login-error" role="alert">
                <AlertCircle size={18} />
                <span>{error}</span>
              </div>
            )}

            <div className="login-field">
              <label htmlFor="username">Username</label>

              <div className="login-input-wrap">
                <UserRound size={19} />
                <input
                  id="username"
                  name="username"
                  type="text"
                  autoComplete="username"
                  placeholder="Enter your username"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  required
                />
              </div>
            </div>

            <div className="login-field">
              <label htmlFor="password">Password</label>

              <div className="login-input-wrap">
                <LockKeyhole size={19} />
                <input
                  id="password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  placeholder="Enter your password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                />

                <button
                  type="button"
                  className="login-password-toggle"
                  onClick={() => setShowPassword((visible) => !visible)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            <button type="submit" className="login-submit" disabled={loading}>
              {loading ? "Signing in..." : "Sign in"}
              {!loading && <ArrowRight size={19} />}
            </button>
          </form>

          <div className="login-security-note">
            <ShieldCheck size={17} />
            <span>Your access is protected by secure authentication.</span>
          </div>
        </div>
      </section>
    </main>
  );
}
