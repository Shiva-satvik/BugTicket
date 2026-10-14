import axios from "axios";

const api = axios.create({
  baseURL: (
    import.meta.env.VITE_API_BASE_URL ||
    "http://127.0.0.1:8000"
  ).replace(/\/+$/, ""),
  timeout: 300000,
  headers: {
    "Content-Type": "application/json",
  },
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("bugpilot_token");

  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401) {
      const url = String(error?.config?.url || "");

      if (!url.includes("/auth/login")) {
        localStorage.removeItem("bugpilot_token");
        localStorage.removeItem("bugpilot_access_token");
        localStorage.removeItem("bugpilot_user");
      }
    }

    return Promise.reject(error);
  }
);

export default api;