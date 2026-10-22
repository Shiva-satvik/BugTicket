import api from "./axios";

export function errorMessage(error, fallback = "Something went wrong.") {
  const data = error?.response?.data;
  const detail = data?.detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => {
      if (typeof item === "string") return item;
      const loc = Array.isArray(item?.loc)
        ? item.loc.filter((part) => part !== "body").join(".")
        : "";
      const msg = item?.msg || "Invalid input";
      return loc ? `${loc}: ${msg}` : msg;
    }).join("; ");
  }
  if (typeof detail === "string") return detail;
  if (typeof data?.message === "string") return data.message;
  if (typeof data?.error === "string") return data.error;
  if (typeof error?.message === "string") return error.message;
  return fallback;
}

export const authService = {
  login: (credentials) => api.post("/auth/login", credentials),
  me: () => api.get("/auth/me"),
};
export const authApi = authService;

export const ticketService = {
  // The AI pipeline makes 3 sequential LLM calls on the backend and can
  // legitimately take longer than the global 5-minute axios timeout,
  // so this endpoint gets its own extended limit (15 minutes).
  analyze: (ticket) =>
    api.post("/api/tickets/analyze", { ticket }, { timeout: 900000 }),
  getAll: (params = {}) => api.get("/api/tickets", { params }),
  getById: (ticketId) => api.get(`/api/tickets/${ticketId}`),
};
export const ticketApi = ticketService;

export const enterpriseTicketService = {
  getAll: (params = {}) => api.get("/api/enterprise/tickets/", { params }),
  create: (payload) => api.post("/api/enterprise/tickets/", payload),
  getById: (ticketId) => api.get(`/api/enterprise/tickets/${ticketId}`),
  getHistory: (ticketId) => api.get(`/api/enterprise/tickets/${ticketId}/history`),
};
export const enterpriseTicketApi = enterpriseTicketService;

export const analyticsService = {
  getDashboard: () => api.get("/api/analytics/dashboard"),
  getTimeline: (period = "weekly", limit = 12) =>
    api.get("/api/analytics/timeline", { params: { period, limit } }),
  getBreakdowns: () => api.get("/api/analytics/breakdowns"),
  getAccessAnalytics: () => api.get("/api/analytics/access"),
};
export const analyticsApi = analyticsService;

export const healthService = {
  check: () => api.get("/health"),
};

export const adminService = {
  getUsers: () => api.get("/api/admin/users"),
  getDepartments: () => api.get("/api/enterprise/departments/"),
};
