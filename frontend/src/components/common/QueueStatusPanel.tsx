import React from "react";
import {
  Box,
  Typography,
  Card,
  CardContent,
  Chip,
  LinearProgress,
  IconButton,
  Tooltip,
  List,
  ListItem,
  Divider,
  Button,
} from "@mui/material";
import {
  Cancel as CancelIcon,
  Pause as PauseIcon,
  PlayArrow as ResumeIcon,
  CheckCircle as DoneIcon,
  Error as ErrorIcon,
  HourglassEmpty as PendingIcon,
  Sync as RunningIcon,
} from "@mui/icons-material";
import { useQueueStatus, useQueueJobs, useCancelQueueJob, usePauseQueue, useResumeQueue } from "../../hooks/useQueue";

const STATUS_ICON: Record<string, React.ReactNode> = {
  running: <RunningIcon sx={{ fontSize: 14, color: "warning.main", animation: "spin 1.5s linear infinite", "@keyframes spin": { from: { transform: "rotate(0)" }, to: { transform: "rotate(360deg)" } } }} />,
  pending: <PendingIcon sx={{ fontSize: 14, color: "text.disabled" }} />,
  completed: <DoneIcon sx={{ fontSize: 14, color: "success.main" }} />,
  failed: <ErrorIcon sx={{ fontSize: 14, color: "error.main" }} />,
  cancelled: <CancelIcon sx={{ fontSize: 14, color: "text.disabled" }} />,
};

const STATUS_COLOR: Record<string, string> = {
  running: "warning",
  pending: "default",
  completed: "success",
  failed: "error",
  cancelled: "default",
};

const JOB_TYPE_LABEL: Record<string, string> = {
  image: "Images",
  voice: "Voice",
  subtitle: "Subtitles",
  thumbnail: "Thumbnail",
  video: "Video",
  metadata: "Metadata",
};

interface QueueStatusPanelProps {
  compact?: boolean;
}

export default function QueueStatusPanel({ compact = false }: QueueStatusPanelProps) {
  const { data: status } = useQueueStatus();
  const { data: jobsData } = useQueueJobs(undefined, 20);
  const cancelJob = useCancelQueueJob();
  const pauseQueue = usePauseQueue();
  const resumeQueue = useResumeQueue();

  const jobs = jobsData?.jobs ?? [];
  const activeJobs = jobs.filter((j) => j.status === "running" || j.status === "pending");
  const recentJobs = jobs.slice(0, compact ? 5 : 15);

  const hasPaused = jobs.some((j) => j.status === "paused");
  const hasRunning = (status?.running ?? 0) > 0;

  return (
    <Card>
      <CardContent sx={{ p: compact ? 1.5 : 2 }}>
        {/* Header */}
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1.5 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <Typography variant="subtitle2" fontWeight={700}>
              Job Queue
            </Typography>
            {(status?.running ?? 0) > 0 && (
              <Box
                sx={{
                  width: 7,
                  height: 7,
                  borderRadius: "50%",
                  bgcolor: "warning.main",
                  animation: "pulse 1.5s ease infinite",
                  "@keyframes pulse": { "0%,100%": { opacity: 1 }, "50%": { opacity: 0.3 } },
                }}
              />
            )}
          </Box>
          <Box sx={{ display: "flex", gap: 0.5 }}>
            {hasRunning && (
              <Tooltip title="Pause running jobs">
                <IconButton size="small" onClick={() => pauseQueue.mutate(undefined)} sx={{ color: "text.secondary" }}>
                  <PauseIcon sx={{ fontSize: 16 }} />
                </IconButton>
              </Tooltip>
            )}
            {hasPaused && (
              <Tooltip title="Resume paused jobs">
                <IconButton size="small" onClick={() => resumeQueue.mutate(undefined)} sx={{ color: "text.secondary" }}>
                  <ResumeIcon sx={{ fontSize: 16 }} />
                </IconButton>
              </Tooltip>
            )}
          </Box>
        </Box>

        {/* Stats row */}
        {status && (
          <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap", mb: 1.5 }}>
            {[
              { label: "Running", value: status.running, color: "#FFB300" },
              { label: "Pending", value: status.pending, color: "#9090A8" },
              { label: "Done", value: status.completed, color: "#00E676" },
              { label: "Failed", value: status.failed, color: "#FF5252" },
            ].map((s) => (
              <Box key={s.label} sx={{ textAlign: "center", minWidth: 44 }}>
                <Typography variant="h6" fontWeight={800} color={s.color} sx={{ lineHeight: 1 }}>
                  {s.value}
                </Typography>
                <Typography variant="caption" color="text.disabled" sx={{ fontSize: "0.58rem" }}>
                  {s.label}
                </Typography>
              </Box>
            ))}
          </Box>
        )}

        <Divider sx={{ borderColor: "rgba(255,255,255,0.06)", mb: 1 }} />

        {/* Job list */}
        {recentJobs.length === 0 ? (
          <Typography variant="caption" color="text.disabled" display="block" sx={{ py: 1, textAlign: "center" }}>
            No jobs yet
          </Typography>
        ) : (
          <List dense disablePadding>
            {recentJobs.map((job) => (
              <ListItem
                key={job.job_id}
                disablePadding
                sx={{
                  py: 0.6,
                  px: 0.5,
                  borderRadius: 1,
                  mb: 0.3,
                  bgcolor: job.status === "running" ? "rgba(255,179,0,0.05)" : "transparent",
                }}
              >
                <Box sx={{ display: "flex", alignItems: "center", gap: 1, flex: 1, minWidth: 0 }}>
                  <Box sx={{ flexShrink: 0 }}>{STATUS_ICON[job.status] ?? STATUS_ICON.pending}</Box>

                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
                      <Typography variant="caption" fontWeight={600} noWrap>
                        {JOB_TYPE_LABEL[job.job_type] ?? job.job_type}
                      </Typography>
                      <Chip
                        label={job.status}
                        size="small"
                        color={(STATUS_COLOR[job.status] as any) ?? "default"}
                        sx={{ height: 14, fontSize: "0.55rem" }}
                      />
                    </Box>
                    {job.status === "running" && (
                      <LinearProgress
                        variant="determinate"
                        value={job.progress}
                        sx={{ height: 2, borderRadius: 1, mt: 0.3 }}
                      />
                    )}
                    {job.error && (
                      <Typography variant="caption" color="error.main" noWrap display="block">
                        {job.error.slice(0, 60)}
                      </Typography>
                    )}
                  </Box>

                  {(job.status === "running" || job.status === "pending") && (
                    <Tooltip title="Cancel">
                      <IconButton
                        size="small"
                        onClick={() => cancelJob.mutate(job.job_id)}
                        disabled={cancelJob.isPending}
                        sx={{ color: "text.disabled", flexShrink: 0, p: 0.25 }}
                      >
                        <CancelIcon sx={{ fontSize: 13 }} />
                      </IconButton>
                    </Tooltip>
                  )}
                </Box>
              </ListItem>
            ))}
          </List>
        )}
      </CardContent>
    </Card>
  );
}
