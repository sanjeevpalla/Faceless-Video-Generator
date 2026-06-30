import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { wan2Api, ProjectClipsResponse } from "../api/wan2";

export const WAN2_KEYS = {
  project: (id: string) => ["wan2", "project", id] as const,
  status: () => ["wan2", "status"] as const,
};

export function useProjectClips(projectId: string | null | undefined) {
  return useQuery({
    queryKey: WAN2_KEYS.project(projectId!),
    queryFn: () => wan2Api.listForProject(projectId!),
    enabled: !!projectId,
    refetchInterval: (query) => {
      const data = query.state.data as ProjectClipsResponse | undefined;
      if (!data) return 5000;
      return data.animated < data.total ? 4000 : 15000;
    },
    staleTime: 2000,
  });
}

export function useWan2GPStatus() {
  return useQuery({
    queryKey: WAN2_KEYS.status(),
    queryFn: wan2Api.wan2gpStatus,
    refetchInterval: 15_000,
    staleTime: 10_000,
    retry: false,
  });
}

export function useAnimateScene() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ projectId, sceneId }: { projectId: string; sceneId: number }) =>
      wan2Api.animateScene(projectId, sceneId),
    onSuccess: (_data, variables) => {
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: WAN2_KEYS.project(variables.projectId) });
      }, 3000);
    },
  });
}
