import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { imagesApi, ProjectImagesResponse } from "../api/images";

export const IMAGE_KEYS = {
  project: (id: string) => ["images", "project", id] as const,
  prompts: (id: string) => ["images", "prompts", id] as const,
  comfyui: () => ["images", "comfyui"] as const,
};

export function useProjectImages(projectId: string | null | undefined) {
  return useQuery({
    queryKey: IMAGE_KEYS.project(projectId!),
    queryFn: () => imagesApi.listForProject(projectId!),
    enabled: !!projectId,
    refetchInterval: (query) => {
      // Poll faster while generation is in progress
      const data = query.state.data as ProjectImagesResponse | undefined;
      if (!data) return 5000;
      return data.generated < data.total ? 3000 : 10000;
    },
    staleTime: 2000,
  });
}

export function useImagePrompts(projectId: string | null | undefined) {
  return useQuery({
    queryKey: IMAGE_KEYS.prompts(projectId!),
    queryFn: () => imagesApi.getPrompts(projectId!),
    enabled: !!projectId,
    staleTime: 30_000,
  });
}

export function useComfyUIStatus() {
  return useQuery({
    queryKey: IMAGE_KEYS.comfyui(),
    queryFn: imagesApi.comfyuiStatus,
    refetchInterval: 15_000,
    staleTime: 10_000,
    retry: false,
  });
}

export function useRegenerateScene() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ projectId, sceneId }: { projectId: string; sceneId: number }) =>
      imagesApi.regenerateScene(projectId, sceneId),
    onSuccess: (_data, variables) => {
      // Invalidate the image list so the UI refreshes status
      setTimeout(() => {
        queryClient.invalidateQueries({
          queryKey: IMAGE_KEYS.project(variables.projectId),
        });
      }, 2000);
    },
  });
}
