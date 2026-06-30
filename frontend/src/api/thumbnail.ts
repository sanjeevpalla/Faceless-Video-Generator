import apiClient from "./client";

export interface ThumbnailStatus {
  status: "ready" | "missing";
  filename: string | null;
  size: number;
  prompt: string;
}

export const thumbnailApi = {
  getStatus: async (projectId: string): Promise<ThumbnailStatus> => {
    const r = await apiClient.get(`/thumbnail/project/${projectId}`);
    return r.data;
  },

  getThumbnailUrl: (projectId: string): string =>
    `/api/v1/thumbnail/project/${projectId}/file`,

  regenerate: async (projectId: string): Promise<{ job_id: string; status: string }> => {
    const r = await apiClient.post(`/thumbnail/project/${projectId}/regenerate`);
    return r.data;
  },

  deleteOutputs: async (projectId: string): Promise<{ deleted_files: number; message: string }> => {
    const r = await apiClient.delete(`/thumbnail/project/${projectId}`);
    return r.data;
  },
};
