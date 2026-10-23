
import api from "./axios";

// --------------------------------------------------
// ERROR HANDLING
// --------------------------------------------------

export function errorMessage(error, fallback = "Something went wrong.") {
  const data = error?.response?.data;
  const detail = data?.detail;

  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item;

        const loc = Array.isArray(item?.loc)
          ? item.loc.filter((part) => part !== "body").join(".")
          : "";

        const msg = item?.msg || "Invalid input";
        return loc ? `${loc}: ${msg}` : msg;
      })
      .join("; ");
  }

  if (typeof detail === "string") return detail;
  if (typeof data?.message === "string") return data.message;
  if (typeof data?.error === "string") return data.error;
  if (typeof error?.message === "string") return error.message;

  return fallback;
}

// --------------------------------------------------
// AUTHENTICATION & PROFILE
// --------------------------------------------------

export const authService = {
  login: (credentials) => api.post("/auth/login", credentials),

  me: () => api.get("/auth/me"),

  // Upload the image as raw binary.
  // The FastAPI endpoint reads the raw request body.
  uploadPhoto: (file) => {
    if (!(file instanceof File)) {
      return Promise.reject(new Error("Please select a valid image file."));
    }

    return api.put("/auth/profile/photo", file, {
      headers: {
        "Content-Type": file.type,
      },
      timeout: 30000,
    });
  },

  // Remove the currently authenticated user's photo.
  removePhoto: () => api.delete("/auth/profile/photo"),
};

export const authApi = authService;

// --------------------------------------------------
// AI TICKET ANALYSIS
// --------------------------------------------------

export const ticketService = {
  // AI analysis may require multiple sequential LLM calls.
  analyze: (ticket) =>
    api.post(
      "/api/tickets/analyze",
      { ticket },
      { timeout: 900000 }
    ),

  getAll: (params = {}) =>
    api.get("/api/tickets", { params }),

  getById: (ticketId) =>
    api.get(`/api/tickets/${ticketId}`),
};

export const ticketApi = ticketService;

// --------------------------------------------------
// ENTERPRISE TICKET MANAGEMENT
// --------------------------------------------------

export const enterpriseTicketService = {
  getAll: (params = {}) =>
    api.get("/api/enterprise/tickets/", { params }),

  create: (payload) =>
    api.post("/api/enterprise/tickets/", payload),

  getById: (ticketId) =>
    api.get(`/api/enterprise/tickets/${ticketId}`),

  getHistory: (ticketId) =>
    api.get(`/api/enterprise/tickets/${ticketId}/history`),
};

export const enterpriseTicketApi = enterpriseTicketService;

// --------------------------------------------------
// ANALYTICS
// --------------------------------------------------

export const analyticsService = {
  getDashboard: () =>
    api.get("/api/analytics/dashboard"),

  getTimeline: (period = "weekly", limit = 12) =>
    api.get("/api/analytics/timeline", {
      params: { period, limit },
    }),

  getBreakdowns: () =>
    api.get("/api/analytics/breakdowns"),

  getAccessAnalytics: () =>
    api.get("/api/analytics/access"),
};

export const analyticsApi = analyticsService;

// --------------------------------------------------
// HEALTH CHECK
// --------------------------------------------------

export const healthService = {
  check: () => api.get("/health"),
};

// --------------------------------------------------
// ADMINISTRATION
// --------------------------------------------------

export const adminService = {
  getUsers: () =>
    api.get("/api/admin/users"),

  getDepartments: () =>
    api.get("/api/enterprise/departments/"),
};
