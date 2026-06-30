import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { jobsApi, Job } from "../api/jobs";

export const JOB_KEYS = {
  all: ["jobs"] as const,
  byProject: (projectId: string) => [...JOB_KEYS.all, "project", projectId] as const,
  detail: (jobId: string) => [...JOB_KEYS.all, "detail", jobId] as const,
};

export function useJobs(
  projectId: string | null | undefined,
  params?: { job_type?: string; status?: string }
) {
  return useQuery({
    queryKey: JOB_KEYS.byProject(projectId!),
    queryFn: () => jobsApi.listForProject(projectId!, params),
    enabled: !!projectId,
    refetchInterval: 5000, // Poll every 5s for active jobs
    staleTime: 2000,
  });
}

export function useJob(jobId: string | null | undefined) {
  return useQuery({
    queryKey: JOB_KEYS.detail(jobId!),
    queryFn: () => jobsApi.get(jobId!),
    enabled: !!jobId,
    staleTime: 2000,
  });
}

export function useTriggerJob() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      projectId,
      jobType,
    }: {
      projectId: string;
      jobType: "image" | "voice" | "subtitle" | "video" | "thumbnail" | "metadata";
    }) => jobsApi.trigger(projectId, jobType),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: JOB_KEYS.byProject(variables.projectId),
      });
    },
  });
}

export function useCancelJob() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (jobId: string) => jobsApi.cancel(jobId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: JOB_KEYS.all });
    },
  });
}

export function useRetryJob() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (jobId: string) => jobsApi.retry(jobId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: JOB_KEYS.all });
    },
  });
}

// Helper: get the latest job for a project by type
export function useLatestJobByType(
  projectId: string | null | undefined,
  jobType: string
): Job | null {
  const { data: jobs } = useJobs(projectId);
  if (!jobs) return null;
  const filtered = jobs
    .filter((j) => j.job_type === jobType)
    .sort(
      (a, b) =>
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    );
  return filtered[0] || null;
}
