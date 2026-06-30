import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { queueApi } from "../api/queue";

export const QUEUE_KEYS = {
  status: () => ["queue", "status"] as const,
  jobs: (status?: string) => ["queue", "jobs", status ?? "all"] as const,
};

export function useQueueStatus() {
  return useQuery({
    queryKey: QUEUE_KEYS.status(),
    queryFn: queueApi.getStatus,
    refetchInterval: 3000,
    staleTime: 1000,
  });
}

export function useQueueJobs(status?: string, limit = 50) {
  return useQuery({
    queryKey: QUEUE_KEYS.jobs(status),
    queryFn: () => queueApi.listJobs({ status, limit }),
    refetchInterval: 3000,
    staleTime: 1000,
  });
}

export function useCancelQueueJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => queueApi.cancelJob(jobId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUEUE_KEYS.status() });
      queryClient.invalidateQueries({ queryKey: QUEUE_KEYS.jobs() });
    },
  });
}

export function usePauseQueue() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId?: string) => queueApi.pauseQueue(jobId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: QUEUE_KEYS.status() }),
  });
}

export function useResumeQueue() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId?: string) => queueApi.resumeQueue(jobId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: QUEUE_KEYS.status() }),
  });
}
