import React from "react";
import { Chip, ChipProps } from "@mui/material";
import {
  CheckCircle as CheckIcon,
  Error as ErrorIcon,
  HourglassEmpty as PendingIcon,
  Sync as ProcessingIcon,
  Archive as ArchiveIcon,
} from "@mui/icons-material";

type StatusValue =
  | "ready"
  | "missing"
  | "processing"
  | "failed"
  | "completed"
  | "pending"
  | "running"
  | "paused"
  | "cancelled"
  | "created"
  | "archived"
  | string;

const STATUS_CONFIG: Record<string, { color: string; bg: string; icon: React.ReactElement; label: string }> = {
  ready: { color: "#00E676", bg: "rgba(0,230,118,0.12)", icon: <CheckIcon fontSize="inherit" />, label: "Ready" },
  completed: { color: "#00E676", bg: "rgba(0,230,118,0.12)", icon: <CheckIcon fontSize="inherit" />, label: "Completed" },
  missing: { color: "#FF5252", bg: "rgba(255,82,82,0.12)", icon: <ErrorIcon fontSize="inherit" />, label: "Missing" },
  failed: { color: "#FF5252", bg: "rgba(255,82,82,0.12)", icon: <ErrorIcon fontSize="inherit" />, label: "Failed" },
  processing: { color: "#FFB300", bg: "rgba(255,179,0,0.12)", icon: <ProcessingIcon fontSize="inherit" />, label: "Processing" },
  running: { color: "#FFB300", bg: "rgba(255,179,0,0.12)", icon: <ProcessingIcon fontSize="inherit" />, label: "Running" },
  pending: { color: "#9090A8", bg: "rgba(144,144,168,0.12)", icon: <PendingIcon fontSize="inherit" />, label: "Pending" },
  created: { color: "#9090A8", bg: "rgba(144,144,168,0.12)", icon: <PendingIcon fontSize="inherit" />, label: "Created" },
  paused: { color: "#29B6F6", bg: "rgba(41,182,246,0.12)", icon: <PendingIcon fontSize="inherit" />, label: "Paused" },
  cancelled: { color: "#9090A8", bg: "rgba(144,144,168,0.12)", icon: <PendingIcon fontSize="inherit" />, label: "Cancelled" },
  archived: { color: "#505068", bg: "rgba(80,80,104,0.12)", icon: <ArchiveIcon fontSize="inherit" />, label: "Archived" },
};

interface StatusBadgeProps {
  status: StatusValue;
  size?: ChipProps["size"];
  showIcon?: boolean;
  label?: string;
}

export default function StatusBadge({
  status,
  size = "small",
  showIcon = true,
  label,
}: StatusBadgeProps) {
  const config = STATUS_CONFIG[status.toLowerCase()] || {
    color: "#9090A8",
    bg: "rgba(144,144,168,0.12)",
    icon: <PendingIcon fontSize="inherit" />,
    label: status,
  };

  return (
    <Chip
      label={label || config.label}
      size={size}
      icon={showIcon ? config.icon : undefined}
      sx={{
        bgcolor: config.bg,
        color: config.color,
        border: `1px solid ${config.color}33`,
        fontWeight: 600,
        fontSize: size === "small" ? "0.7rem" : "0.8rem",
        height: size === "small" ? 22 : 28,
        "& .MuiChip-icon": {
          color: config.color,
          fontSize: "0.85rem",
          ml: "6px",
        },
      }}
    />
  );
}
