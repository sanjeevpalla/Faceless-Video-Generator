import React, { useState, useEffect } from "react";
import {
  Box,
  Typography,
  Grid,
  Button,
  CircularProgress,
  Snackbar,
  IconButton,
  Tooltip,
  Chip,
} from "@mui/material";
import {
  Image as ImageIcon,
  RecordVoiceOver as VoiceIcon,
  Subtitles as SubtitleIcon,
  PhotoCamera as ThumbnailIcon,
  VideoLibrary as VideoIcon,
  Tag as MetadataIcon,
  Edit as RenameIcon,
  ContentCopy as DuplicateIcon,
  Refresh as RefreshIcon,
  Translate as TranslateIcon,
  Movie as ClipsIcon,
  AutoAwesomeMotion as ContentIcon,
} from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import { useProjectStore } from "../store";
import { useProject } from "../hooks/useProjects";
import { projectsApi } from "../api/projects";
import { jobsApi } from "../api/jobs";
import { imagesApi } from "../api/images";
import { voiceApi } from "../api/voice";
import { wan2Api } from "../api/wan2";
import { subtitlesApi } from "../api/subtitles";
import { thumbnailApi } from "../api/thumbnail";
import { videoApi } from "../api/video";
import ProgressCard from "../components/common/ProgressCard";
import StatusBadge from "../components/common/StatusBadge";
import ProjectRenameDialog from "../components/project/ProjectRenameDialog";
import LiveLogPanel from "../components/common/LiveLogPanel";
import QueueStatusPanel from "../components/common/QueueStatusPanel";
import { useProjectLogs } from "../hooks/useLogs";
import { LogEntry } from "../components/common/LogViewer";

const AI_FILE_KEYS = ["script", "scenes", "image_prompts", "thumbnail_prompt", "seo"];

const DEEP_DIVE_STEPS = [
  { key: "images",    label: "Image Generation",    icon: <ImageIcon />,     path: "/images" },
  { key: "voice",     label: "Voice Generation",     icon: <VoiceIcon />,     path: "/voice" },
  { key: "wan2",      label: "Clips / Animation",    icon: <ClipsIcon />,     path: "/clips" },
  { key: "subtitles", label: "Subtitle Generation",  icon: <SubtitleIcon />,  path: "/subtitles" },
  { key: "thumbnail", label: "Thumbnail",            icon: <ThumbnailIcon />, path: "/thumbnail" },
  { key: "video",     label: "Video Render",         icon: <VideoIcon />,     path: "/video" },
  { key: "metadata",  label: "Metadata",             icon: <MetadataIcon />,  path: "/video" },
];

const AI_NEWS_STEPS = [
  { key: "images",    label: "Image Generation",    icon: <ImageIcon />,     path: "/images" },
  { key: "voice",     label: "Voice Generation",     icon: <VoiceIcon />,     path: "/voice" },
  { key: "subtitles", label: "Subtitle Generation",  icon: <SubtitleIcon />,  path: "/subtitles" },
  { key: "thumbnail", label: "Thumbnail",            icon: <ThumbnailIcon />, path: "/thumbnail" },
  { key: "video",     label: "Video Render",         icon: <VideoIcon />,     path: "/video" },
  { key: "metadata",  label: "Metadata",             icon: <MetadataIcon />,  path: "/video" },
];

export default function ProjectPage() {
  const navigate = useNavigate();
  const currentProject = useProjectStore((s) => s.currentProject);
  const setCurrentProject = useProjectStore((s) => s.setCurrentProject);
  const generationProgress = useProjectStore((s) => s.generationProgress);
  const { data: project, isLoading, refetch } = useProject(currentProject?.id);
  const updateProgress = useProjectStore((s) => s.updateProgress);

  // On project open, snapshot actual output counts so already-done steps show 100%
  useEffect(() => {
    if (!currentProject?.id) return;
    const id = currentProject.id;
    Promise.allSettled([
      imagesApi.listForProject(id).then((r) => {
        if (r.total > 0)
          updateProgress("images", {
            status: r.generated === r.total ? "completed" : "pending",
            progress: r.generated === r.total ? 100 : Math.round((r.generated / r.total) * 100),
            completed: r.generated,
            total: r.total,
          });
      }),
      voiceApi.listForProject(id).then((r) => {
        if (r.total > 0) {
          const done = r.merged !== null;
          updateProgress("voice", {
            status: done ? "completed" : "pending",
            progress: done ? 100 : Math.round((r.generated / r.total) * 100),
            completed: r.generated,
            total: r.total,
          });
        }
      }),
      wan2Api.listForProject(id).then((r) => {
        if (r.total > 0)
          updateProgress("wan2", {
            status: r.animated === r.total ? "completed" : "pending",
            progress: r.animated === r.total ? 100 : Math.round((r.animated / r.total) * 100),
            completed: r.animated,
            total: r.total,
          });
      }),
      subtitlesApi.getStatus(id).then((r) => {
        if (r.status === "ready")
          updateProgress("subtitles", { status: "completed", progress: 100 });
      }),
      thumbnailApi.getStatus(id).then((r) => {
        if (r.status === "ready")
          updateProgress("thumbnail", { status: "completed", progress: 100 });
      }),
      videoApi.getStatus(id).then((r) => {
        if (r.status === "ready") {
          updateProgress("video", { status: "completed", progress: 100 });
          updateProgress("metadata", { status: "completed", progress: 100 });
        }
      }),
    ]);
  }, [currentProject?.id]);

  const [translating, setTranslating] = useState(false);
  const [snackMsg, setSnackMsg] = useState<string>("");
  const [renameOpen, setRenameOpen] = useState(false);

  const { data: serverLogs = [] } = useProjectLogs(currentProject?.id);

  if (!currentProject) {
    return (
      <Box sx={{ textAlign: "center", py: 8 }}>
        <Typography variant="h5" color="text.secondary" gutterBottom>
          No Project Selected
        </Typography>
        <Typography variant="body2" color="text.disabled" sx={{ mb: 3 }}>
          Go to the Dashboard to open or create a project.
        </Typography>
        <Button variant="contained" onClick={() => navigate("/")}>
          Go to Dashboard
        </Button>
      </Box>
    );
  }

  const displayProject = project || currentProject;
  const isAiNews = displayProject.project_type === "ai_news";
  const stepConfigs = isAiNews ? AI_NEWS_STEPS : DEEP_DIVE_STEPS;
  const contentLabel = "Content Generation";
  const inputFiles = displayProject.input_files_status || {};
  const contentReadyCount = AI_FILE_KEYS.filter((k) => inputFiles[k]?.status === "ready").length;

  const handleDuplicate = async () => {
    try {
      const dup = await projectsApi.duplicate(displayProject.id);
      setSnackMsg(`Duplicated as "${dup.name}"`);
    } catch {
      setSnackMsg("Duplicate failed");
    }
  };

  const handleTranslate = async () => {
    setTranslating(true);
    try {
      await jobsApi.trigger(displayProject.id, "translate");
      setSnackMsg("Translation job started");
    } catch {
      setSnackMsg("Failed to start translation");
    } finally {
      setTranslating(false);
    }
  };

  const logViewerEntries: LogEntry[] = serverLogs.map((log) => ({
    id: log.id,
    level: log.level as "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL",
    message: log.message,
    timestamp: log.timestamp,
    source: log.source || undefined,
  }));

  return (
    <Box>
      {/* Header */}
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", mb: 3 }}>
        <Box>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 0.5 }}>
            <Typography variant="h4" fontWeight={800}>
              {displayProject.name}
            </Typography>
            <StatusBadge status={displayProject.status} size="medium" />
            <Chip
              label={isAiNews ? "AI NEWS" : "DEEP DIVE"}
              size="small"
              color={isAiNews ? "warning" : "primary"}
              variant="outlined"
              sx={{ fontSize: "0.65rem", height: 20 }}
            />
            {displayProject.language && displayProject.language !== "en" && (
              <Chip
                icon={<TranslateIcon sx={{ fontSize: 14 }} />}
                label={displayProject.language.toUpperCase()}
                size="small"
                color="secondary"
                variant="outlined"
              />
            )}
            <Tooltip title="Rename project">
              <IconButton size="small" onClick={() => setRenameOpen(true)} sx={{ color: "text.secondary" }}>
                <RenameIcon fontSize="small" />
              </IconButton>
            </Tooltip>
            <Tooltip title="Duplicate project">
              <IconButton size="small" onClick={handleDuplicate} sx={{ color: "text.secondary" }}>
                <DuplicateIcon fontSize="small" />
              </IconButton>
            </Tooltip>
            <Tooltip title="Refresh">
              <IconButton size="small" onClick={() => refetch()} sx={{ color: "text.secondary" }}>
                <RefreshIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Box>
          {displayProject.description && (
            <Typography variant="body2" color="text.secondary">
              {displayProject.description}
            </Typography>
          )}
          <Typography variant="caption" color="text.disabled">
            ID: {displayProject.id.slice(0, 8)}… · {contentReadyCount}/5 AI files ready
          </Typography>
        </Box>

        <Box sx={{ display: "flex", gap: 1.5 }}>
          {displayProject.language && displayProject.language !== "en" && (() => {
            const tprog = generationProgress.translate;
            const isDone = tprog?.status === "completed";
            return (
              <Button
                variant={isDone ? "outlined" : "contained"}
                color="secondary"
                startIcon={translating ? <CircularProgress size={16} /> : <TranslateIcon />}
                onClick={handleTranslate}
                disabled={translating || tprog?.status === "running"}
                size="large"
              >
                {isDone ? "Re-translate" : "Translate"}
              </Button>
            );
          })()}
        </Box>
      </Box>

      {/* Generation Steps */}
      <Typography variant="h6" fontWeight={700} sx={{ mb: 2 }}>Generation Steps</Typography>
      <Grid container spacing={2} sx={{ mb: 4 }}>

        {/* Step 0: Content Generation */}
        <Grid item xs={12} sm={6} md={4}>
          <Box onClick={() => navigate("/content")} sx={{ cursor: "pointer" }}>
            <ProgressCard
              title={contentLabel}
              status={contentReadyCount >= 5 ? "completed" : contentReadyCount > 0 ? "running" : "pending"}
              progress={Math.round((contentReadyCount / 5) * 100)}
              completed={contentReadyCount}
              total={5}
              icon={<ContentIcon />}
            />
          </Box>
        </Grid>

        {/* Translation (non-English projects) */}
        {displayProject.language && displayProject.language !== "en" && (() => {
          const tprog = generationProgress.translate || { status: "pending" as const, progress: 0, total: 0, completed: 0 };
          return (
            <Grid item xs={12} sm={6} md={4} key="translate">
              <Box onClick={handleTranslate} sx={{ cursor: "pointer" }}>
                <ProgressCard
                  title="Translation"
                  status={tprog.status}
                  progress={tprog.progress}
                  completed={tprog.completed}
                  total={tprog.total}
                  icon={<TranslateIcon />}
                  error={tprog.error}
                />
              </Box>
            </Grid>
          );
        })()}

        {/* Generation steps */}
        {stepConfigs.map((step) => {
          const prog = generationProgress[step.key as keyof typeof generationProgress] || {
            status: "pending" as const,
            progress: 0,
            total: 0,
            completed: 0,
          };
          return (
            <Grid item xs={12} sm={6} md={4} key={step.key}>
              <Box onClick={() => navigate(step.path)} sx={{ cursor: "pointer" }}>
                <ProgressCard
                  title={step.label}
                  status={prog.status}
                  progress={prog.progress}
                  completed={prog.completed}
                  total={prog.total}
                  icon={step.icon}
                  error={prog.error}
                />
              </Box>
            </Grid>
          );
        })}
      </Grid>

      {/* Logs */}
      <Grid container spacing={3}>
        <Grid item xs={12} md={8}>
          <LiveLogPanel
            projectId={displayProject.id}
            serverLogs={logViewerEntries}
            maxHeight={400}
            title={`Live Logs · ${displayProject.name}`}
          />
        </Grid>
        <Grid item xs={12} md={4}>
          <QueueStatusPanel />
        </Grid>
      </Grid>

      {/* Rename Dialog */}
      <ProjectRenameDialog
        open={renameOpen}
        project={displayProject}
        onClose={() => setRenameOpen(false)}
        onSuccess={(updated) => {
          setCurrentProject({ ...displayProject, ...updated });
          setSnackMsg("Project renamed ✓");
          refetch();
        }}
      />

      <Snackbar
        open={!!snackMsg}
        autoHideDuration={4000}
        onClose={() => setSnackMsg("")}
        message={snackMsg}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      />
    </Box>
  );
}
