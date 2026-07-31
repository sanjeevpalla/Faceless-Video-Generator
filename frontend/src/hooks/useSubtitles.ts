import { useQuery, useQueryClient } from "@tanstack/react-query";
import { subtitlesApi, SubtitleStatus } from "../api/subtitles";

export const SUBTITLE_KEYS = {
  status: (id: string, language?: string) => ["subtitles", "status", id, language ?? "primary"] as const,
  segments: (id: string, language?: string) => ["subtitles", "segments", id, language ?? "primary"] as const,
  srt: (id: string, language?: string) => ["subtitles", "srt", id, language ?? "primary"] as const,
  whisper: () => ["subtitles", "whisper"] as const,
};

export function useSubtitleStatus(projectId: string | null | undefined, language?: string) {
  return useQuery({
    queryKey: SUBTITLE_KEYS.status(projectId!, language),
    queryFn: () => subtitlesApi.getStatus(projectId!, language),
    enabled: !!projectId,
    refetchInterval: (query) => {
      const data = query.state.data as SubtitleStatus | undefined;
      return data?.status === "ready" ? 15_000 : 5000;
    },
    staleTime: 2000,
  });
}

export function useSubtitleSegments(projectId: string | null | undefined, language?: string) {
  return useQuery({
    queryKey: SUBTITLE_KEYS.segments(projectId!, language),
    queryFn: () => subtitlesApi.getSegments(projectId!, language),
    enabled: !!projectId,
    staleTime: 10_000,
  });
}

export function useSrtText(projectId: string | null | undefined, language?: string) {
  return useQuery({
    queryKey: SUBTITLE_KEYS.srt(projectId!, language),
    queryFn: () => subtitlesApi.getSrtText(projectId!, language),
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
