import axios, { AxiosError, AxiosResponse, InternalAxiosRequestConfig } from "axios";

const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export const apiClient = axios.create({
  baseURL: `${BASE_URL}/api/v1`,
  timeout: 0, // no default — each call sets its own timeout
});

// Request interceptor
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    return config;
  },
  (error: AxiosError) => {
    console.error("[API Request Error]", error);
    return Promise.reject(error);
  }
);

// Response interceptor
apiClient.interceptors.response.use(
  (response: AxiosResponse) => response,
  (error: AxiosError<{ error?: string; detail?: string; code?: string }>) => {
    if (error.response) {
      const { status, data } = error.response;
      const message = data?.error || data?.detail || "An unexpected error occurred";
      console.error(`[API Error ${status}]`, message, data);

      const apiError = new Error(
        status === 422 ? `Validation error: ${message}` : status >= 500 ? `Server error: ${message}` : message
      ) as Error & { status: number };
      apiError.status = status;
      return Promise.reject(apiError);
    }

    if (error.code === "ECONNABORTED") {
      return Promise.reject(new Error("Request timed out. Please try again."));
    }
    if (!error.response) {
      return Promise.reject(
        new Error("Cannot connect to the backend server. Please ensure it is running.")
      );
    }
    return Promise.reject(error);
  }
);

export const WS_BASE_URL = BASE_URL.replace(/^http/, "ws");

export default apiClient;
