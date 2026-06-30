import apiClient from "./client";

export interface SceneImageInfo {
  scene_id: number;
  filename: string;
  status: "ready" | "missing" | "generating" | "failed";
  size: number;
  path: string | null;
  prompt: string;
  scene_title: string;
}

export interface ProjectImagesResponse {
  total: number;
  generated: number;
  scenes: SceneImageInfo[];
}

export interface ComfyUIStatus {
  online: boolean;
  url: string;
  gpu_vram_total?: number;
  gpu_vram_free?: number;
}

export const imagesApi = {
  listForProject: async (projectId: string): Promise<ProjectImagesResponse> => {
    const r = await apiClient.get(`/images/project/${projectId}`);
    return r.data;
  },

  getSceneImageUrl: (projectId: string, sceneId: number): string =>
    `/api/v1/images/project/${projectId}/scene/${sceneId}/file`,

  getPrompts: async (projectId: string): Promise<{ prompts: string[]; count: number }> => {
    const r = await apiClient.get(`/images/project/${projectId}/prompts`);
    return r.data;
  },

  regenerateScene: async (
    projectId: string,
    sceneId: number
  ): Promise<{ job_id: string; scene_id: number; status: string }> => {
    const r = await apiClient.post(`/images/project/${projectId}/scene/${sceneId}/regenerate`);
    return r.data;
  },

  comfyuiStatus: async (): Promise<ComfyUIStatus> => {
    const r = await apiClient.get("/images/comfyui/status");
    return r.data;
  },

  replaceSceneImage: async (projectId: string, sceneId: number, file: File): Promise<{ scene_id: number; replaced: boolean; size: number }> => {
    const form = new FormData();
    form.append("file", file);
    const r = await apiClient.put(`/images/project/${projectId}/scene/${sceneId}/replace`, form);
    return r.data;
  },

  deleteOutputs: async (projectId: string): Promise<{ deleted_files: number; message: string }> => {
    const r = await apiClient.delete(`/images/project/${projectId}`);
    return r.data;
  },

  generateWithGemini: async (
    projectId: string
  ): Promise<{ job_id: string; total_scenes: number; status: string; message: string }> => {
    const r = await apiClient.post(`/images/project/${projectId}/generate-gemini`);
    return r.data;
  },
};
