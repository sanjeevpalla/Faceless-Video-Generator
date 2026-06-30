import React from "react";
import {
  Card,
  CardContent,
  Box,
  Typography,
  LinearProgress,
  Chip,
} from "@mui/material";
import StatusBadge from "./StatusBadge";

interface ProgressCardProps {
  title: string;
  status: string;
  progress: number;
  completed?: number;
  total?: number;
  currentItem?: string;
  estimatedRemaining?: string;
  icon?: React.ReactNode;
  error?: string;
}

export default function ProgressCard({
  title,
  status,
  progress,
  completed,
  total,
  currentItem,
  estimatedRemaining,
  icon,
  error,
}: ProgressCardProps) {
  const clampedProgress = Math.min(100, Math.max(0, progress));

  const progressColor =
    status === "failed"
      ? "error"
      : status === "completed"
      ? "success"
      : "primary";

  return (
    <Card
      sx={{
        bgcolor: "background.paper",
        height: "100%",
      }}
    >
      <CardContent sx={{ p: 2, "&:last-child": { pb: 2 } }}>
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1.5 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            {icon && (
              <Box sx={{ color: "primary.main", display: "flex", alignItems: "center" }}>
                {icon}
              </Box>
            )}
            <Typography variant="subtitle2" fontWeight={600}>
              {title}
            </Typography>
          </Box>
          <StatusBadge status={status} />
        </Box>

        <Box sx={{ mb: 1 }}>
          <Box sx={{ display: "flex", justifyContent: "space-between", mb: 0.5 }}>
            <Typography variant="caption" color="text.secondary">
              {status === "running" && currentItem ? currentItem : " "}
            </Typography>
            <Typography variant="caption" fontWeight={700} color="primary.light">
              {clampedProgress.toFixed(0)}%
            </Typography>
          </Box>
          <LinearProgress
            variant="determinate"
            value={clampedProgress}
            color={progressColor}
            sx={{ height: 6 }}
          />
        </Box>

        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          {total !== undefined && completed !== undefined ? (
            <Typography variant="caption" color="text.secondary">
              {completed} / {total} items
            </Typography>
          ) : (
            <Box />
          )}
          {estimatedRemaining && status === "running" && (
            <Typography variant="caption" color="text.secondary">
              ~{estimatedRemaining} remaining
            </Typography>
          )}
        </Box>

        {error && (
          <Typography
            variant="caption"
            color="error.main"
            sx={{ display: "block", mt: 1, wordBreak: "break-word" }}
          >
            {error}
          </Typography>
        )}
      </CardContent>
    </Card>
  );
}
