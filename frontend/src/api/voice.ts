import apiClient from "./client";

export interface SceneAudioInfo {
  scene_id: number;
  filename: string;
  status: "ready" | "missing" | "generating" | "failed";
  size: number;
  duration: number;
  path: string | null;
  narration: string;
  scene_title: string;
}

export interface MergedAudioInfo {
  filename: string;
  size: number;
  duration: number;
}

export interface ProjectVoiceResponse {
  total: number;
  generated: number;
  total_duration: number;
  scenes: SceneAudioInfo[];
  merged: MergedAudioInfo | null;
}

export interface NarrationScene {
  scene_id: number;
  title: string;
  narration: string;
  duration: number;
}

export interface PiperStatus {
  executable: string;
  executable_found: boolean;
  executable_path: string | null;
  model_path: string;
  model_found: boolean;
  version: string | null;
  ready: boolean;
}

export interface AudioPart {
  index: number;
  filename: string;
  original_name: string;
  duration: number;
  size: number;
}

export interface AudioPartsResponse {
  parts: AudioPart[];
  total_duration: number;
}

export const voiceApi = {
  listForProject: async (projectId: string): Promise<ProjectVoiceResponse> => {
    const r = await apiClient.get(`/voice/project/${projectId}`);
    return r.data;
  },

  getNarration: async (projectId: string): Promise<{ scenes: NarrationScene[] }> => {
    const r = await apiClient.get(`/voice/project/${projectId}/narration`);
    return r.data;
  },

  getSceneAudioUrl: (projectId: string, sceneId: number): string =>
    `/api/v1/voice/project/${projectId}/scene/${sceneId}/file`,

  getMergedAudioUrl: (projectId: string): string =>
    `/api/v1/voice/project/${projectId}/merged/file`,

  regenerateScene: async (
    projectId: string,
    sceneId: number
  ): Promise<{ job_id: string; scene_id: number; status: string }> => {
    const r = await apiClient.post(`/voice/project/${projectId}/scene/${sceneId}/regenerate`);
    return r.data;
  },

  piperStatus: async (): Promise<PiperStatus> => {
    const r = await apiClient.get("/voice/piper/status");
    return r.data;
  },

  uploadNarration: async (
    projectId: string,
    file: File
  ): Promise<{ uploaded: boolean; filename: string; duration: number; size: number }> => {
    const form = new FormData();
    form.append("file", file);
    const r = await apiClient.post(`/voice/project/${projectId}/upload`, form);
    return r.data;
  },

  deleteOutputs: async (projectId: string): Promise<{ deleted_files: number; message: string }> => {
    const r = await apiClient.delete(`/voice/project/${projectId}`);
    return r.data;
  },

  // ── Multi-part narration upload ──────────────────────────────────────────
  listParts: async (projectId: string): Promise<AudioPartsResponse> => {
    const r = await apiClient.get(`/voice/project/${projectId}/parts`);
    return r.data;
  },

  uploadPart: async (projectId: string, file: File): Promise<AudioPart> => {
    const form = new FormData();
    form.append("file", file);
    const r = await apiClient.post(`/voice/project/${projectId}/parts`, form);
    return r.data;
  },

  deletePart: async (projectId: string, index: number): Promise<void> => {
    await apiClient.delete(`/voice/project/${projectId}/parts/${index}`);
  },

  reorderParts: async (projectId: string, order: number[]): Promise<AudioPartsResponse> => {
    const r = await apiClient.post(`/voice/project/${projectId}/parts/reorder`, { order });
    return r.data;
  },

  mergeParts: async (projectId: string): Promise<{ merged: boolean; parts: number; duration: number }> => {
    const r = await apiClient.post(`/voice/project/${projectId}/parts/merge`);
    return r.data;
  },

  getPartAudioUrl: (projectId: string, index: number): string =>
    `/api/v1/voice/project/${projectId}/parts/${index}/file`,
};
