import apiClient from "./client";

export interface PipelineStep {
  name: string;
  label: string;
}

export interface PipelineStepsResponse {
  project_type: string;
  steps: PipelineStep[];
}

export interface PipelineRunResponse {
  job_id: string;
  status: string;
}

export const pipelineApi = {
  getSteps: async (projectType: string): Promise<PipelineStepsResponse> => {
    const r = await apiClient.get(`/pipeline/steps/${projectType}`);
    return r.data;
  },

  run: async (projectId: string, checkComfyui = true): Promise<PipelineRunResponse> => {
    const r = await apiClient.post(`/pipeline/${projectId}/run`, { check_comfyui: checkComfyui });
    return r.data;
  },

  cancel: async (projectId: string): Promise<{ job_id: string; status: string }> => {
    const r = await apiClient.post(`/pipeline/${projectId}/cancel`);
    return r.data;
  },
};
