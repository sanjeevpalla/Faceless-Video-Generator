import apiClient from "./client";

export interface ServiceResult {
  started?: boolean;
  stopped?: boolean;
  error?: string;
  mode?: string;
  path?: string;
}

export const servicesApi = {
  startComfyUI: async (): Promise<ServiceResult> => {
    const r = await apiClient.post("/services/comfyui/start");
    return r.data;
  },
  stopComfyUI: async (): Promise<ServiceResult> => {
    const r = await apiClient.post("/services/comfyui/stop");
    return r.data;
  },
  startWan2GP: async (): Promise<ServiceResult> => {
    const r = await apiClient.post("/services/wan2gp/start");
    return r.data;
  },
  stopWan2GP: async (): Promise<ServiceResult> => {
    const r = await apiClient.post("/services/wan2gp/stop");
    return r.data;
  },
  clearComfyUIQueue: async (): Promise<{ interrupted: boolean; cleared: boolean }> => {
    const r = await apiClient.post("/services/comfyui/clear-queue");
    return r.data;
  },
};
