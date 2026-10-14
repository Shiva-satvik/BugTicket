import { useEffect, useState } from "react";

import { AlertCircle, CheckCircle2, Plus, ShieldCheck } from "lucide-react";

import { useNavigate } from "react-router-dom";

import { enterpriseTicketApi, errorMessage } from "../api/services";

import { PageHeader } from "../components/Common.jsx";

export default function CreateTicketPage({ user }) {
  const [form, setForm] = useState({
    title: "",
    description: "",
    department_id: user?.department_id || "",
    module: "",
    category: "ERP",
    issue_type: "BUG",
    severity: "MEDIUM",
    priority: "MEDIUM",
  });

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(null);

  const navigate = useNavigate();

  // Populate the department ID from the logged-in user
  useEffect(() => {
    if (user?.department_id) {
      setForm((previous) => ({
        ...previous,
        department_id: previous.department_id || user.department_id,
      }));
    }
  }, [user]);

  function handleChange(event) {
    const { name, value } = event.target;

    setForm((previous) => ({
      ...previous,
      [name]: value,
    }));
  }

  async function submit(event) {
    event.preventDefault();

    if (busy) return;

    setBusy(true);
    setError("");
    setSuccess(null);

    const departmentId = Number(form.department_id);

    if (!Number.isInteger(departmentId) || departmentId <= 0) {
      setError(
        "Your account has no valid department ID. Ask your administrator to check your user profile.",
      );
      setBusy(false);
      return;
    }

    if (!form.title.trim() || !form.description.trim()) {
      setError("Please provide both a ticket title and description.");
      setBusy(false);
      return;
    }

    try {
      const payload = {
        ...form,
        title: form.title.trim(),
        description: form.description.trim(),
        module: form.module.trim(),
        department_id: departmentId,
      };

      const { data } = await enterpriseTicketApi.create(payload);

      setSuccess(data ?? { success: true });

      // Redirect after successful creation
      window.setTimeout(() => {
        navigate("/tickets");
      }, 1200);
    } catch (err) {
      setError(errorMessage(err, "Ticket creation failed. Please try again."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="WORK MANAGEMENT"
        title="Create a ticket"
        description="Capture the issue clearly so the right team can act."
        action={
          <button
            type="button"
            className="button button-secondary"
            onClick={() => navigate("/tickets")}
          >
            Cancel
          </button>
        }
      />

      <div className="form-layout">
        <form className="panel form-panel" onSubmit={submit}>
          {/* Section heading */}
          <div className="form-section-title">
            <span className="section-number">01</span>

            <div>
              <h2>Issue details</h2>
              <p>Describe what happened and where.</p>
            </div>
          </div>

          {/* Error message */}
          {error && (
            <div className="alert alert-error" role="alert">
              <AlertCircle size={17} />
              <span>{error}</span>
            </div>
          )}

          {busy && (
            <div className="alert alert-info" role="status">
              <span className="spinner" />
              <span>Creating ticket… saving it to your workspace and preparing ticket history.</span>
            </div>
          )}

          {/* Success message */}
          {success && (
            <div className="alert alert-success" role="status">
              <CheckCircle2 size={17} />
              <span>Ticket created successfully. Opening ticket list…</span>
            </div>
          )}

          {/* Ticket title */}
          <label htmlFor="ticket-title">
            Ticket title <span className="required">*</span>
          </label>

          <input
            id="ticket-title"
            name="title"
            className="text-input"
            value={form.title}
            onChange={handleChange}
            maxLength={200}
            placeholder="e.g. Payroll export fails at month end"
            required
            disabled={busy || !!success}
          />

          {/* Description */}
          <label htmlFor="ticket-description">
            Description <span className="required">*</span>
          </label>

          <textarea
            id="ticket-description"
            name="description"
            className="text-input textarea"
            value={form.description}
            onChange={handleChange}
            maxLength={10000}
            placeholder="What were you trying to do? What happened instead? Include any error message."
            required
            disabled={busy || !!success}
          />

          {/* Additional fields */}
          <div className="form-grid">
            <div>
              <label htmlFor="department">
                Department ID <span className="required">*</span>
              </label>

              <input
                id="department"
                name="department_id"
                className="text-input"
                type="number"
                min="1"
                step="1"
                value={form.department_id}
                onChange={handleChange}
                required
                disabled={busy || !!success}
              />
            </div>

            <div>
              <label htmlFor="module">ERP module</label>

              <input
                id="module"
                name="module"
                className="text-input"
                value={form.module}
                onChange={handleChange}
                placeholder="e.g. Payroll"
                disabled={busy || !!success}
              />
            </div>

            <div>
              <label htmlFor="category">Category</label>

              <select
                id="category"
                name="category"
                className="text-input"
                value={form.category}
                onChange={handleChange}
                disabled={busy || !!success}
              >
                <option value="ERP">ERP</option>
                <option value="Finance">Finance</option>
                <option value="Payroll">Payroll</option>
                <option value="Access">Access</option>
                <option value="Reporting">Reporting</option>
                <option value="Other">Other</option>
              </select>
            </div>

            <div>
              <label htmlFor="issue-type">Issue type</label>

              <select
                id="issue-type"
                name="issue_type"
                className="text-input"
                value={form.issue_type}
                onChange={handleChange}
                disabled={busy || !!success}
              >
                <option value="BUG">Bug</option>
                <option value="INCIDENT">Incident</option>
                <option value="REQUEST">Request</option>
                <option value="ACCESS">Access</option>
              </select>
            </div>

            <div>
              <label htmlFor="severity">Severity</label>

              <select
                id="severity"
                name="severity"
                className="text-input"
                value={form.severity}
                onChange={handleChange}
                disabled={busy || !!success}
              >
                {["LOW", "MEDIUM", "HIGH", "CRITICAL"].map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label htmlFor="priority">Priority</label>

              <select
                id="priority"
                name="priority"
                className="text-input"
                value={form.priority}
                onChange={handleChange}
                disabled={busy || !!success}
              >
                {["LOW", "MEDIUM", "HIGH", "CRITICAL"].map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Form actions */}
          <div className="form-actions">
            <span className="muted-cell">
              <span className="required">*</span> Required fields
            </span>

            <button
              type="submit"
              className="button button-primary"
              disabled={busy || !!success}
            >
              {busy ? (
                <>
                  <span className="spinner" />
                  Creating…
                </>
              ) : (
                <>
                  <Plus size={17} />
                  Create ticket
                </>
              )}
            </button>
          </div>
        </form>

        {/* Helpful information */}
        <aside className="panel form-aside">
          <div className="aside-icon">
            <ShieldCheck size={21} />
          </div>

          <h3>Ticket visibility</h3>

          <p>
            BugPilot applies department and role-based access rules on the
            server. Your account can only create tickets within the scope
            permitted by your role.
          </p>

          <div className="aside-divider" />

          <h4>Helpful details to include</h4>

          <ul>
            <li>ERP module and action attempted</li>
            <li>Steps to reproduce the issue</li>
            <li>Expected versus actual result</li>
            <li>Exact error text, if available</li>
          </ul>
        </aside>
      </div>
    </>
  );
}
