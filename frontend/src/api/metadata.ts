import apiClient from "./client";

export interface MetadataStatus {
  seo_available: boolean;
  youtube_metadata_available: boolean;
  description_available: boolean;
  title: string;
  tag_count: number;
  description_length: number;
}

export interface SeoData {
  title: string;
  alternate_titles?: string[];
  description: string;
  tags: string[];
  hashtags?: string[];
  chapters?: Array<{ timestamp: string; title: string }>;
  keywords?: string[];
  search_intent?: string;
  ctr_estimate?: string;
}

export interface YouTubeMetadata {
  title: string;
  description: string;
  tags: string[];
  category_id: string;
  language: string;
  chapters: Array<{ timestamp: string; title: string }>;
  hashtags?: string[];
  privacy_status: string;
  made_for_kids: boolean;
  generated_at: string;
}

export interface MetadataUpdatePayload {
  title?: string;
  description?: string;
  tags?: string[];
  privacy_status?: string;
}

export const metadataApi = {
  getStatus: async (projectId: string): Promise<MetadataStatus> => {
    const r = await apiClient.get(`/metadata/project/${projectId}`);
    return r.data;
  },

  getSeo: async (projectId: string): Promise<SeoData> => {
    const r = await apiClient.get(`/metadata/project/${projectId}/seo`);
    return r.data;
  },

  getYouTube: async (projectId: string): Promise<YouTubeMetadata> => {
    const r = await apiClient.get(`/metadata/project/${projectId}/youtube`);
    return r.data;
  },

  updateYouTube: async (projectId: string, payload: MetadataUpdatePayload): Promise<YouTubeMetadata> => {
    const r = await apiClient.put(`/metadata/project/${projectId}/youtube`, payload);
    return r.data;
  },

  getCopyText: async (projectId: string): Promise<{ text: string; title: string; char_count: number }> => {
    const r = await apiClient.get(`/metadata/project/${projectId}/copy`);
    return r.data;
  },

  generate: async (projectId: string): Promise<{ job_id: string; status: string }> => {
    const r = await apiClient.post(`/metadata/project/${projectId}/generate`);
    return r.data;
  },
};
