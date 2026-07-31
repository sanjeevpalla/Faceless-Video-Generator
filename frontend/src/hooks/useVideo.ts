import { useQuery } from "@tanstack/react-query";
import { videoApi, VideoStatus } from "../api/video";

export const VIDEO_KEYS = {
  status: (id: string, language?: string) => ["video", "status", id, language ?? "primary"] as const,
  assets: (id: string, language?: string) => ["video", "assets", id, language ?? "primary"] as const,
  ffmpeg: () => ["video", "ffmpeg"] as const,
  templates: () => ["video", "templates"] as const,
};

export function useVideoStatus(projectId: string | null | undefined, language?: string) {
  return useQuery({
    queryKey: VIDEO_KEYS.status(projectId!, language),
    queryFn: () => videoApi.getStatus(projectId!, language),
    enabled: !!projectId,
    refetchInterval: (query) => {
      const data = query.state.data as VideoStatus | undefined;
      return data?.status === "ready" ? 15_000 : 5000;
    },
    staleTime: 2000,
  });
}

export function useRenderAssets(projectId: string | null | undefined, language?: string) {
  return useQuery({
    queryKey: VIDEO_KEYS.assets(projectId!, language),
    queryFn: () => videoApi.getAssets(projectId!, language),
    enabled: !!projectId,
    staleTime: 10_000,
    refetchInterval: 10_000,
  });
}

export function useFFmpegStatus() {
  return useQuery({
    queryKey: VIDEO_KEYS.ffmpeg(),
    queryFn: videoApi.ffmpegStatus,
    refetchInterval: 60_000,
    staleTime: 30_000,
    retry: false,
  });
}

export function useVideoTemplates() {
  return useQuery({
    queryKey: VIDEO_KEYS.templates(),
    queryFn: videoApi.getTemplates,
    staleTime: Infinity,
  });
}
