import apiClient from "./client";

export interface Job {
  id: string;
  project_id: string;
  job_type: string;
  status: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  progress: number;
  error_message?: string;
  metadata: Record<string, unknown>;
  priority: number;
  retry_count: number;
  max_retries: number;
}

export const jobsApi = {
  listForProject: async (
    projectId: string,
    params?: { job_type?: string; status?: string }
  ): Promise<Job[]> => {
    const response = await apiClient.get(`/jobs/project/${projectId}`, { params });
    return response.data;
  },

  get: async (jobId: string): Promise<Job> => {
    const response = await apiClient.get(`/jobs/${jobId}`);
    return response.data;
  },

  cancel: async (jobId: string): Promise<{ message: string }> => {
    const response = await apiClient.post(`/jobs/${jobId}/cancel`);
    return response.data;
  },

  retry: async (jobId: string): Promise<Job> => {
    const response = await apiClient.post(`/jobs/${jobId}/retry`);
    return response.data;
  },

  trigger: async (
    projectId: string,
    jobType: "translate" | "image" | "voice" | "subtitle" | "video" | "thumbnail" | "metadata"
  ): Promise<Job> => {
    const response = await apiClient.post(`/jobs/trigger/${projectId}/${jobType}`);
    return response.data;
  },
};
