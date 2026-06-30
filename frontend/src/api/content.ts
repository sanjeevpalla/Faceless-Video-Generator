import apiClient from "./client";
import { tauriPost } from "./tauriFetch";

export interface StepResponse { text: string; }

export interface GenerateRequest {
  topic: string;
  research?: string;
}

export interface ContentState {
  trends: string;
  research: string;
  script: string;
  scenes: string;
  image_prompts: string;
  thumbnail: string;
  seo: string;
}

export const contentApi = {
  getState: async (pid: string): Promise<ContentState> => {
    const r = await apiClient.get<ContentState>(`/content/${pid}/state`);
    return r.data;
  },

  discoverTrends: (pid: string) =>
    tauriPost<StepResponse>(`/content/${pid}/trends`),

  researchTopic: (pid: string, topic: string) =>
    tauriPost<StepResponse>(`/content/${pid}/research`, { topic }),

  generateScript: (pid: string, research: string) =>
    tauriPost<StepResponse>(`/content/${pid}/script`, { research }),

  generateScenes: (pid: string, script: string) =>
    tauriPost<StepResponse>(`/content/${pid}/scenes`, { script }),

  generateImagePrompts: (pid: string, scenes_json: string) =>
    tauriPost<StepResponse>(`/content/${pid}/image-prompts`, { scenes_json }),

  generateThumbnail: (pid: string, script: string) =>
    tauriPost<StepResponse>(`/content/${pid}/thumbnail`, { script }),

  generateSeo: (pid: string, script: string) =>
    tauriPost<StepResponse>(`/content/${pid}/seo`, { script }),

  runAll: (pid: string, req: GenerateRequest) =>
    tauriPost(`/content/${pid}/generate`, req),
};
