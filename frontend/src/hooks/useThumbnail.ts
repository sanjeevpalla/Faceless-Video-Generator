import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { thumbnailApi, ThumbnailStatus } from "../api/thumbnail";

export const THUMBNAIL_KEYS = {
  status: (id: string) => ["thumbnail", "status", id] as const,
};

export function useThumbnailStatus(projectId: string | null | undefined) {
  return useQuery({
    queryKey: THUMBNAIL_KEYS.status(projectId!),
    queryFn: () => thumbnailApi.getStatus(projectId!),
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
    mutationFn: (projectId: string) => thumbnailApi.regenerate(projectId),
    onSuccess: (_data, projectId) => {
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: THUMBNAIL_KEYS.status(projectId) });
      }, 5000);
    },
  });
}
