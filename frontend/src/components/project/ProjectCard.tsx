import React from "react";
import {
  Card,
  CardContent,
  CardActions,
  Box,
  Typography,
  IconButton,
  Tooltip,
  LinearProgress,
  Chip,
} from "@mui/material";
import {
  FolderOpen as OpenIcon,
  Archive as ArchiveIcon,
  Delete as DeleteIcon,
  ContentCopy as DuplicateIcon,
  Edit as RenameIcon,
  Translate as TranslateIcon,
} from "@mui/icons-material";
import StatusBadge from "../common/StatusBadge";
import { Project } from "../../store/projectStore";

interface ProjectCardProps {
  project: Project;
  onOpen: (project: Project) => void;
  onArchive: (project: Project) => void;
  onDelete: (project: Project) => void;
  onDuplicate?: (project: Project) => void;
  onRename?: (project: Project) => void;
}

const STEP_LABELS: { key: string; label: string }[] = [
  { key: "images", label: "Images" },
  { key: "voice", label: "Voice" },
  { key: "wan2", label: "Clips" },
  { key: "subtitles", label: "Subtitles" },
  { key: "thumbnail", label: "Thumbnail" },
  { key: "video", label: "Video" },
  { key: "metadata", label: "Metadata" },
];

function getOverallProgress(progress_state: Project["progress_state"]): number {
  if (!progress_state) return 0;
  const total = STEP_LABELS.reduce((acc, { key }) => {
    return acc + ((progress_state as any)[key]?.progress || 0);
  }, 0);
  return Math.round(total / STEP_LABELS.length);
}

const LANG_LABELS: Record<string, string> = {
  en: "English", te: "Telugu", hi: "Hindi", ta: "Tamil", kn: "Kannada",
  ml: "Malayalam", bn: "Bengali", mr: "Marathi", gu: "Gujarati",
  fr: "French", de: "German", es: "Spanish", ja: "Japanese",
  ko: "Korean", "zh-CN": "Chinese",
};

function stepColor(status: string | undefined): string {
  if (status === "completed") return "#00E676";
  if (status === "failed") return "#f44336";
  if (status === "running") return "#6C63FF";
  return "rgba(255,255,255,0.12)";
}

export default function ProjectCard({
  project,
  onOpen,
  onArchive,
  onDelete,
  onDuplicate,
  onRename,
}: ProjectCardProps) {
  const overallProgress = getOverallProgress(project.progress_state || {});

  const formatDate = (dateStr: string) => {
    const d = new Date(dateStr);
    return d.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  };

  return (
    <Card
      sx={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        cursor: "pointer",
        transition: "transform 0.15s ease, box-shadow 0.15s ease",
        "&:hover": {
          transform: "translateY(-2px)",
          boxShadow: "0 8px 24px rgba(108,99,255,0.2)",
        },
      }}
      onClick={() => onOpen(project)}
    >
      <CardContent sx={{ flex: 1, pb: 1 }}>
        <Box
          sx={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            mb: 1,
          }}
        >
          <Typography
            variant="subtitle1"
            fontWeight={700}
            noWrap
            sx={{ flex: 1, mr: 1 }}
            title={project.name}
          >
            {project.name}
          </Typography>
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, flexShrink: 0 }}>
            {project.language && (
              <Chip
                icon={<TranslateIcon sx={{ fontSize: "12px !important" }} />}
                label={LANG_LABELS[project.language] ?? project.language.toUpperCase()}
                size="small"
                variant="outlined"
                sx={{
                  height: 20,
                  fontSize: 10,
                  fontWeight: 600,
                  borderColor: project.language === "en" ? "rgba(255,255,255,0.15)" : "secondary.main",
                  color: project.language === "en" ? "text.disabled" : "secondary.main",
                  "& .MuiChip-icon": { color: "inherit" },
                }}
              />
            )}
            <StatusBadge status={project.status} />
          </Box>
        </Box>

        {project.description && (
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{
              display: "-webkit-box",
              WebkitLineClamp: 2,
              WebkitBoxOrient: "vertical",
              overflow: "hidden",
              mb: 1.5,
            }}
          >
            {project.description}
          </Typography>
        )}

        <Box sx={{ mb: 1.5 }}>
          <Box
            sx={{ display: "flex", justifyContent: "space-between", mb: 0.5 }}
          >
            <Typography variant="caption" color="text.secondary">
              Overall progress
            </Typography>
            <Typography variant="caption" fontWeight={700} color="primary.light">
              {overallProgress}%
            </Typography>
          </Box>
          <LinearProgress
            variant="determinate"
            value={overallProgress}
            sx={{ height: 4, mb: 1 }}
          />
          <Box sx={{ display: "flex", gap: 0.5, alignItems: "center" }}>
            {STEP_LABELS.map(({ key, label }) => {
              const stepData = (project.progress_state as any)?.[key];
              const status: string = stepData?.status || "pending";
              return (
                <Tooltip key={key} title={`${label}: ${status}`} placement="top">
                  <Box
                    sx={{
                      flex: 1,
                      height: 4,
                      borderRadius: 1,
                      bgcolor: stepColor(status),
                      transition: "background-color 0.2s",
                    }}
                  />
                </Tooltip>
              );
            })}
          </Box>
        </Box>

        <Box sx={{ display: "flex", flexDirection: "column", gap: 0.25 }}>
          <Typography variant="caption" color="text.secondary">
            Created: {formatDate(project.created_at)}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            Updated: {formatDate(project.updated_at)}
          </Typography>
        </Box>
      </CardContent>

      <CardActions
        sx={{
          px: 2,
          pb: 1.5,
          pt: 0,
          gap: 0.5,
          borderTop: "1px solid rgba(255,255,255,0.04)",
          justifyContent: "flex-end",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <Tooltip title="Open project">
          <IconButton size="small" onClick={() => onOpen(project)} color="primary">
            <OpenIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        {onRename && (
          <Tooltip title="Rename">
            <IconButton size="small" onClick={() => onRename(project)} sx={{ color: "text.secondary" }}>
              <RenameIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        )}
        {onDuplicate && (
          <Tooltip title="Duplicate">
            <IconButton size="small" onClick={() => onDuplicate(project)} sx={{ color: "text.secondary" }}>
              <DuplicateIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        )}
        <Tooltip title="Archive">
          <IconButton size="small" onClick={() => onArchive(project)} sx={{ color: "text.secondary" }}>
            <ArchiveIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        <Tooltip title="Delete">
          <IconButton size="small" onClick={() => onDelete(project)} color="error">
            <DeleteIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </CardActions>
    </Card>
  );
}
