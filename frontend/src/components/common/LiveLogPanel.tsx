/**
 * LiveLogPanel — feeds from two sources:
 *   1. Server logs fetched via REST (persisted in DB)
 *   2. WS log_entry events accumulated in window.__wsLogs
 *
 * Merges and deduplicates by id, sorts newest-first, renders with LogViewer.
 */
import React, { useEffect, useState } from "react";
import LogViewer, { LogEntry } from "./LogViewer";
import { useClearLogs } from "../../hooks/useLogs";

interface LiveLogPanelProps {
  projectId: string;
  serverLogs: LogEntry[];
  maxHeight?: number | string;
  title?: string;
}

export default function LiveLogPanel({
  projectId,
  serverLogs,
  maxHeight = 360,
  title = "Live Logs",
}: LiveLogPanelProps) {
  const [wsLogs, setWsLogs] = useState<LogEntry[]>([]);
  const clearLogs = useClearLogs();

  // Poll window.__wsLogs every second (cheap — just a ref copy)
  useEffect(() => {
    const interval = setInterval(() => {
      const raw: LogEntry[] = (window as any).__wsLogs ?? [];
      if (raw.length !== wsLogs.length) {
        setWsLogs([...raw]);
      }
    }, 1000);
    return () => clearInterval(interval);
  }, [wsLogs.length]);

  // Merge WS + server logs; deduplicate by id; sort by timestamp desc
  const merged: LogEntry[] = React.useMemo(() => {
    const map = new Map<string, LogEntry>();
    for (const l of serverLogs) map.set(l.id, l);
    for (const l of wsLogs) map.set(l.id, l);
    return Array.from(map.values()).sort(
      (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
    );
  }, [serverLogs, wsLogs]);

  const handleClear = () => {
    (window as any).__wsLogs = [];
    setWsLogs([]);
    clearLogs.mutate(projectId);
  };

  return (
    <LogViewer
      logs={merged}
      maxHeight={maxHeight}
      title={title}
      onClear={handleClear}
      autoScroll={true}
    />
  );
}
