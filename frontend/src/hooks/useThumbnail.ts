import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { thumbnailApi, ThumbnailStatus } from "../api/thumbnail";

export const THUMBNAIL_KEYS = {
  status: (id: string, language?: string) => ["thumbnail", "status", id, language ?? "primary"] as const,
};

export function useThumbnailStatus(projectId: string | null | undefined, language?: string) {
  return useQuery({
    queryKey: THUMBNAIL_KEYS.status(projectId!, language),
    queryFn: () => thumbnailApi.getStatus(projectId!, language),
    enabled: !!projectId,
    refetchInterval: (query) => {
      const data = query.state.data as ThumbnailStatus | undefined;
      return data?.status === "ready" ? 15_000 : 5000;
    },
    staleTime: 2000,
  });
}

export function useRegenerateThumbnail() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ projectId, language }: { projectId: string; language?: string }) =>
      thumbnailApi.regenerate(projectId, language),
    onSuccess: (_data, variables) => {
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: THUMBNAIL_KEYS.status(variables.projectId, variables.language) });
      }, 5000);
    },
  });
}
