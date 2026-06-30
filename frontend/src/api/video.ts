import apiClient from "./client";

export interface VideoManifest {
  output_path: string;
  filename: string;
  scene_count: number;
  template: string;
  resolution: string;
  fps: number;
  duration: number;
  size_mb: number;
  has_audio: boolean;
  has_music: boolean;
  has_subtitles: boolean;
}

export interface VideoStatus {
  status: "ready" | "missing";
  filename: string | null;
  size_mb: number;
  path: string | null;
  manifest: VideoManifest | null;
}

export interface RenderAssets {
  images_ready: number;
  narration_ready: boolean;
  music_file: string | null;
  subtitles_ready: boolean;
  estimated_duration: number;
  can_render: boolean;
}

export interface FFmpegStatus {
  ffmpeg_found: boolean;
  ffprobe_found: boolean;
  ffmpeg_path: string | null;
  version: string | null;
  ready: boolean;
}

export interface VideoTemplate {
  id: string;
  label: string;
  transition: string;
  motion: string;
  animations: string[];
  color_grade: string;
  subtitle_style: string;
  music_volume: number;
}

export const videoApi = {
  getStatus: async (projectId: string): Promise<VideoStatus> => {
    const r = await apiClient.get(`/video/project/${projectId}`);
    return r.data;
  },

  getVideoUrl: (projectId: string): string =>
    `/api/v1/video/project/${projectId}/file`,

  getAssets: async (projectId: string): Promise<RenderAssets> => {
    const r = await apiClient.get(`/video/project/${projectId}/assets`);
    return r.data;
  },

  ffmpegStatus: async (): Promise<FFmpegStatus> => {
    const r = await apiClient.get("/video/ffmpeg/status");
    return r.data;
  },

  getTemplates: async (): Promise<{ templates: VideoTemplate[] }> => {
    const r = await apiClient.get("/video/templates");
    return r.data;
  },

  deleteOutputs: async (projectId: string): Promise<{ deleted_files: number; message: string }> => {
    const r = await apiClient.delete(`/video/project/${projectId}`);
    return r.data;
  },
};
