import apiClient from "./client";

export interface NewsStory {
  title: string;
  summary: string;
}

export interface AiNewsState {
  script: string;
  scenes: string;
  image_prompts: string;
  thumbnail: string;
  seo: string;
}

export interface SectionContent {
  label: string;
  type: "intro" | "story" | "outro";
  title: string;
  order: number;
  scenes_json: string | null;
  image_prompts: string | null;
  subtitle_srt: string | null;
  image_scene_ids: number[];
  voice_scene_ids: number[];
  has_narration: boolean;
  script_text: string | null;
}

export interface SectionStatus {
  label: string;
  type: "intro" | "story" | "outro" | "agenda";
  story_num: number;
  title: string;
  order: number;
  has_scenes: boolean | null;
  has_image_prompts: boolean | null;
  has_images: boolean | null;
  has_voice: boolean;
  has_subtitles: boolean;
  has_clip: boolean;
  has_short: boolean;
  has_ltx: boolean;
}

export const aiNewsApi = {
  scrape: async (
    projectId: string
  ): Promise<{ stories: NewsStory[]; source: "gemini" | "rss" }> => {
    const response = await apiClient.get(`/ai-news/${projectId}/scrape`);
    return response.data;
  },

  generate: async (
    projectId: string,
    stories: NewsStory[]
  ): Promise<{ status: string; message: string }> => {
    const response = await apiClient.post(`/ai-news/${projectId}/generate`, { stories });
    return response.data;
  },

  getState: async (projectId: string): Promise<AiNewsState> => {
    const response = await apiClient.get(`/ai-news/${projectId}/state`);
    return response.data;
  },

  getSections: async (projectId: string): Promise<SectionStatus[]> => {
    const response = await apiClient.get(`/ai-news/${projectId}/sections`);
    return response.data;
  },

  generateSections: async (
    projectId: string
  ): Promise<{ status: string; message: string }> => {
    const response = await apiClient.post(`/ai-news/${projectId}/sections/generate`);
    return response.data;
  },

  generateSectionImages: async (
    projectId: string,
    label: string
  ): Promise<{ status: string; message: string }> => {
    const response = await apiClient.post(
      `/ai-news/${projectId}/sections/${label}/images`
    );
    return response.data;
  },

  generateSectionVoice: async (
    projectId: string,
    label: string
  ): Promise<{ status: string; message: string }> => {
    const response = await apiClient.post(
      `/ai-news/${projectId}/sections/${label}/voice`
    );
    return response.data;
  },

  generateSectionSubtitles: async (
    projectId: string,
    label: string
  ): Promise<{ status: string; message: string }> => {
    const response = await apiClient.post(
      `/ai-news/${projectId}/sections/${label}/subtitles`
    );
    return response.data;
  },

  generateMissingSectionsSubtitles: async (
    projectId: string
  ): Promise<{ status: string; message: string; labels: string[] }> => {
    const response = await apiClient.post(
      `/ai-news/${projectId}/sections/subtitles/generate-missing`
    );
    return response.data;
  },

  deleteSectionSubtitles: async (
    projectId: string,
    label: string
  ): Promise<{ status: string; deleted_files: number; label: string }> => {
    const response = await apiClient.delete(
      `/ai-news/${projectId}/sections/${label}/subtitles`
    );
    return response.data;
  },

  deleteAllSectionSubtitles: async (
    projectId: string
  ): Promise<{ status: string; deleted_files: number }> => {
    const response = await apiClient.delete(
      `/ai-news/${projectId}/sections/subtitles/all`
    );
    return response.data;
  },

  getClipUrl: (projectId: string, label: string): string =>
    `${apiClient.defaults.baseURL}/ai-news/${projectId}/clips/${label}`,

  generateSectionShort: async (
    projectId: string,
    label: string,
    options?: { narrator_text?: string; logo_path?: string }
  ): Promise<{ status: string; message: string }> => {
    const response = await apiClient.post(
      `/ai-news/${projectId}/sections/${label}/short`,
      options ?? {}
    );
    return response.data;
  },

  getShortUrl: (projectId: string, label: string): string =>
    `${apiClient.defaults.baseURL}/ai-news/${projectId}/shorts/${label}`,

  deleteSectionShort: async (
    projectId: string,
    label: string
  ): Promise<{ status: string; deleted_files: number; label: string }> => {
    const response = await apiClient.delete(
      `/ai-news/${projectId}/sections/${label}/short`
    );
    return response.data;
  },

  deleteAllSectionShorts: async (
    projectId: string
  ): Promise<{ status: string; deleted_files: number }> => {
    const response = await apiClient.delete(
      `/ai-news/${projectId}/sections/shorts/all`
    );
    return response.data;
  },

  regenerateSectionClip: async (
    projectId: string,
    label: string
  ): Promise<{ status: string; message: string }> => {
    const response = await apiClient.post(
      `/ai-news/${projectId}/sections/${label}/clip/regenerate`
    );
    return response.data;
  },

  uploadSectionClip: async (
    projectId: string,
    label: string,
    file: File
  ): Promise<{ status: string; label: string; path: string }> => {
    const form = new FormData();
    form.append("file", file);
    const response = await apiClient.post(
      `/ai-news/${projectId}/sections/${label}/clip/upload`,
      form,
      { headers: { "Content-Type": "multipart/form-data" } }
    );
    return response.data;
  },

  uploadSectionShort: async (
    projectId: string,
    label: string,
    file: File
  ): Promise<{ status: string; label: string; path: string }> => {
    const form = new FormData();
    form.append("file", file);
    const response = await apiClient.post(
      `/ai-news/${projectId}/sections/${label}/short/upload`,
      form,
      { headers: { "Content-Type": "multipart/form-data" } }
    );
    return response.data;
  },

  deleteSectionClip: async (
    projectId: string,
    label: string
  ): Promise<{ status: string; deleted_files: number; label: string }> => {
    const response = await apiClient.delete(
      `/ai-news/${projectId}/sections/${label}/clip`
    );
    return response.data;
  },

  deleteAllSectionClips: async (
    projectId: string
  ): Promise<{ status: string; deleted_files: number }> => {
    const response = await apiClient.delete(
      `/ai-news/${projectId}/sections/clips/all`
    );
    return response.data;
  },

  generateSectionLtx: async (
    projectId: string,
    label: string
  ): Promise<{ status: string; message: string }> => {
    const response = await apiClient.post(
      `/ai-news/${projectId}/sections/${label}/ltx`
    );
    return response.data;
  },

  generateAllSectionsLtx: async (
    projectId: string
  ): Promise<{ status: string; message: string }> => {
    const response = await apiClient.post(
      `/ai-news/${projectId}/sections/ltx/generate-all`
    );
    return response.data;
  },

  deleteSectionLtx: async (
    projectId: string,
    label: string
  ): Promise<{ status: string; deleted_files: number; label: string }> => {
    const response = await apiClient.delete(
      `/ai-news/${projectId}/sections/${label}/ltx`
    );
    return response.data;
  },

  getSectionsContent: async (projectId: string): Promise<SectionContent[]> => {
    const response = await apiClient.get(`/ai-news/${projectId}/sections/content`);
    return response.data;
  },

  getSectionImageUrl: (projectId: string, label: string, sceneId: number): string =>
    `${apiClient.defaults.baseURL}/ai-news/${projectId}/sections/${label}/media/image/${sceneId}`,

  getSectionAudioUrl: (projectId: string, label: string, filename: string): string =>
    `${apiClient.defaults.baseURL}/ai-news/${projectId}/sections/${label}/media/audio/${filename}`,

  deleteSectionImages: async (
    projectId: string,
    label: string
  ): Promise<{ status: string; deleted_files: number; label: string }> => {
    const response = await apiClient.delete(
      `/ai-news/${projectId}/sections/${label}/images`
    );
    return response.data;
  },

  deleteAllSectionImages: async (
    projectId: string
  ): Promise<{ status: string; deleted_files: number }> => {
    const response = await apiClient.delete(
      `/ai-news/${projectId}/sections/images/all`
    );
    return response.data;
  },

  regenerateSectionImage: async (
    projectId: string,
    label: string,
    sceneId: number
  ): Promise<{ status: string; message: string }> => {
    const response = await apiClient.post(
      `/ai-news/${projectId}/sections/${label}/images/${sceneId}/regenerate`
    );
    return response.data;
  },

  generateMissingSectionsVoice: async (
    projectId: string
  ): Promise<{ status: string; message: string; labels: string[] }> => {
    const response = await apiClient.post(
      `/ai-news/${projectId}/sections/voice/generate-missing`
    );
    return response.data;
  },

  deleteSectionVoice: async (
    projectId: string,
    label: string
  ): Promise<{ status: string; deleted_files: number; label: string }> => {
    const response = await apiClient.delete(
      `/ai-news/${projectId}/sections/${label}/voice`
    );
    return response.data;
  },

  deleteAllSectionVoice: async (
    projectId: string
  ): Promise<{ status: string; deleted_files: number }> => {
    const response = await apiClient.delete(
      `/ai-news/${projectId}/sections/voice/all`
    );
    return response.data;
  },

  uploadSectionImage: async (
    projectId: string,
    label: string,
    sceneId: number,
    file: File
  ): Promise<{ status: string; path: string }> => {
    const form = new FormData();
    form.append("file", file);
    const response = await apiClient.post(
      `/ai-news/${projectId}/sections/${label}/images/${sceneId}/upload`,
      form,
      { headers: { "Content-Type": "multipart/form-data" } }
    );
    return response.data;
  },

  getLtxStatus: async (): Promise<{ online: boolean; url: string; model?: string; error?: string }> => {
    const response = await apiClient.get("/ai-news/ltx/status");
    return response.data;
  },
};
