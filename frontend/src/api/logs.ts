import apiClient from "./client";

export interface LogEntry {
  id: string;
  level: "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL";
  message: string;
  timestamp: string;
  source: string | null;
  job_id: string | null;
  context: Record<string, unknown>;
}

export const logsApi = {
  getForProject: async (
    projectId: string,
    params?: { level?: string; limit?: number; offset?: number }
  ): Promise<LogEntry[]> => {
    const response = await apiClient.get(`/logs/project/${projectId}`, { params });
    return response.data;
  },

  clearForProject: async (projectId: string): Promise<{ message: string; count: number }> => {
    const response = await apiClient.delete(`/logs/project/${projectId}`);
    return response.data;
  },
};
