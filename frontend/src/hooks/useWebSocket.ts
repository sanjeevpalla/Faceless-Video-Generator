import { useEffect, useRef, useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { WS_BASE_URL } from "../api/client";
import { useAppStore } from "../store/appStore";
import { useProjectStore } from "../store/projectStore";
import { IMAGE_KEYS } from "./useImages";
import { VOICE_KEYS } from "./useVoice";
import { SUBTITLE_KEYS } from "./useSubtitles";
import { VIDEO_KEYS } from "./useVideo";
import { QUEUE_KEYS } from "./useQueue";
import { LOG_KEYS } from "./useLogs";
import { WAN2_KEYS } from "./useWan2";

type MessageHandler = (event: string, data: Record<string, unknown>) => void;

interface UseWebSocketOptions {
  projectId?: string;
  onMessage?: MessageHandler;
  autoReconnect?: boolean;
  reconnectDelay?: number;
  maxReconnects?: number;
}

interface WebSocketState {
  isConnected: boolean;
  reconnectCount: number;
  lastError: string | null;
}

export function useWebSocket({
  projectId,
  onMessage,
  autoReconnect = true,
  reconnectDelay = 3000,
  maxReconnects = 20,
}: UseWebSocketOptions = {}) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectCountRef = useRef(0);
  const mountedRef = useRef(true);
  const queryClient = useQueryClient();

  const [state, setState] = useState<WebSocketState>({
    isConnected: false,
    reconnectCount: 0,
    lastError: null,
  });

  const setWsConnected = useAppStore((s) => s.setWsConnected);
  const updateProgress = useProjectStore((s) => s.updateProgress);
  const setActiveJob = useAppStore((s) => s.setActiveJob);
  const removeActiveJob = useAppStore((s) => s.removeActiveJob);
  const addNotification = useAppStore((s) => s.addNotification);

  // Local log accumulator for live log panel (keyed by projectId)
  const logAccumRef = useRef<Array<{ id: string; level: string; message: string; timestamp: string; source?: string }>>([]);
  let logCounter = 0;

  const invalidateImages = useCallback(() => {
    if (projectId) {
      queryClient.invalidateQueries({ queryKey: IMAGE_KEYS.project(projectId) });
    }
  }, [projectId, queryClient]);

  const invalidateVoice = useCallback(() => {
    if (projectId) {
      queryClient.invalidateQueries({ queryKey: VOICE_KEYS.project(projectId) });
    }
  }, [projectId, queryClient]);

  const invalidateSubtitles = useCallback(() => {
    if (projectId) {
      queryClient.invalidateQueries({ queryKey: SUBTITLE_KEYS.status(projectId) });
      queryClient.invalidateQueries({ queryKey: SUBTITLE_KEYS.segments(projectId) });
      queryClient.invalidateQueries({ queryKey: SUBTITLE_KEYS.srt(projectId) });
    }
  }, [projectId, queryClient]);

  const invalidateVideo = useCallback(() => {
    if (projectId) {
      queryClient.invalidateQueries({ queryKey: VIDEO_KEYS.status(projectId) });
      queryClient.invalidateQueries({ queryKey: VIDEO_KEYS.assets(projectId) });
    }
  }, [projectId, queryClient]);

  const invalidateLogs = useCallback(() => {
    if (projectId) {
      queryClient.invalidateQueries({ queryKey: LOG_KEYS.byProject(projectId) });
    }
  }, [projectId, queryClient]);

  const invalidateClips = useCallback(() => {
    if (projectId) {
      queryClient.invalidateQueries({ queryKey: WAN2_KEYS.project(projectId) });
    }
  }, [projectId, queryClient]);

  const invalidateAiNewsSections = useCallback(() => {
    if (projectId) {
      queryClient.invalidateQueries({ queryKey: ["ai-news-sections", projectId] });
      queryClient.invalidateQueries({ queryKey: ["ai-news-sections-content", projectId] });
    }
  }, [projectId, queryClient]);

  const handleMessage = useCallback(
    (raw: string) => {
      let parsed: Record<string, unknown>;
      try {
        parsed = JSON.parse(raw);
      } catch {
        return;
      }

      const { event, data = {}, job_id } = parsed as {
        event: string;
        data: Record<string, unknown>;
        job_id?: string;
      };

      // Map backend job_type values to ProgressState store keys
      const toStoreKey = (jt: string) =>
        jt === "image" ? "images" : jt === "subtitle" ? "subtitles" : jt;

      switch (event) {
        // ── Job lifecycle ─────────────────────────────────────────────
        case "job_started": {
          const jobType = String(data.job_type ?? "");
          if (jobType && job_id) {
            setActiveJob({
              jobId: String(job_id),
              projectId: projectId ?? String(data.project_id ?? ""),
              jobType,
              progress: 0,
              status: "running",
              message: "Starting…",
            });
            updateProgress(toStoreKey(jobType) as any, { status: "running", progress: 0 });
          }
          break;
        }

        case "job_progress": {
          const jobType = String(data.job_type ?? "");
          const progress = Number(data.progress ?? 0);
          const message = String(data.message ?? "");
          if (jobType) {
            updateProgress(toStoreKey(jobType) as any, {
              progress,
              status: "running",
              completed: Number(data.completed ?? 0),
              total: Number(data.total ?? 0),
            });
          }
          if (job_id) {
            setActiveJob({
              jobId: String(job_id),
              projectId: projectId ?? "",
              jobType,
              progress,
              status: "running",
              message,
            });
          }
          // Refresh sections list after each per-section completion event
          if (jobType === "ai_news_sections" && data.section_done) {
            invalidateAiNewsSections();
          }
          break;
        }

        case "job_completed": {
          const jobType = String(data.job_type ?? "");
          if (jobType) {
            updateProgress(toStoreKey(jobType) as any, { progress: 100, status: "completed" });
          }
          if (job_id) removeActiveJob(String(job_id));

          // Invalidate relevant query caches
          if (jobType === "image") invalidateImages();
          else if (jobType === "voice") invalidateVoice();
          else if (jobType === "subtitle") invalidateSubtitles();
          else if (jobType === "video") invalidateVideo();
          else if (jobType === "thumbnail") invalidateImages();
          else if (jobType === "wan2") invalidateClips();
          else if (jobType === "ai_news_sections") invalidateAiNewsSections();
          else if (jobType === "section_images") invalidateAiNewsSections();
          else if (jobType === "section_voice" || jobType === "all_sections_voice") invalidateAiNewsSections();
          else if (jobType === "section_subtitles" || jobType === "all_sections_subtitles") invalidateAiNewsSections();
          else if (jobType === "section_short") invalidateAiNewsSections();
          else if (jobType === "section_clip") invalidateAiNewsSections();

          addNotification({
            type: "success",
            title: `${jobType || "Job"} completed`,
            message: `${jobType.charAt(0).toUpperCase() + jobType.slice(1)} generation finished successfully`,
          });
          queryClient.invalidateQueries({ queryKey: QUEUE_KEYS.status() });
          break;
        }

        case "job_failed": {
          const jobType = String(data.job_type ?? "");
          const error = String(data.error ?? "Unknown error");
          if (jobType) {
            updateProgress(toStoreKey(jobType) as any, { status: "failed", error });
          }
          if (job_id) removeActiveJob(String(job_id));
          if (jobType === "section_images") invalidateAiNewsSections();
          addNotification({
            type: "error",
            title: `${jobType || "Job"} failed`,
            message: error.slice(0, 120),
          });
          queryClient.invalidateQueries({ queryKey: QUEUE_KEYS.status() });
          break;
        }

        case "job_cancelled": {
          const jobType = String(data.job_type ?? "");
          if (jobType) updateProgress(toStoreKey(jobType) as any, { status: "pending", progress: 0 });
          if (job_id) removeActiveJob(String(job_id));
          queryClient.invalidateQueries({ queryKey: QUEUE_KEYS.status() });
          break;
        }

        // ── Scene-level events ────────────────────────────────────────
        case "scene_image_ready": {
          // Invalidate image gallery after a short debounce
          setTimeout(invalidateImages, 500);
          break;
        }

        case "scene_audio_ready": {
          setTimeout(invalidateVoice, 500);
          break;
        }

        case "wan2_clip_ready": {
          setTimeout(invalidateClips, 500);
          break;
        }

        case "wan2_complete": {
          updateProgress("wan2" as any, { progress: 100, status: "completed" });
          if (job_id) removeActiveJob(String(job_id));
          addNotification({
            type: "success",
            title: "Animation complete",
            message: `${String(data.animated ?? 0)}/${String(data.total ?? 0)} clips generated`,
          });
          queryClient.invalidateQueries({ queryKey: QUEUE_KEYS.status() });
          setTimeout(invalidateClips, 500);
          break;
        }

        // ── Log streaming ─────────────────────────────────────────────
        case "log_entry": {
          // Persist to local log accumulator for LiveLogPanel
          const entry = {
            id: `ws_log_${++logCounter}_${Date.now()}`,
            level: String(data.level ?? "INFO"),
            message: String(data.message ?? ""),
            timestamp: String(data.timestamp ?? new Date().toISOString()),
            source: data.source ? String(data.source) : undefined,
          };
          // Store on window so LiveLogPanel can consume without re-renders
          (window as any).__wsLogs = [(entry), ...((window as any).__wsLogs ?? [])].slice(0, 500);
          // Debounce invalidating the server logs query
          setTimeout(invalidateLogs, 2000);
          break;
        }

        // ── Queue / system ────────────────────────────────────────────
        case "queue_updated": {
          queryClient.invalidateQueries({ queryKey: QUEUE_KEYS.status() });
          queryClient.invalidateQueries({ queryKey: QUEUE_KEYS.jobs() });
          break;
        }

        case "connected": {
          // Restore active jobs from snapshot
          const activeJobs = (data.active_jobs ?? []) as Array<Record<string, unknown>>;
          for (const j of activeJobs) {
            const jid = String(j.job_id ?? "");
            const jtype = String(j.job_type ?? "");
            if (jid && jtype) {
              setActiveJob({
                jobId: jid,
                projectId: String(j.project_id ?? projectId ?? ""),
                jobType: jtype,
                progress: Number(j.progress ?? 0),
                status: String(j.status ?? "running"),
              });
            }
          }
          break;
        }
      }

      if (onMessage) {
        onMessage(event, data);
      }
    },
    [
      projectId,
      updateProgress,
      setActiveJob,
      removeActiveJob,
      addNotification,
      invalidateImages,
      invalidateVoice,
      invalidateSubtitles,
      invalidateVideo,
      invalidateLogs,
      invalidateClips,
      invalidateAiNewsSections,
      queryClient,
      onMessage,
    ]
  );

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const url = projectId ? `${WS_BASE_URL}/ws/${projectId}` : `${WS_BASE_URL}/ws`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) return;
      reconnectCountRef.current = 0;
      setState({ isConnected: true, reconnectCount: 0, lastError: null });
      setWsConnected(true);
    };

    ws.onmessage = (e) => {
      if (mountedRef.current) handleMessage(e.data);
    };

    ws.onerror = () => {
      if (mountedRef.current) setState((prev) => ({ ...prev, lastError: "Connection error" }));
    };

    ws.onclose = () => {
      if (!mountedRef.current) return;
      setState((prev) => ({ ...prev, isConnected: false }));
      setWsConnected(false);

      if (autoReconnect && reconnectCountRef.current < maxReconnects) {
        const delay = Math.min(reconnectDelay * (reconnectCountRef.current + 1), 30000);
        reconnectTimerRef.current = setTimeout(() => {
          if (mountedRef.current) {
            reconnectCountRef.current += 1;
            setState((prev) => ({ ...prev, reconnectCount: reconnectCountRef.current }));
            connect();
          }
        }, delay);
      }
    };
  }, [projectId, autoReconnect, reconnectDelay, maxReconnects, handleMessage, setWsConnected]);

  const disconnect = useCallback(() => {
    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
    wsRef.current?.close();
    wsRef.current = null;
  }, []);

  const sendMessage = useCallback((data: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  const ping = useCallback(() => sendMessage({ type: "ping" }), [sendMessage]);

  const requestStatus = useCallback(
    () => sendMessage({ type: "get_status" }),
    [sendMessage]
  );

  useEffect(() => {
    mountedRef.current = true;
    connect();
    const pingInterval = setInterval(ping, 25000);
    return () => {
      mountedRef.current = false;
      clearInterval(pingInterval);
      disconnect();
    };
  }, [connect, disconnect, ping]);

  return {
    isConnected: state.isConnected,
    reconnectCount: state.reconnectCount,
    lastError: state.lastError,
    disconnect,
    sendMessage,
    requestStatus,
  };
}
