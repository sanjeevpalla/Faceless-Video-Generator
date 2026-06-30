import apiClient from "./client";

export interface SceneClipInfo {
  scene_id: number;
  filename: string;
  status: "ready" | "missing";
  size: number;
  path: string | null;
  image_newer: boolean;
  clip_type: "ltx" | "animated" | null;
}

export interface ProjectClipsResponse {
  total: number;
  animated: number;
  scenes: SceneClipInfo[];
  manifest: Record<string, unknown> | null;
}

export interface Wan2GPStatus {
  online: boolean;
  mode?: "mcp" | "gradio_ui_only" | "offline";
  url: string;
  api_endpoints: string[];
  suggested_api_name: string;
  probe?: string;
  error?: string;
}

export const wan2Api = {
  listForProject: async (projectId: string): Promise<ProjectClipsResponse> => {
    const r = await apiClient.get(`/wan2/project/${projectId}`);
    return r.data;
  },

  getClipUrl: (projectId: string, sceneId: number): string =>
    `/api/v1/wan2/project/${projectId}/scene/${sceneId}/file`,

  animateAll: async (
    projectId: string,
    selectedSceneIds?: number[]
  ): Promise<{ job_id: string; status: string; message: string }> => {
    const body = selectedSceneIds !== undefined ? { selected_scene_ids: selectedSceneIds } : {};
    const r = await apiClient.post(`/wan2/project/${projectId}/generate`, body);
    return r.data;
  },

  animateScene: async (
    projectId: string,
    sceneId: number
  ): Promise<{ job_id: string; scene_id: number; status: string }> => {
    const r = await apiClient.post(`/wan2/project/${projectId}/scene/${sceneId}/animate`);
    return r.data;
  },

  wan2gpStatus: async (): Promise<Wan2GPStatus> => {
    const r = await apiClient.get("/wan2/status");
    return r.data;
  },

  replaceClip: async (projectId: string, sceneId: number, file: File): Promise<{ scene_id: number; replaced: boolean; size: number }> => {
    const form = new FormData();
    form.append("file", file);
    const r = await apiClient.put(`/wan2/project/${projectId}/scene/${sceneId}/replace`, form);
    return r.data;
  },

  deleteOutputs: async (projectId: string): Promise<{ deleted_files: number; message: string }> => {
    const r = await apiClient.delete(`/wan2/project/${projectId}`);
    return r.data;
  },
};
