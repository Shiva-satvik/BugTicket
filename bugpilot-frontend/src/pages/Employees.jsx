import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  Building2,
  RefreshCw,
  Search,
  ShieldCheck,
  UserCheck,
  Users,
} from "lucide-react";

import { adminService, errorMessage } from "../api/services";
import { safeArray } from "../utils";
import { EmptyState, LoadingPanel, PageHeader } from "../components/Common.jsx";

function normalize(value) {
  return String(value ?? "").trim().toLowerCase();
}

function getRoles(entry) {
  if (Array.isArray(entry?.roles)) {
    const names = entry.roles
      .map((role) => (typeof role === "object" ? role.name || role.role || "" : role))
      .filter(Boolean)
      .join(", ");
    return names || "Unassigned";
  }
  return entry?.role || "Unassigned";
}

function EmployeesPage() {
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [department, setDepartment] = useState("all");
  const [status, setStatus] = useState("all");

  const loadEmployees = useCallback(async (quiet = false) => {
    if (quiet) setRefreshing(true);
    else setLoading(true);
    setError("");

    try {
      const response = await adminService.getUsers();
      const data = response?.data;
      setEmployees(safeArray(data?.users ?? data?.items ?? data?.data ?? data));
    } catch (err) {
      setError(errorMessage(err, "Employee directory could not be loaded."));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadEmployees();
  }, [loadEmployees]);

  const departments = useMemo(() => {
    return [...new Set(employees.map((entry) => entry.department_name || entry.department_id).filter(Boolean))]
      .sort((a, b) => String(a).localeCompare(String(b)));
  }, [employees]);

  const filteredEmployees = useMemo(() => {
    return employees.filter((entry) => {
      const searchable = [
        entry.full_name, entry.username, entry.email, entry.employee_id,
        entry.department_name, entry.department_id, getRoles(entry),
      ].map(normalize).join(" ");
      const matchesQuery = !query.trim() || searchable.includes(normalize(query));
      const departmentValue = String(entry.department_name || entry.department_id || "");
      const matchesDepartment = department === "all" || departmentValue === department;
      const isActive = Boolean(entry.is_active);
      const matchesStatus = status === "all" || (status === "active" ? isActive : !isActive);
      return matchesQuery && matchesDepartment && matchesStatus;
    });
  }, [employees, query, department, status]);

  const activeCount = employees.filter((entry) => Boolean(entry.is_active)).length;
  const departmentCount = departments.length;

  return (
    <>
      <PageHeader
        eyebrow="ADMINISTRATION"
        title="Employees"
        description="Manage visibility of employee accounts across departments, roles, and account status."
        action={
          <button
            type="button"
            className="button button-secondary"
            onClick={() => loadEmployees(true)}
            disabled={refreshing}
          >
            <RefreshCw size={15} className={refreshing ? "spin" : ""} />
            {refreshing ? "Refreshing…" : "Refresh directory"}
          </button>
        }
      />

      {error && (
        <div className="alert alert-warning employees-alert">
          <AlertCircle size={17} />
          <span>{error}</span>
          <button type="button" className="button button-secondary button-small" onClick={() => loadEmployees(true)}>
            Retry
          </button>
        </div>
      )}

      {!loading && !error && (
        <section className="employees-summary-grid">
          <article className="employees-summary-card">
            <span className="employees-summary-icon employees-summary-icon-teal"><Users size={20} /></span>
            <div><span>Total employees</span><strong>{employees.length.toLocaleString()}</strong><small>Accounts in directory</small></div>
          </article>
          <article className="employees-summary-card">
            <span className="employees-summary-icon employees-summary-icon-green"><UserCheck size={20} /></span>
            <div><span>Active accounts</span><strong>{activeCount.toLocaleString()}</strong><small>{employees.length ? Math.round(activeCount / employees.length * 100) : 0}% of directory</small></div>
          </article>
          <article className="employees-summary-card">
            <span className="employees-summary-icon employees-summary-icon-blue"><Building2 size={20} /></span>
            <div><span>Departments</span><strong>{departmentCount.toLocaleString()}</strong><small>Represented in directory</small></div>
          </article>
        </section>
      )}

      <section className="panel employees-directory-panel">
        <div className="employees-directory-heading">
          <div>
            <span className="eyebrow">EMPLOYEE DIRECTORY</span>
            <h2>Employee accounts</h2>
            <p>Search employees by name, email, employee ID, department, or role.</p>
          </div>
          <span className="employees-result-count">{filteredEmployees.length.toLocaleString()} results</span>
        </div>

        <div className="employees-filters">
          <label className="employees-search">
            <Search size={17} />
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search name, email, ID, or role…"
              aria-label="Search employees"
            />
          </label>

          <label className="employees-filter">
            <span>Department</span>
            <select value={department} onChange={(event) => setDepartment(event.target.value)}>
              <option value="all">All departments</option>
              {departments.map((item) => <option key={item} value={String(item)}>{item}</option>)}
            </select>
          </label>

          <label className="employees-filter">
            <span>Account status</span>
            <select value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="all">All statuses</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
          </label>
        </div>

        {loading ? <LoadingPanel label="Loading employee directory…" /> : (
          <div className="table-scroll employees-table-scroll">
            <table className="data-table employees-table">
              <thead>
                <tr>
                  <th>Employee</th>
                  <th>Employee ID</th>
                  <th>Email</th>
                  <th>Department</th>
                  <th>Role(s)</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {filteredEmployees.map((entry, index) => {
                  const active = Boolean(entry.is_active);
                  const displayName = entry.full_name || entry.username || "Unnamed employee";
                  return (
                    <tr key={entry.employee_id || entry.id || entry.username || index}>
                      <td>
                        <div className="employees-person">
                          <span className="employees-avatar">
                            {String(displayName).split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase()}
                          </span>
                          <span className="employees-person-copy">
                            <strong>{displayName}</strong>
                            {entry.username && entry.full_name && <small>@{entry.username}</small>}
                          </span>
                        </div>
                      </td>
                      <td>
                        {entry.employee_id
                          ? <span className="employees-id">{entry.employee_id}</span>
                          : <span className="muted-cell">—</span>}
                      </td>
                      <td className="employees-email">
                        {entry.email
                          ? <a href={`mailto:${entry.email}`}>{entry.email}</a>
                          : <span className="muted-cell">—</span>}
                      </td>
                      <td>{entry.department_name || entry.department_id || "—"}</td>
                      <td><span className="employees-role">{getRoles(entry)}</span></td>
                      <td><span className={`employees-status ${active ? "is-active" : "is-inactive"}`}><span />{active ? "Active" : "Inactive"}</span></td>
                    </tr>
                  );
                })}
                {!filteredEmployees.length && (
                  <tr><td colSpan={6}>
                    <EmptyState icon={ShieldCheck} title="No employees found" body="Try changing the search term or clearing the selected filters." />
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

export default EmployeesPage;
