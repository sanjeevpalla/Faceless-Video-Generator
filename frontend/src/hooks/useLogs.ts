import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { logsApi, LogEntry } from "../api/logs";
import { useState, useEffect, useRef } from "react";

export const LOG_KEYS = {
  byProject: (projectId: string) => ["logs", "project", projectId] as const,
};

export function useProjectLogs(
  projectId: string | null | undefined,
  params?: { level?: string; limit?: number }
) {
  return useQuery({
    queryKey: LOG_KEYS.byProject(projectId!),
    queryFn: () => logsApi.getForProject(projectId!, params),
    enabled: !!projectId,
    refetchInterval: 5000,
    staleTime: 2000,
  });
}

export function useClearLogs() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (projectId: string) => logsApi.clearForProject(projectId),
    onSuccess: (_data, projectId) => {
      queryClient.setQueryData(LOG_KEYS.byProject(projectId), []);
    },
  });
}

// Local log accumulator fed from WebSocket messages
export function useLocalLogs(maxEntries = 500) {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const counterRef = useRef(0);

  const appendLog = (entry: Omit<LogEntry, "id">) => {
    setLogs((prev) => {
      const next = [
        { ...entry, id: `local_${++counterRef.current}` },
        ...prev,
      ].slice(0, maxEntries);
      return next;
    });
  };

  const clearLogs = () => setLogs([]);

  return { logs, appendLog, clearLogs };
}
