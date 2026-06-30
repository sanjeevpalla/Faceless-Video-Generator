import apiClient from "./client";

export interface ShortClip {
  index: number;
  filename: string;
  title: string;
  start_time: number;
  duration: number;
  size_mb: number;
  status: "ready" | "error";
  error?: string;
}

export interface ShortsStatus {
  state: "idle" | "generating" | "ready" | "error";
  progress: number;
  message: string;
  shorts: ShortClip[];
  count: number;
  resolution: string;
}

export const shortsApi = {
  getStatus: async (projectId: string): Promise<ShortsStatus> => {
    const r = await apiClient.get(`/shorts/project/${projectId}`);
    return r.data;
  },

  generate: async (projectId: string, count = 5): Promise<{ status: string; message: string }> => {
    const r = await apiClient.post(`/shorts/project/${projectId}/generate`, { count });
    return r.data;
  },

  getShortUrl: (projectId: string, filename: string): string =>
    `/api/v1/shorts/project/${projectId}/${encodeURIComponent(filename)}/file`,

  deleteAll: async (projectId: string): Promise<{ deleted: number; message: string }> => {
    const r = await apiClient.delete(`/shorts/project/${projectId}`);
    return r.data;
  },
};
