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

const langQuery = (language?: string) => (language ? `?language=${encodeURIComponent(language)}` : "");

export const contentApi = {
  getState: async (pid: string, language?: string): Promise<ContentState> => {
    const r = await apiClient.get<ContentState>(`/content/${pid}/state${langQuery(language)}`);
    return r.data;
  },

  discoverTrends: (pid: string, language?: string) =>
    tauriPost<StepResponse>(`/content/${pid}/trends${langQuery(language)}`),

  researchTopic: (pid: string, topic: string, language?: string) =>
    tauriPost<StepResponse>(`/content/${pid}/research${langQuery(language)}`, { topic }),

  generateScript: (pid: string, research: string, language?: string) =>
    tauriPost<StepResponse>(`/content/${pid}/script${langQuery(language)}`, { research }),

  generateScenes: (pid: string, script: string, language?: string) =>
    tauriPost<StepResponse>(`/content/${pid}/scenes${langQuery(language)}`, { script }),

  generateImagePrompts: (pid: string, scenes_json: string, language?: string) =>
    tauriPost<StepResponse>(`/content/${pid}/image-prompts${langQuery(language)}`, { scenes_json }),

  generateThumbnail: (pid: string, script: string, language?: string) =>
    tauriPost<StepResponse>(`/content/${pid}/thumbnail${langQuery(language)}`, { script }),

  generateSeo: (pid: string, script: string, language?: string) =>
    tauriPost<StepResponse>(`/content/${pid}/seo${langQuery(language)}`, { script }),

  runAll: (pid: string, req: GenerateRequest) =>
    tauriPost(`/content/${pid}/generate`, req),
};
