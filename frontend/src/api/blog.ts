import apiClient from "./client";

export type BlogPlatform = "medium" | "linkedin" | "generic";

export interface BlogStatus {
  available: boolean;
  title: string;
  subtitle: string;
  tag_count: number;
  word_count: number;
  generated_at?: string;
  script_available: boolean;
}

export interface BlogContent {
  title: string;
  subtitle: string;
  tags: string[];
  word_count: number;
  generated_at?: string;
  body: string;
}

export interface BlogUpdatePayload {
  title?: string;
  subtitle?: string;
  tags?: string[];
  body?: string;
}

export const blogApi = {
  getStatus: async (projectId: string): Promise<BlogStatus> => {
    const r = await apiClient.get(`/blog/project/${projectId}`);
    return r.data;
  },

  getContent: async (projectId: string): Promise<BlogContent> => {
    const r = await apiClient.get(`/blog/project/${projectId}/content`);
    return r.data;
  },

  updateContent: async (projectId: string, payload: BlogUpdatePayload): Promise<BlogContent> => {
    const r = await apiClient.put(`/blog/project/${projectId}`, payload);
    return r.data;
  },

  getCopyText: async (
    projectId: string,
    platform: BlogPlatform
  ): Promise<{ text: string; platform: string; char_count: number }> => {
    const r = await apiClient.get(`/blog/project/${projectId}/copy`, { params: { platform } });
    return r.data;
  },

  generate: async (projectId: string): Promise<{ status: string; message: string }> => {
    const r = await apiClient.post(`/blog/project/${projectId}/generate`);
    return r.data;
  },
};
