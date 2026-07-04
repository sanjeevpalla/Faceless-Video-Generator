import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { blogApi, BlogPlatform, BlogUpdatePayload } from "../api/blog";

export const BLOG_KEYS = {
  status: (id: string) => ["blog", "status", id] as const,
  content: (id: string) => ["blog", "content", id] as const,
  copy: (id: string, platform: BlogPlatform) => ["blog", "copy", id, platform] as const,
};

export function useBlogStatus(projectId: string | null | undefined) {
  return useQuery({
    queryKey: BLOG_KEYS.status(projectId!),
    queryFn: () => blogApi.getStatus(projectId!),
    enabled: !!projectId,
    staleTime: 5000,
  });
}

export function useBlogContent(projectId: string | null | undefined) {
  return useQuery({
    queryKey: BLOG_KEYS.content(projectId!),
    queryFn: () => blogApi.getContent(projectId!),
    enabled: !!projectId,
    staleTime: 5000,
    retry: false,
  });
}

export function useBlogCopyText(projectId: string | null | undefined, platform: BlogPlatform, enabled: boolean) {
  return useQuery({
    queryKey: BLOG_KEYS.copy(projectId!, platform),
    queryFn: () => blogApi.getCopyText(projectId!, platform),
    enabled: !!projectId && enabled,
    staleTime: 5000,
    retry: false,
  });
}

export function useUpdateBlog() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ projectId, payload }: { projectId: string; payload: BlogUpdatePayload }) =>
      blogApi.updateContent(projectId, payload),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: BLOG_KEYS.content(variables.projectId) });
      queryClient.invalidateQueries({ queryKey: BLOG_KEYS.status(variables.projectId) });
      queryClient.invalidateQueries({ queryKey: ["blog", "copy", variables.projectId] });
    },
  });
}

export function useGenerateBlog() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (projectId: string) => blogApi.generate(projectId),
    onSuccess: (_data, projectId) => {
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: BLOG_KEYS.status(projectId) });
        queryClient.invalidateQueries({ queryKey: BLOG_KEYS.content(projectId) });
        queryClient.invalidateQueries({ queryKey: ["blog", "copy", projectId] });
      }, 3000);
    },
  });
}
