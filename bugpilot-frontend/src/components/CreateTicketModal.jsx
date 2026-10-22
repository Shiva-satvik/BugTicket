import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { AlertCircle, CheckCircle2, Plus, X } from "lucide-react";
import { enterpriseTicketApi, errorMessage } from "../api/services";

const INITIAL_FORM = {
  title: "",
  description: "",
  module: "",
  category: "ERP",
  issue_type: "BUG",
  severity: "MEDIUM",
  priority: "MEDIUM",
};

export default function CreateTicketModal({ user, onClose, onCreated }) {
  const [form, setForm] = useState(INITIAL_FORM);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    function onKeyDown(event) {
      if (event.key === "Escape" && !busy) onClose?.();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [busy, onClose]);

  function update(event) {
    const { name, value } = event.target;
    setForm((previous) => ({ ...previous, [name]: value }));
  }

  async function submit(event) {
    event.preventDefault();
    setError("");
    const departmentId = Number(user?.department_id);
    if (!Number.isInteger(departmentId) || departmentId <= 0) {
      setError("Your account has no valid department. Ask an administrator to update your profile.");
      return;
    }
    if (!form.title.trim() || !form.description.trim()) {
      setError("Enter a title and description before creating the ticket.");
      return;
    }

    setBusy(true);
    try {
      const { data } = await enterpriseTicketApi.create({
        ...form,
        title: form.title.trim(),
        description: form.description.trim(),
        module: form.module.trim() || null,
        department_id: departmentId,
      });
      setSuccess(true);
      await onCreated?.(data);
      window.setTimeout(() => onClose?.(), 700);
    } catch (err) {
      setError(errorMessage(err, "Ticket creation failed. Please try again."));
    } finally {
      setBusy(false);
    }
  }

  return createPortal(
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget && !busy) onClose?.();
    }}>
      <section className="ticket-modal create-ticket-modal panel" role="dialog" aria-modal="true" aria-labelledby="create-ticket-modal-title">
        <div className="panel-heading">
          <div>
            <div className="eyebrow">WORK MANAGEMENT</div>
            <h2 id="create-ticket-modal-title">Create a ticket</h2>
            <p>Capture the issue clearly so it can be routed and tracked.</p>
          </div>
          <button type="button" className="icon-button border-button" onClick={onClose} disabled={busy} aria-label="Close create ticket dialog"><X size={18} /></button>
        </div>

        {error && <div className="alert alert-error" role="alert"><AlertCircle size={17} /><span>{error}</span></div>}
        {success && <div className="alert alert-success" role="status"><CheckCircle2 size={17} /><span>Ticket created successfully. Refreshing your workspace…</span></div>}

        <form onSubmit={submit}>
          <label htmlFor="modal-ticket-title">Ticket title <span className="required">*</span></label>
          <input id="modal-ticket-title" className="text-input" name="title" value={form.title} onChange={update} maxLength={200} placeholder="e.g. Payroll export fails for monthly reports" required />

          <label htmlFor="modal-ticket-description">Description <span className="required">*</span></label>
          <textarea id="modal-ticket-description" className="text-input" name="description" value={form.description} onChange={update} maxLength={10000} rows={4} placeholder="Describe what happened, the steps to reproduce it, and the impact…" required />

          <div className="form-grid">
            <div>
              <label htmlFor="modal-ticket-department">Department</label>
              <input id="modal-ticket-department" className="text-input" value={user?.department_name || `Department ${user?.department_id || "not set"}`} readOnly />
            </div>
            <div>
              <label htmlFor="modal-ticket-module">ERP module</label>
              <input id="modal-ticket-module" className="text-input" name="module" value={form.module} onChange={update} placeholder="Payroll, Finance, HR…" maxLength={100} />
            </div>
            <div>
              <label htmlFor="modal-ticket-category">Category</label>
              <select id="modal-ticket-category" className="text-input" name="category" value={form.category} onChange={update}>
                <option value="ERP">ERP</option><option value="Access">Access</option><option value="Data">Data</option><option value="Integration">Integration</option><option value="Performance">Performance</option><option value="Reporting">Reporting</option>
              </select>
            </div>
            <div>
              <label htmlFor="modal-ticket-type">Issue type</label>
              <select id="modal-ticket-type" className="text-input" name="issue_type" value={form.issue_type} onChange={update}>
                <option value="BUG">Bug</option><option value="INCIDENT">Incident</option><option value="SERVICE_REQUEST">Service request</option><option value="ACCESS_REQUEST">Access request</option>
              </select>
            </div>
            <div>
              <label htmlFor="modal-ticket-severity">Severity</label>
              <select id="modal-ticket-severity" className="text-input" name="severity" value={form.severity} onChange={update}>
                <option value="LOW">Low</option><option value="MEDIUM">Medium</option><option value="HIGH">High</option><option value="CRITICAL">Critical</option><option value="URGENT">Urgent</option>
              </select>
            </div>
            <div>
              <label htmlFor="modal-ticket-priority">Priority</label>
              <select id="modal-ticket-priority" className="text-input" name="priority" value={form.priority} onChange={update}>
                <option value="LOW">Low</option><option value="MEDIUM">Medium</option><option value="HIGH">High</option><option value="CRITICAL">Critical</option><option value="URGENT">Urgent</option>
              </select>
            </div>
          </div>

          <div className="modal-actions">
            <button type="button" className="button button-secondary" onClick={onClose} disabled={busy}>Cancel</button>
            <button type="submit" className="button button-primary" disabled={busy || success}>
              {busy ? <span className="spinner" /> : <Plus size={16} />}
              {busy ? "Creating…" : "Create ticket"}
            </button>
          </div>
        </form>
      </section>
    </div>,
    document.body
  );
}
