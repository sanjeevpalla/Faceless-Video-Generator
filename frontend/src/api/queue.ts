import apiClient from "./client";

export interface QueueStatus {
  queue_length: number;
  active_count: number;
  pending: number;
  running: number;
  completed: number;
  failed: number;
  cancelled: number;
  total: number;
  is_running: boolean;
}

export interface QueueJobEntry {
  job_id: string;
  project_id: string;
  job_type: string;
  status: string;
  progress: number;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
}

export const queueApi = {
  getStatus: async (): Promise<QueueStatus> => {
    const r = await apiClient.get("/queue/status");
    return r.data;
  },

  listJobs: async (params?: { status?: string; limit?: number }): Promise<{ jobs: QueueJobEntry[]; total: number }> => {
    const r = await apiClient.get("/queue/jobs", { params });
    return r.data;
  },

  cancelJob: async (jobId: string): Promise<{ message: string; job_id: string }> => {
    const r = await apiClient.post(`/queue/jobs/${jobId}/cancel`);
    return r.data;
  },

  pauseQueue: async (jobId?: string): Promise<{ message: string }> => {
    const r = await apiClient.post("/queue/pause", null, { params: jobId ? { job_id: jobId } : {} });
    return r.data;
  },

  resumeQueue: async (jobId?: string): Promise<{ message: string }> => {
    const r = await apiClient.post("/queue/resume", null, { params: jobId ? { job_id: jobId } : {} });
    return r.data;
  },
};
