import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { metadataApi, MetadataUpdatePayload } from "../api/metadata";

export const METADATA_KEYS = {
  status: (id: string) => ["metadata", "status", id] as const,
  seo: (id: string) => ["metadata", "seo", id] as const,
  youtube: (id: string) => ["metadata", "youtube", id] as const,
};

export function useMetadataStatus(projectId: string | null | undefined) {
  return useQuery({
    queryKey: METADATA_KEYS.status(projectId!),
    queryFn: () => metadataApi.getStatus(projectId!),
    enabled: !!projectId,
    staleTime: 5000,
    refetchInterval: 10_000,
  });
}

export function useSeoData(projectId: string | null | undefined) {
  return useQuery({
    queryKey: METADATA_KEYS.seo(projectId!),
    queryFn: () => metadataApi.getSeo(projectId!),
    enabled: !!projectId,
    staleTime: 30_000,
    retry: false,
  });
}

export function useYouTubeMetadata(projectId: string | null | undefined) {
  return useQuery({
    queryKey: METADATA_KEYS.youtube(projectId!),
    queryFn: () => metadataApi.getYouTube(projectId!),
    enabled: !!projectId,
    staleTime: 5000,
    retry: false,
  });
}

export function useUpdateYouTubeMetadata() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ projectId, payload }: { projectId: string; payload: MetadataUpdatePayload }) =>
      metadataApi.updateYouTube(projectId, payload),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: METADATA_KEYS.youtube(variables.projectId) });
      queryClient.invalidateQueries({ queryKey: METADATA_KEYS.status(variables.projectId) });
    },
  });
}

export function useGenerateMetadata() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (projectId: string) => metadataApi.generate(projectId),
    onSuccess: (_data, projectId) => {
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: METADATA_KEYS.status(projectId) });
        queryClient.invalidateQueries({ queryKey: METADATA_KEYS.youtube(projectId) });
      }, 3000);
    },
  });
}
