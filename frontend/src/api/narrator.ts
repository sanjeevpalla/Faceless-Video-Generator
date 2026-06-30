import apiClient from "./client";

export interface NarratorClip {
  filename: string;
  size_mb: number;
}

export interface NarratorClipsResponse {
  clips: NarratorClip[];
  count: number;
}

export interface BgClipStatus {
  filename: string;
  processed: boolean;
  nobg_filename: string;
}

export interface BgStatusResponse {
  clips: BgClipStatus[];
  processed: number;
  total: number;
}

export interface BgRemoveResult {
  filename: string;
  output: string | null;
  status: "ok" | "error";
  error?: string;
}

export interface BgRemoveResponse {
  results: BgRemoveResult[];
  processed: number;
  errors: number;
  skipped: number;
  message?: string;
}

export const narratorApi = {
  list: async (projectId: string): Promise<NarratorClipsResponse> => {
    const r = await apiClient.get(`/narrator/project/${projectId}`);
    return r.data;
  },

  upload: async (projectId: string, files: File[]): Promise<{ uploaded: NarratorClip[]; count: number }> => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    const r = await apiClient.post(`/narrator/project/${projectId}/upload`, form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return r.data;
  },

  delete: async (projectId: string, filename: string): Promise<{ deleted: string }> => {
    const r = await apiClient.delete(`/narrator/project/${projectId}/${encodeURIComponent(filename)}`);
    return r.data;
  },

  bgStatus: async (clipsDir?: string, projectId?: string): Promise<BgStatusResponse> => {
    const params: Record<string, string> = {};
    if (clipsDir) params.clips_dir = clipsDir;
    if (projectId) params.project_id = projectId;
    const r = await apiClient.get("/narrator/bg-status", { params });
    return r.data;
  },

  removeBackground: async (clipsDir?: string, projectId?: string): Promise<BgRemoveResponse> => {
    const r = await apiClient.post("/narrator/remove-background", {
      clips_dir: clipsDir || null,
      project_id: projectId || null,
    });
    return r.data;
  },
};
