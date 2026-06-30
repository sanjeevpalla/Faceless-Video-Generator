import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { voiceApi, ProjectVoiceResponse } from "../api/voice";

export const VOICE_KEYS = {
  project: (id: string) => ["voice", "project", id] as const,
  narration: (id: string) => ["voice", "narration", id] as const,
  piper: () => ["voice", "piper"] as const,
};

export function useProjectVoice(projectId: string | null | undefined) {
  return useQuery({
    queryKey: VOICE_KEYS.project(projectId!),
    queryFn: () => voiceApi.listForProject(projectId!),
    enabled: !!projectId,
    refetchInterval: (query) => {
      const data = query.state.data as ProjectVoiceResponse | undefined;
      if (!data) return 5000;
      return data.generated < data.total ? 3000 : 10000;
    },
    staleTime: 2000,
  });
}

export function useNarration(projectId: string | null | undefined) {
  return useQuery({
    queryKey: VOICE_KEYS.narration(projectId!),
    queryFn: () => voiceApi.getNarration(projectId!),
    enabled: !!projectId,
    staleTime: 30_000,
  });
}

export function usePiperStatus() {
  return useQuery({
    queryKey: VOICE_KEYS.piper(),
    queryFn: voiceApi.piperStatus,
    refetchInterval: 30_000,
    staleTime: 15_000,
    retry: false,
  });
}

export function useRegenerateSceneVoice() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ projectId, sceneId }: { projectId: string; sceneId: number }) =>
      voiceApi.regenerateScene(projectId, sceneId),
    onSuccess: (_data, variables) => {
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: VOICE_KEYS.project(variables.projectId) });
      }, 3000);
    },
  });
}
