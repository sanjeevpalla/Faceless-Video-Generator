import React from "react";
import {
  Box,
  Typography,
  LinearProgress,
  Chip,
  IconButton,
  Tooltip,
  Collapse,
} from "@mui/material";
import {
  Cancel as CancelIcon,
  ExpandLess as CollapseIcon,
  ExpandMore as ExpandIcon,
} from "@mui/icons-material";
import { useState } from "react";
import { useAppStore, ActiveJob } from "../../store/appStore";
import { useCancelJob } from "../../hooks/useJobs";

const JOB_TYPE_LABELS: Record<string, string> = {
  image: "Image Generation",
  voice: "Voice Generation",
  subtitle: "Subtitle Generation",
  thumbnail: "Thumbnail Generation",
  video: "Video Render",
  metadata: "Metadata",
};

function JobRow({ job }: { job: ActiveJob }) {
  const cancelJob = useCancelJob();

  return (
    <Box
      sx={{
        display: "flex",
        alignItems: "center",
        gap: 1.5,
        py: 1,
        px: 1.5,
        borderRadius: 1.5,
        bgcolor: "rgba(108,99,255,0.06)",
        border: "1px solid rgba(108,99,255,0.15)",
        mb: 0.75,
      }}
    >
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Box sx={{ display: "flex", justifyContent: "space-between", mb: 0.5 }}>
          <Typography variant="caption" fontWeight={600} noWrap>
            {JOB_TYPE_LABELS[job.jobType] || job.jobType}
          </Typography>
          <Typography variant="caption" color="primary.light" fontWeight={700}>
            {job.progress.toFixed(0)}%
          </Typography>
        </Box>
        <LinearProgress
          variant="determinate"
          value={job.progress}
          sx={{ height: 4, borderRadius: 2 }}
        />
        {job.message && (
          <Typography variant="caption" color="text.secondary" noWrap display="block" sx={{ mt: 0.25 }}>
            {job.message}
          </Typography>
        )}
      </Box>

      <Chip
        label={job.status}
        size="small"
        sx={{
          height: 18,
          fontSize: "0.6rem",
          bgcolor: "rgba(255,179,0,0.12)",
          color: "warning.main",
          flexShrink: 0,
        }}
      />

      <Tooltip title="Cancel job">
        <IconButton
          size="small"
          onClick={() => cancelJob.mutate(job.jobId)}
          sx={{ color: "text.secondary", flexShrink: 0 }}
          disabled={cancelJob.isPending}
        >
          <CancelIcon sx={{ fontSize: 16 }} />
        </IconButton>
      </Tooltip>
    </Box>
  );
}

export default function ActiveJobsBar() {
  const activeJobs = useAppStore((s) => s.activeJobs);
  const [expanded, setExpanded] = useState(true);

  const jobs = Object.values(activeJobs);
  if (jobs.length === 0) return null;

  return (
    <Box
      sx={{
        position: "fixed",
        bottom: 16,
        right: 16,
        width: 320,
        zIndex: 1200,
        bgcolor: "#12121A",
        border: "1px solid rgba(108,99,255,0.3)",
        borderRadius: 2,
        boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
        overflow: "hidden",
      }}
    >
      {/* Header */}
      <Box
        sx={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          px: 1.5,
          py: 1,
          bgcolor: "rgba(108,99,255,0.1)",
          borderBottom: "1px solid rgba(108,99,255,0.15)",
          cursor: "pointer",
        }}
        onClick={() => setExpanded(!expanded)}
      >
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          <Box
            sx={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              bgcolor: "warning.main",
              animation: "pulse 1.5s ease-in-out infinite",
              "@keyframes pulse": {
                "0%, 100%": { opacity: 1 },
                "50%": { opacity: 0.4 },
              },
            }}
          />
          <Typography variant="caption" fontWeight={700} color="primary.light">
            {jobs.length} Active Job{jobs.length !== 1 ? "s" : ""}
          </Typography>
        </Box>
        <IconButton size="small" sx={{ color: "text.secondary", p: 0.25 }}>
          {expanded ? <CollapseIcon fontSize="small" /> : <ExpandIcon fontSize="small" />}
        </IconButton>
      </Box>

      <Collapse in={expanded}>
        <Box sx={{ p: 1.25 }}>
          {jobs.map((job) => (
            <JobRow key={job.jobId} job={job} />
          ))}
        </Box>
      </Collapse>
    </Box>
  );
}
