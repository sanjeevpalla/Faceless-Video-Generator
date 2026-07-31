import apiClient from "./client";

export interface ThumbnailStatus {
  status: "ready" | "missing";
  filename: string | null;
  size: number;
  prompt: string;
}

const langQuery = (language?: string) => (language ? `?language=${encodeURIComponent(language)}` : "");

export const thumbnailApi = {
  getStatus: async (projectId: string, language?: string): Promise<ThumbnailStatus> => {
    const r = await apiClient.get(`/thumbnail/project/${projectId}${langQuery(language)}`);
    return r.data;
  },

  getThumbnailUrl: (projectId: string, language?: string): string =>
    `/api/v1/thumbnail/project/${projectId}/file${langQuery(language)}`,

  regenerate: async (projectId: string, language?: string): Promise<{ job_id: string; status: string }> => {
    const r = await apiClient.post(`/thumbnail/project/${projectId}/regenerate${langQuery(language)}`);
    return r.data;
  },

  deleteOutputs: async (projectId: string, language?: string): Promise<{ deleted_files: number; message: string }> => {
    const r = await apiClient.delete(`/thumbnail/project/${projectId}${langQuery(language)}`);
    return r.data;
  },
};
