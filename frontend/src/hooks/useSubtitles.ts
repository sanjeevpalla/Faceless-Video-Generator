import { useQuery, useQueryClient } from "@tanstack/react-query";
import { subtitlesApi, SubtitleStatus } from "../api/subtitles";

export const SUBTITLE_KEYS = {
  status: (id: string) => ["subtitles", "status", id] as const,
  segments: (id: string) => ["subtitles", "segments", id] as const,
  srt: (id: string) => ["subtitles", "srt", id] as const,
  whisper: () => ["subtitles", "whisper"] as const,
};

export function useSubtitleStatus(projectId: string | null | undefined) {
  return useQuery({
    queryKey: SUBTITLE_KEYS.status(projectId!),
    queryFn: () => subtitlesApi.getStatus(projectId!),
    enabled: !!projectId,
    refetchInterval: (query) => {
      const data = query.state.data as SubtitleStatus | undefined;
      return data?.status === "ready" ? 15_000 : 5000;
    },
    staleTime: 2000,
  });
}

export function useSubtitleSegments(projectId: string | null | undefined) {
  return useQuery({
    queryKey: SUBTITLE_KEYS.segments(projectId!),
    queryFn: () => subtitlesApi.getSegments(projectId!),
    enabled: !!projectId,
    staleTime: 10_000,
  });
}

export function useSrtText(projectId: string | null | undefined) {
  return useQuery({
    queryKey: SUBTITLE_KEYS.srt(projectId!),
    queryFn: () => subtitlesApi.getSrtText(projectId!),
    enabled: !!projectId,
    staleTime: 10_000,
  });
}

export function useWhisperStatus() {
  return useQuery({
    queryKey: SUBTITLE_KEYS.whisper(),
    queryFn: subtitlesApi.whisperStatus,
    refetchInterval: 60_000,
    staleTime: 30_000,
    retry: false,
  });
}
