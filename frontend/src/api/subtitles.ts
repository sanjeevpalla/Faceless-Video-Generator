import apiClient from "./client";

export interface SubtitleSegment {
  id: number;
  start: number;
  end: number;
  text: string;
}

export interface SubtitleStatus {
  status: "ready" | "missing";
  srt_exists: boolean;
  vtt_exists: boolean;
  segment_count: number;
  total_duration: number;
  srt_size: number;
}

export interface WhisperStatus {
  available: boolean;
  configured_model: string;
  device: string;
  available_models: string[];
  version: string | null;
  error?: string;
}

const langQuery = (language?: string) => (language ? `?language=${encodeURIComponent(language)}` : "");

export const subtitlesApi = {
  getStatus: async (projectId: string, language?: string): Promise<SubtitleStatus> => {
    const r = await apiClient.get(`/subtitles/project/${projectId}${langQuery(language)}`);
    return r.data;
  },

  getSegments: async (projectId: string, language?: string): Promise<{ segments: SubtitleSegment[]; segment_count: number }> => {
    const r = await apiClient.get(`/subtitles/project/${projectId}/segments${langQuery(language)}`);
    return r.data;
  },

  getSrtText: async (projectId: string, language?: string): Promise<string> => {
    const r = await apiClient.get(`/subtitles/project/${projectId}/srt${langQuery(language)}`);
    return r.data;
  },

  getSrtDownloadUrl: (projectId: string, language?: string): string =>
    `/api/v1/subtitles/project/${projectId}/srt/download${langQuery(language)}`,

  getVttDownloadUrl: (projectId: string, language?: string): string =>
    `/api/v1/subtitles/project/${projectId}/vtt/download${langQuery(language)}`,

  whisperStatus: async (): Promise<WhisperStatus> => {
    const r = await apiClient.get("/subtitles/whisper/status");
    return r.data;
  },

  deleteOutputs: async (projectId: string, language?: string): Promise<{ deleted_files: number; message: string }> => {
    const r = await apiClient.delete(`/subtitles/project/${projectId}${langQuery(language)}`);
    return r.data;
  },
};
