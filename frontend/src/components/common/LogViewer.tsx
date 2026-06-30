import React, { useEffect, useRef, useState, useCallback } from "react";
import {
  Box,
  Typography,
  ToggleButtonGroup,
  ToggleButton,
  IconButton,
  Tooltip,
  Paper,
} from "@mui/material";
import {
  VerticalAlignBottom as ScrollBottomIcon,
  DeleteOutline as ClearIcon,
} from "@mui/icons-material";

export type LogLevel = "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL";

export interface LogEntry {
  id: string;
  level: LogLevel;
  message: string;
  timestamp: string;
  source?: string;
}

const LEVEL_COLORS: Record<LogLevel, string> = {
  DEBUG: "#9090A8",
  INFO: "#E8E8F0",
  WARNING: "#FFB300",
  ERROR: "#FF5252",
  CRITICAL: "#FF1744",
};

const LEVEL_BG: Record<LogLevel, string> = {
  DEBUG: "transparent",
  INFO: "transparent",
  WARNING: "rgba(255,179,0,0.04)",
  ERROR: "rgba(255,82,82,0.06)",
  CRITICAL: "rgba(255,23,68,0.08)",
};

interface LogViewerProps {
  logs: LogEntry[];
  maxHeight?: number | string;
  autoScroll?: boolean;
  onClear?: () => void;
  showFilter?: boolean;
  title?: string;
}

const ALL_LEVELS: LogLevel[] = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"];

export default function LogViewer({
  logs,
  maxHeight = 320,
  autoScroll = true,
  onClear,
  showFilter = true,
  title = "Logs",
}: LogViewerProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [activeFilters, setActiveFilters] = useState<LogLevel[]>(["INFO", "WARNING", "ERROR", "CRITICAL"]);
  const [userScrolled, setUserScrolled] = useState(false);

  const handleScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 30;
    setUserScrolled(!atBottom);
  }, []);

  useEffect(() => {
    if (autoScroll && !userScrolled) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs, autoScroll, userScrolled]);

  const scrollToBottom = () => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    setUserScrolled(false);
  };

  const handleFilterChange = (_: React.MouseEvent, newFilters: LogLevel[]) => {
    if (newFilters.length > 0) setActiveFilters(newFilters);
  };

  const filteredLogs = logs.filter((log) => activeFilters.includes(log.level));

  return (
    <Box>
      {/* Header */}
      <Box
        sx={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          mb: 1,
        }}
      >
        <Typography variant="subtitle2" fontWeight={600}>
          {title}
          <Typography
            component="span"
            variant="caption"
            color="text.secondary"
            sx={{ ml: 1 }}
          >
            ({filteredLogs.length} entries)
          </Typography>
        </Typography>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
          {showFilter && (
            <ToggleButtonGroup
              value={activeFilters}
              onChange={handleFilterChange}
              size="small"
              sx={{
                "& .MuiToggleButton-root": {
                  px: 0.75,
                  py: 0.25,
                  fontSize: "0.6rem",
                  fontWeight: 700,
                  border: "1px solid rgba(255,255,255,0.08)",
                  "&.Mui-selected": {
                    bgcolor: "rgba(108,99,255,0.15)",
                    color: "primary.light",
                  },
                },
              }}
            >
              {ALL_LEVELS.filter((l) => l !== "DEBUG").map((level) => (
                <ToggleButton key={level} value={level} sx={{ color: LEVEL_COLORS[level] }}>
                  {level.slice(0, 4)}
                </ToggleButton>
              ))}
            </ToggleButtonGroup>
          )}
          <Tooltip title="Scroll to bottom">
            <IconButton size="small" onClick={scrollToBottom} sx={{ color: "text.secondary" }}>
              <ScrollBottomIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          {onClear && (
            <Tooltip title="Clear logs">
              <IconButton size="small" onClick={onClear} sx={{ color: "text.secondary" }}>
                <ClearIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
        </Box>
      </Box>

      {/* Log Container */}
      <Paper
        ref={containerRef}
        onScroll={handleScroll}
        sx={{
          bgcolor: "#080810",
          border: "1px solid rgba(255,255,255,0.06)",
          borderRadius: 2,
          maxHeight,
          overflow: "auto",
          fontFamily: '"JetBrains Mono", "Fira Code", "Courier New", monospace',
          fontSize: "0.75rem",
          p: 1,
        }}
      >
        {filteredLogs.length === 0 ? (
          <Typography
            variant="caption"
            color="text.disabled"
            sx={{ display: "block", textAlign: "center", py: 3 }}
          >
            No log entries
          </Typography>
        ) : (
          filteredLogs.map((log) => (
            <Box
              key={log.id}
              sx={{
                display: "flex",
                gap: 1,
                py: 0.3,
                px: 0.5,
                borderRadius: 1,
                bgcolor: LEVEL_BG[log.level],
                "&:hover": { bgcolor: "rgba(255,255,255,0.03)" },
              }}
            >
              <Typography
                component="span"
                sx={{
                  color: "#505068",
                  flexShrink: 0,
                  fontSize: "0.7rem",
                  lineHeight: 1.6,
                  minWidth: 80,
                }}
              >
                {new Date(log.timestamp).toLocaleTimeString()}
              </Typography>
              <Typography
                component="span"
                sx={{
                  color: LEVEL_COLORS[log.level],
                  flexShrink: 0,
                  fontSize: "0.7rem",
                  fontWeight: 700,
                  lineHeight: 1.6,
                  minWidth: 52,
                }}
              >
                [{log.level.slice(0, 4)}]
              </Typography>
              {log.source && (
                <Typography
                  component="span"
                  sx={{
                    color: "#6C63FF",
                    flexShrink: 0,
                    fontSize: "0.7rem",
                    lineHeight: 1.6,
                  }}
                >
                  {log.source}:
                </Typography>
              )}
              <Typography
                component="span"
                sx={{
                  color: LEVEL_COLORS[log.level],
                  fontSize: "0.75rem",
                  lineHeight: 1.6,
                  wordBreak: "break-word",
                }}
              >
                {log.message}
              </Typography>
            </Box>
          ))
        )}
        <div ref={bottomRef} />
      </Paper>
    </Box>
  );
}
