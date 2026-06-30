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

export const subtitlesApi = {
  getStatus: async (projectId: string): Promise<SubtitleStatus> => {
    const r = await apiClient.get(`/subtitles/project/${projectId}`);
    return r.data;
  },

  getSegments: async (projectId: string): Promise<{ segments: SubtitleSegment[]; segment_count: number }> => {
    const r = await apiClient.get(`/subtitles/project/${projectId}/segments`);
    return r.data;
  },

  getSrtText: async (projectId: string): Promise<string> => {
    const r = await apiClient.get(`/subtitles/project/${projectId}/srt`);
    return r.data;
  },

  getSrtDownloadUrl: (projectId: string): string =>
    `/api/v1/subtitles/project/${projectId}/srt/download`,

  getVttDownloadUrl: (projectId: string): string =>
    `/api/v1/subtitles/project/${projectId}/vtt/download`,

  whisperStatus: async (): Promise<WhisperStatus> => {
    const r = await apiClient.get("/subtitles/whisper/status");
    return r.data;
  },

  deleteOutputs: async (projectId: string): Promise<{ deleted_files: number; message: string }> => {
    const r = await apiClient.delete(`/subtitles/project/${projectId}`);
    return r.data;
  },
};
