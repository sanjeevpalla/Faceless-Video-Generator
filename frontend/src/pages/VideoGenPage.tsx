import React, { useState, useRef } from "react";
import {
  Box,
  Typography,
  Card,
  CardContent,
  Button,
  Grid,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  LinearProgress,
  List,
  ListItem,
  ListItemText,
  Chip,
  Alert,
  Skeleton,
  CircularProgress,
  Tooltip,
  Divider,
  IconButton,
  Tabs,
  Tab,
} from "@mui/material";
import {
  VideoLibrary as VideoIcon,
  PlayArrow as PlayIcon,
  Pause as PauseIcon,
  FolderOpen as FolderIcon,
  FileDownload as ExportIcon,
  CheckCircle as CheckIcon,
  HourglassEmpty as PendingIcon,
  Sync as ProcessingIcon,
  Build as FFmpegIcon,
  Subtitles as SubIcon,
  RecordVoiceOver as AudioIcon,
  Image as ImageIcon,
  Refresh as RefreshIcon,
  DeleteForever as DeleteIcon,
  CloudUpload as UploadIcon,
  PictureInPictureAlt as NarratorIcon,
  Close as CloseIcon,
  Smartphone as ShortsIcon,
  Download as DownloadIcon,
  ErrorOutline as ErrorOutlineIcon,
} from "@mui/icons-material";
import { useProjectStore } from "../store";
import { useTriggerJob } from "../hooks/useJobs";
import { useVideoStatus, useRenderAssets, useFFmpegStatus, useVideoTemplates, VIDEO_KEYS } from "../hooks/useVideo";
import { videoApi, VideoTemplate } from "../api/video";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { narratorApi, NarratorClip } from "../api/narrator";
import { shortsApi, ShortClip } from "../api/shorts";
import ProgressCard from "../components/common/ProgressCard";
import MetadataPanel from "../components/project/MetadataPanel";
import DeleteConfirmDialog from "../components/common/DeleteConfirmDialog";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function formatDuration(s: number): string {
  if (!s || s <= 0) return "0:00";
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

function formatFileSize(mb: number): string {
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
  return `${mb.toFixed(1)} MB`;
}

// ---------------------------------------------------------------------------
// FFmpeg status chip
// ---------------------------------------------------------------------------
function FFmpegStatusChip() {
  const { data, isLoading } = useFFmpegStatus();
  if (isLoading) return <Chip label="Checking FFmpeg…" size="small" sx={{ height: 22 }} />;
  const ok = data?.ready ?? false;
  return (
    <Tooltip title={ok ? `FFmpeg found: ${data?.ffmpeg_path}\n${data?.version}` : "FFmpeg not found — install from ffmpeg.org and add to PATH"}>
      <Chip
        icon={<FFmpegIcon sx={{ fontSize: "12px !important" }} />}
        label={ok ? `FFmpeg Ready${data?.version ? ` · ${data.version.split(" ")[2] ?? ""}` : ""}` : "FFmpeg Not Found"}
        size="small"
        sx={{
          height: 24,
          fontSize: "0.7rem",
          bgcolor: ok ? "rgba(0,230,118,0.1)" : "rgba(255,82,82,0.1)",
          color: ok ? "success.main" : "error.main",
          border: `1px solid ${ok ? "rgba(0,230,118,0.3)" : "rgba(255,82,82,0.3)"}`,
        }}
      />
    </Tooltip>
  );
}

// ---------------------------------------------------------------------------
// Asset readiness row
// ---------------------------------------------------------------------------
function AssetRow({ icon, label, ready, value }: { icon: React.ReactNode; label: string; ready: boolean; value?: string }) {
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, py: 0.75 }}>
      <Box sx={{ color: ready ? "success.main" : "text.disabled", display: "flex" }}>{icon}</Box>
      <Typography variant="body2" sx={{ flex: 1, color: ready ? "text.primary" : "text.secondary" }}>
        {label}
      </Typography>
      {value && (
        <Typography variant="caption" color="text.disabled">
          {value}
        </Typography>
      )}
      <Chip
        label={ready ? "Ready" : "Missing"}
        size="small"
        sx={{
          height: 18,
          fontSize: "0.6rem",
          bgcolor: ready ? "rgba(0,230,118,0.1)" : "rgba(255,82,82,0.08)",
          color: ready ? "success.main" : "error.main",
        }}
      />
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Template selector card
// ---------------------------------------------------------------------------
interface TemplateSelectorProps {
  value: string;
  onChange: (v: string) => void;
  templates: VideoTemplate[];
}

const TEMPLATE_DESCRIPTIONS: Record<string, string> = {
  documentary: "Cinematic Ken Burns, crossfade transitions, warm audio mix",
  news: "Clean cuts, neutral grade, clear lower thirds",
  technology: "Fade transitions, cool blue grade, dynamic zoom-out",
  finance: "Subtle zoom, warm tones, professional feel",
  educational: "Balanced zoom, neutral grade, yellow subtitle style",
  history: "Slow Ken Burns, sepia colour grade, atmospheric",
};

function TemplateSelector({ value, onChange, templates }: TemplateSelectorProps) {
  return (
    <FormControl fullWidth size="small">
      <InputLabel>Video Template</InputLabel>
      <Select value={value} onChange={(e) => onChange(e.target.value)} label="Video Template">
        {templates.map((t) => (
          <MenuItem key={t.id} value={t.id}>
            <Box>
              <Typography variant="body2" fontWeight={600}>
                {t.label}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {TEMPLATE_DESCRIPTIONS[t.id] ?? `${t.transition} · ${t.motion}`}
              </Typography>
            </Box>
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );
}

// ---------------------------------------------------------------------------
// Scene render progress list
// ---------------------------------------------------------------------------
interface SceneProgressListProps {
  totalScenes: number;
  completedScenes: number;
  currentScene: number | null;
  isRunning: boolean;
}

function SceneProgressList({ totalScenes, completedScenes, currentScene, isRunning }: SceneProgressListProps) {
  const display = Math.min(totalScenes, 20);
  return (
    <Box sx={{ maxHeight: 320, overflow: "auto" }}>
      {Array.from({ length: display }, (_, i) => {
        const sceneNum = i + 1;
        const done = sceneNum <= completedScenes;
        const active = isRunning && sceneNum === currentScene;
        return (
          <Box
            key={sceneNum}
            sx={{
              display: "flex",
              alignItems: "center",
              gap: 1.5,
              py: 0.6,
              px: 1,
              borderRadius: 1.5,
              mb: 0.4,
              bgcolor: active ? "rgba(255,179,0,0.07)" : "transparent",
              border: `1px solid ${active ? "rgba(255,179,0,0.2)" : "rgba(255,255,255,0.04)"}`,
            }}
          >
            {done ? (
              <CheckIcon sx={{ fontSize: 14, color: "success.main", flexShrink: 0 }} />
            ) : active ? (
              <ProcessingIcon sx={{ fontSize: 14, color: "warning.main", flexShrink: 0, animation: "spin 1s linear infinite", "@keyframes spin": { from: { transform: "rotate(0deg)" }, to: { transform: "rotate(360deg)" } } }} />
            ) : (
              <PendingIcon sx={{ fontSize: 14, color: "text.disabled", flexShrink: 0 }} />
            )}
            <Typography variant="caption" sx={{ flex: 1, color: active ? "warning.main" : done ? "text.primary" : "text.disabled" }}>
              Scene {sceneNum}
            </Typography>
            <Chip
              label={done ? "done" : active ? "rendering" : "pending"}
              size="small"
              sx={{
                height: 16,
                fontSize: "0.58rem",
                bgcolor: done ? "rgba(0,230,118,0.08)" : active ? "rgba(255,179,0,0.1)" : "rgba(255,255,255,0.03)",
                color: done ? "success.main" : active ? "warning.main" : "text.disabled",
              }}
            />
          </Box>
        );
      })}
      {totalScenes > display && (
        <Typography variant="caption" color="text.disabled" sx={{ px: 1 }}>
          + {totalScenes - display} more scenes…
        </Typography>
      )}
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Video preview player
// ---------------------------------------------------------------------------
interface VideoPreviewProps {
  projectId: string;
  videoReady: boolean;
  manifest: ReturnType<typeof useVideoStatus>["data"] extends infer T ? (T extends { manifest: infer M } ? M : null) : null;
}

function VideoPreview({ projectId, videoReady, manifest }: VideoPreviewProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);

  const videoUrl = videoApi.getVideoUrl(projectId);

  const toggle = () => {
    const v = videoRef.current;
    if (!v) return;
    if (playing) { v.pause(); setPlaying(false); }
    else { v.play(); setPlaying(true); }
  };

  if (!videoReady) {
    return (
      <Box
        sx={{
          width: "100%",
          aspectRatio: "16/9",
          bgcolor: "rgba(255,255,255,0.02)",
          borderRadius: 2,
          border: "2px dashed rgba(255,255,255,0.06)",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 1,
        }}
      >
        <VideoIcon sx={{ fontSize: 40, color: "text.disabled" }} />
        <Typography variant="caption" color="text.disabled">
          Video not rendered yet
        </Typography>
      </Box>
    );
  }

  return (
    <Box>
      <Box sx={{ position: "relative", borderRadius: 2, overflow: "hidden", bgcolor: "#000", cursor: "pointer" }} onClick={toggle}>
        <video
          ref={videoRef}
          src={videoUrl}
          style={{ width: "100%", display: "block" }}
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onEnded={() => setPlaying(false)}
          controls
          preload="metadata"
        />
      </Box>
      {manifest && (
        <Box sx={{ mt: 1, display: "flex", gap: 1, flexWrap: "wrap" }}>
          {[
            { label: manifest.resolution },
            { label: `${manifest.fps} FPS` },
            { label: formatDuration(manifest.duration) },
            { label: formatFileSize(manifest.size_mb) },
            { label: manifest.template },
          ].map((info, i) => (
            <Chip
              key={i}
              label={info.label}
              size="small"
              sx={{ height: 20, fontSize: "0.65rem", bgcolor: "rgba(255,255,255,0.06)" }}
            />
          ))}
        </Box>
      )}
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Narrator clips panel
// ---------------------------------------------------------------------------
function NarratorClipsPanel({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const NARRATOR_KEY = ["narrator", projectId];

  const { data, isLoading } = useQuery({
    queryKey: NARRATOR_KEY,
    queryFn: () => narratorApi.list(projectId),
    enabled: !!projectId,
  });

  const deleteMutation = useMutation({
    mutationFn: (filename: string) => narratorApi.delete(projectId, filename),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: NARRATOR_KEY }),
  });

  const clips: NarratorClip[] = data?.clips ?? [];

  const handleFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const mp4s = Array.from(files).filter((f) => f.name.toLowerCase().endsWith(".mp4"));
    if (mp4s.length === 0) { setUploadError("Only .mp4 files are accepted"); return; }
    setUploadError(null);
    setUploading(true);
    try {
      await narratorApi.upload(projectId, mp4s);
      queryClient.invalidateQueries({ queryKey: NARRATOR_KEY });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Upload failed";
      setUploadError(msg);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    handleFiles(e.dataTransfer.files);
  };

  return (
    <Card sx={{ mb: 2 }}>
      <CardContent sx={{ p: 2.5 }}>
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 1.5 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <NarratorIcon sx={{ fontSize: 16, color: clips.length > 0 ? "info.main" : "text.disabled" }} />
            <Typography variant="subtitle1" fontWeight={700}>
              Narrator Clips
            </Typography>
          </Box>
          <Chip
            label={clips.length > 0 ? `${clips.length} clip${clips.length > 1 ? "s" : ""}` : "None"}
            size="small"
            sx={{
              height: 18,
              fontSize: "0.6rem",
              bgcolor: clips.length > 0 ? "rgba(2,136,209,0.12)" : "rgba(255,255,255,0.04)",
              color: clips.length > 0 ? "info.main" : "text.disabled",
            }}
          />
        </Box>

        {/* Clip list */}
        {isLoading ? (
          <Skeleton variant="rounded" height={36} sx={{ mb: 1 }} />
        ) : clips.length > 0 ? (
          <Box sx={{ mb: 1.5 }}>
            {clips.map((clip) => (
              <Box
                key={clip.filename}
                sx={{
                  display: "flex",
                  alignItems: "center",
                  gap: 1,
                  py: 0.5,
                  px: 0.75,
                  borderRadius: 1,
                  "&:hover": { bgcolor: "rgba(255,255,255,0.03)" },
                }}
              >
                <VideoIcon sx={{ fontSize: 13, color: "info.main", flexShrink: 0 }} />
                <Typography
                  variant="caption"
                  sx={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                >
                  {clip.filename}
                </Typography>
                <Typography variant="caption" color="text.disabled" sx={{ flexShrink: 0 }}>
                  {clip.size_mb} MB
                </Typography>
                <IconButton
                  size="small"
                  onClick={() => deleteMutation.mutate(clip.filename)}
                  disabled={deleteMutation.isPending}
                  sx={{ p: 0.25 }}
                >
                  <CloseIcon sx={{ fontSize: 13, color: "text.disabled" }} />
                </IconButton>
              </Box>
            ))}
          </Box>
        ) : (
          <Typography variant="caption" color="text.disabled" display="block" sx={{ mb: 1.5 }}>
            No clips yet — upload .mp4 files below
          </Typography>
        )}

        {/* Drop zone / upload button */}
        <Box
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          sx={{
            border: `1px dashed ${dragging ? "rgba(2,136,209,0.6)" : "rgba(255,255,255,0.1)"}`,
            borderRadius: 1.5,
            p: 1.5,
            textAlign: "center",
            bgcolor: dragging ? "rgba(2,136,209,0.06)" : "transparent",
            transition: "all 0.15s",
            cursor: "pointer",
          }}
          onClick={() => fileInputRef.current?.click()}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".mp4"
            multiple
            hidden
            onChange={(e) => handleFiles(e.target.files)}
          />
          {uploading ? (
            <CircularProgress size={18} sx={{ color: "info.main" }} />
          ) : (
            <>
              <UploadIcon sx={{ fontSize: 20, color: "text.disabled", mb: 0.5 }} />
              <Typography variant="caption" color="text.disabled" display="block">
                Click or drag .mp4 clips here
              </Typography>
            </>
          )}
        </Box>

        {uploadError && (
          <Alert severity="error" sx={{ mt: 1, py: 0.25, fontSize: "0.7rem" }}>
            {uploadError}
          </Alert>
        )}

        {clips.length > 0 && (
          <Typography variant="caption" color="text.disabled" display="block" sx={{ mt: 1 }}>
            Clips cycle and loop as narrator PiP during render
          </Typography>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// YouTube Shorts panel
// ---------------------------------------------------------------------------
function formatDur(s: number) {
  if (!s) return "0:00";
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

function ShortsPanel({ projectId, assetsReady }: { projectId: string; assetsReady: boolean }) {
  const queryClient = useQueryClient();
  const SHORTS_KEY = ["shorts", projectId];
  const COUNT = 5;

  const { data } = useQuery({
    queryKey: SHORTS_KEY,
    queryFn: () => shortsApi.getStatus(projectId),
    enabled: !!projectId,
    refetchInterval: (query) => ((query.state.data as any)?.state === "generating" ? 3000 : 30_000),
    staleTime: 2000,
  });

  const generateMutation = useMutation({
    mutationFn: () => shortsApi.generate(projectId, COUNT),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: SHORTS_KEY }),
  });

  const deleteMutation = useMutation({
    mutationFn: () => shortsApi.deleteAll(projectId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: SHORTS_KEY }),
  });

  const state = data?.state ?? "idle";
  const isGenerating = state === "generating";
  const shorts: ShortClip[] = data?.shorts ?? [];
  const hasShorts = shorts.length > 0;
  const placeholders = Array.from({ length: COUNT }, (_, i) => i + 1);

  return (
    <Box>
      {/* Header */}
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 3 }}>
        <Box>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <ShortsIcon sx={{ color: "error.main" }} />
            <Typography variant="h6" fontWeight={700}>YouTube Shorts</Typography>
            <Chip label="30 sec · 1080×1920 · 9:16" size="small"
              sx={{ height: 18, fontSize: "0.6rem", bgcolor: "rgba(255,82,82,0.1)", color: "error.light" }} />
          </Box>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            Builds {COUNT} content-rich 30-second shorts from scene clips — TF-IDF topic scoring, no subtitles
          </Typography>
        </Box>
        <Box sx={{ display: "flex", gap: 1 }}>
          {hasShorts && (
            <Button size="small" variant="outlined" color="error"
              startIcon={deleteMutation.isPending ? <CircularProgress size={12} color="inherit" /> : <DeleteIcon />}
              onClick={() => deleteMutation.mutate()}
              disabled={deleteMutation.isPending || isGenerating}>
              Delete All
            </Button>
          )}
          <Tooltip title={!assetsReady ? "Generate scene images first" : ""}>
            <span>
              <Button variant="contained" color="error"
                startIcon={isGenerating ? <CircularProgress size={14} color="inherit" /> : <ShortsIcon />}
                onClick={() => generateMutation.mutate()}
                disabled={!assetsReady || isGenerating || generateMutation.isPending}>
                {isGenerating ? "Generating…" : hasShorts ? "Regenerate" : `Generate ${COUNT} Shorts`}
              </Button>
            </span>
          </Tooltip>
        </Box>
      </Box>

      {/* Progress */}
      {isGenerating && (
        <Box sx={{ mb: 3 }}>
          <Box sx={{ display: "flex", justifyContent: "space-between", mb: 0.5 }}>
            <Typography variant="caption" color="text.secondary">{data?.message || "Selecting highlights…"}</Typography>
            <Typography variant="caption" fontWeight={700} color="error.light">{(data?.progress ?? 0).toFixed(0)}%</Typography>
          </Box>
          <LinearProgress variant="determinate" value={data?.progress ?? 0} color="error" sx={{ height: 8, borderRadius: 2 }} />
        </Box>
      )}

      {state === "error" && (
        <Alert severity="error" sx={{ mb: 3 }} icon={<ErrorOutlineIcon />}>
          {data?.message || "Shorts generation failed"}
        </Alert>
      )}

      {/* Cards */}
      <Grid container spacing={2}>
        {(hasShorts ? shorts : placeholders.map((i) => ({
          index: i, filename: "", title: `Highlight ${i}`, start_time: 0,
          duration: 30, size_mb: 0, status: "pending" as const,
        }))).map((short: any) => {
          const ready = short.status === "ready" && short.filename;
          const url = ready ? shortsApi.getShortUrl(projectId, short.filename) : null;
          return (
            <Grid item xs={12} sm={6} md={4} lg={2.4} key={short.index}>
              <Card sx={{
                height: "100%",
                border: ready ? "1px solid rgba(255,82,82,0.3)"
                  : isGenerating ? "1px solid rgba(255,179,0,0.2)"
                  : "1px solid rgba(255,255,255,0.06)",
                transition: "border-color 0.2s",
              }}>
                <CardContent sx={{ p: 1.5, "&:last-child": { pb: 1.5 } }}>
                  {/* 9:16 preview */}
                  <Box sx={{
                    aspectRatio: "9/16",
                    bgcolor: "rgba(255,255,255,0.03)",
                    borderRadius: 1.5,
                    mb: 1.5,
                    overflow: "hidden",
                    position: "relative",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}>
                    {ready && url ? (
                      <video
                        style={{ width: "100%", height: "100%", objectFit: "cover" }}
                        preload="none"
                        muted
                        playsInline
                        onMouseEnter={(e) => {
                          const v = e.currentTarget as HTMLVideoElement;
                          if (!v.src) v.src = url;
                          v.play();
                        }}
                        onMouseLeave={(e) => {
                          const v = e.currentTarget as HTMLVideoElement;
                          v.pause(); v.currentTime = 0;
                        }}
                      />
                    ) : isGenerating ? (
                      <CircularProgress size={24} color="warning" />
                    ) : (
                      <ShortsIcon sx={{ fontSize: 32, color: "text.disabled" }} />
                    )}

                    {/* Index badge */}
                    <Chip label={`#${short.index}/${COUNT}`} size="small" sx={{
                      position: "absolute", top: 6, left: 6,
                      height: 18, fontSize: "0.58rem",
                      bgcolor: "rgba(0,0,0,0.7)", color: "white", fontWeight: 700,
                    }} />

                    {/* Start time badge */}
                    {(ready || short.start_time > 0) && (
                      <Chip label={`@${formatDur(short.start_time)}`} size="small" sx={{
                        position: "absolute", top: 6, right: 6,
                        height: 18, fontSize: "0.56rem",
                        bgcolor: "rgba(255,82,82,0.75)", color: "white",
                      }} />
                    )}

                    {short.status === "error" && (
                      <Chip label="Error" size="small" color="error" sx={{
                        position: "absolute", bottom: 6, left: 6, height: 18, fontSize: "0.58rem",
                      }} />
                    )}
                  </Box>

                  {/* Title */}
                  <Tooltip title={short.title || ""}>
                    <Typography variant="caption" fontWeight={600}
                      sx={{ display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", mb: 0.5 }}>
                      {short.title || `Short ${short.index}`}
                    </Typography>
                  </Tooltip>

                  {/* Meta */}
                  <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                    <Typography variant="caption" color="text.secondary">30 sec</Typography>
                    <Typography variant="caption" color="text.disabled">
                      {ready && short.size_mb > 0 ? `${short.size_mb} MB` : ""}
                    </Typography>
                  </Box>

                  {ready && url && (
                    <Button fullWidth size="small" variant="outlined" color="error"
                      startIcon={<DownloadIcon sx={{ fontSize: 13 }} />}
                      component="a" href={url} download={short.filename}
                      sx={{ fontSize: "0.7rem", py: 0.4 }}>
                      Download
                    </Button>
                  )}
                </CardContent>
              </Card>
            </Grid>
          );
        })}
      </Grid>

      {!hasShorts && !isGenerating && (
        <Box sx={{ textAlign: "center", py: 4 }}>
          <ShortsIcon sx={{ fontSize: 40, mb: 1, opacity: 0.25, color: "text.disabled" }} />
          <Typography variant="body2" color="text.disabled">
            {assetsReady
              ? `Click "Generate ${COUNT} Shorts" — TF-IDF selects the ${COUNT} most content-rich scene groups`
              : "Generate scene images first, then create shorts"}
          </Typography>
        </Box>
      )}
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function VideoGenPage() {
  const currentProject = useProjectStore((s) => s.currentProject);
  const generationProgress = useProjectStore((s) => s.generationProgress);
  const triggerJob = useTriggerJob();

  const queryClient = useQueryClient();
  const { data: videoStatus, isLoading: statusLoading, refetch: refetchStatus } = useVideoStatus(currentProject?.id);
  const { data: assets, isLoading: assetsLoading } = useRenderAssets(currentProject?.id);
  const { data: templatesData } = useVideoTemplates();

  const [selectedTemplate, setSelectedTemplate] = useState("documentary");
  const [isRendering, setIsRendering] = useState(false);
  const [activeTab, setActiveTab] = useState(0);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const videoProgress = generationProgress.video;
  const isRunning = videoProgress.status === "running";
  const videoReady = videoStatus?.status === "ready";
  const templates = templatesData?.templates ?? [];

  // Derive current rendering scene from progress
  const currentSceneNum = videoProgress.completed > 0
    ? Math.min(videoProgress.completed + 1, videoProgress.total || 999)
    : null;

  const handleRender = async () => {
    if (!currentProject) return;
    setIsRendering(true);
    try {
      await triggerJob.mutateAsync({ projectId: currentProject.id, jobType: "video" });
    } catch (err) {
      console.error("Video render failed:", err);
    } finally {
      setIsRendering(false);
    }
  };

  const handleDownload = () => {
    if (!currentProject) return;
    window.location.href = videoApi.getVideoUrl(currentProject.id);
  };

  const handleDelete = async () => {
    if (!currentProject) return;
    setDeleting(true);
    try {
      await videoApi.deleteOutputs(currentProject.id);
      queryClient.invalidateQueries({ queryKey: VIDEO_KEYS.status(currentProject.id) });
      queryClient.invalidateQueries({ queryKey: VIDEO_KEYS.assets(currentProject.id) });
    } catch (err) {
      console.error("Failed to delete video:", err);
    } finally {
      setDeleting(false);
      setDeleteOpen(false);
    }
  };

  const canRender = (assets?.can_render ?? false) && !isRunning;

  if (!currentProject) {
    return (
      <Box sx={{ textAlign: "center", py: 8 }}>
        <Typography color="text.secondary">No project selected.</Typography>
      </Box>
    );
  }

  return (
    <Box>
      {/* Header */}
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 3 }}>
        <Box>
          <Typography variant="h4" fontWeight={800} gutterBottom>
            Video Generation
          </Typography>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
            <Typography variant="body2" color="text.secondary">
              Assemble final video with MoviePy + FFmpeg
            </Typography>
            <FFmpegStatusChip />
          </Box>
        </Box>
        <Box sx={{ display: "flex", gap: 1.5 }}>
          {videoReady && (
            <>
              <Tooltip title="Download MP4">
                <Button variant="outlined" startIcon={<ExportIcon />} onClick={handleDownload} color="success">
                  Export MP4
                </Button>
              </Tooltip>
              <Tooltip title="Refresh status">
                <IconButton onClick={() => refetchStatus()} sx={{ color: "text.secondary" }}>
                  <RefreshIcon />
                </IconButton>
              </Tooltip>
              <Button
                variant="outlined"
                color="error"
                startIcon={<DeleteIcon />}
                onClick={() => setDeleteOpen(true)}
                disabled={isRunning}
                size="large"
              >
                Delete
              </Button>
            </>
          )}
          <Button
            variant="contained"
            startIcon={isRunning || isRendering ? <CircularProgress size={16} color="inherit" /> : <VideoIcon />}
            onClick={handleRender}
            disabled={!canRender || isRendering}
            size="large"
          >
            {isRunning ? "Rendering…" : videoReady ? "Re-render" : "Render Video"}
          </Button>
        </Box>
      </Box>

      <DeleteConfirmDialog
        open={deleteOpen}
        title="Delete Rendered Video"
        description="Delete the rendered video file? All source assets (images, audio, subtitles) will be kept — only the final MP4 will be removed."
        loading={deleting}
        onConfirm={handleDelete}
        onCancel={() => setDeleteOpen(false)}
      />

      {/* Tabs */}
      <Tabs
        value={activeTab}
        onChange={(_, v) => setActiveTab(v)}
        sx={{ mb: 3, borderBottom: "1px solid rgba(255,255,255,0.06)" }}
      >
        <Tab label="Render" />
        <Tab label="Shorts" icon={<ShortsIcon sx={{ fontSize: 16 }} />} iconPosition="start" />
        <Tab label="YouTube Metadata" />
      </Tabs>

      {activeTab === 2 && (
        <MetadataPanel projectId={currentProject.id} />
      )}

      {activeTab === 1 && (
        <ShortsPanel projectId={currentProject.id} assetsReady={(assets?.images_ready ?? 0) > 0} />
      )}

      {activeTab === 0 && <>

      {/* Asset readiness */}
      {!canRender && !isRunning && (
        <Alert severity={assets?.images_ready === 0 ? "error" : "warning"} sx={{ mb: 3, borderRadius: 2 }}>
          {assets?.images_ready === 0
            ? "No scene images found — generate images first."
            : "Some assets are missing — check the readiness panel below."}
        </Alert>
      )}

      {/* Progress */}
      {isRunning && (
        <Box sx={{ mb: 3 }}>
          <Box sx={{ display: "flex", justifyContent: "space-between", mb: 0.5 }}>
            <Typography variant="caption" color="text.secondary">
              {videoProgress.progress < 15
                ? "Building scene clips…"
                : videoProgress.progress < 75
                ? `Rendering frame-by-frame… (scene ${videoProgress.completed + 1}/${videoProgress.total})`
                : videoProgress.progress < 95
                ? "Burning subtitles via FFmpeg…"
                : "Finalising output…"}
            </Typography>
            <Typography variant="caption" fontWeight={700} color="primary.light">
              {videoProgress.progress.toFixed(0)}%
            </Typography>
          </Box>
          <LinearProgress variant="determinate" value={videoProgress.progress} sx={{ height: 10, borderRadius: 2 }} />
        </Box>
      )}

      <Grid container spacing={3}>
        {/* Left column */}
        <Grid item xs={12} md={4}>
          {/* Template selector */}
          <Card sx={{ mb: 2 }}>
            <CardContent sx={{ p: 2.5 }}>
              <Typography variant="subtitle1" fontWeight={700} sx={{ mb: 2 }}>
                Template
              </Typography>
              {templates.length > 0 ? (
                <TemplateSelector
                  value={selectedTemplate}
                  onChange={setSelectedTemplate}
                  templates={templates}
                />
              ) : (
                <Skeleton variant="rounded" height={40} />
              )}

              {templates.length > 0 && (
                <Box sx={{ mt: 2, display: "flex", flexDirection: "column", gap: 0.5 }}>
                  {(templates.find((t) => t.id === selectedTemplate)
                    ? [
                        { label: "Transition", value: templates.find((t) => t.id === selectedTemplate)!.transition },
                        { label: "Motion", value: templates.find((t) => t.id === selectedTemplate)!.motion },
                        { label: "Subtitle", value: templates.find((t) => t.id === selectedTemplate)!.subtitle_style },
                      ]
                    : []
                  ).map((item) => (
                    <Box key={item.label} sx={{ display: "flex", justifyContent: "space-between" }}>
                      <Typography variant="caption" color="text.disabled">{item.label}</Typography>
                      <Typography variant="caption" color="text.secondary" fontWeight={600}>{item.value}</Typography>
                    </Box>
                  ))}
                </Box>
              )}
            </CardContent>
          </Card>

          {/* Asset readiness */}
          <Card sx={{ mb: 2 }}>
            <CardContent sx={{ p: 2.5 }}>
              <Typography variant="subtitle1" fontWeight={700} sx={{ mb: 1.5 }}>
                Asset Readiness
              </Typography>
              {assetsLoading ? (
                <Box sx={{ display: "flex", flexDirection: "column", gap: 0.5 }}>
                  {[1, 2, 3, 4].map((i) => <Skeleton key={i} height={32} />)}
                </Box>
              ) : (
                <>
                  <AssetRow
                    icon={<ImageIcon sx={{ fontSize: 16 }} />}
                    label="Scene Images"
                    ready={(assets?.images_ready ?? 0) > 0}
                    value={assets?.images_ready ? `${assets.images_ready} images` : undefined}
                  />
                  <Divider sx={{ borderColor: "rgba(255,255,255,0.04)", my: 0.5 }} />
                  <AssetRow
                    icon={<AudioIcon sx={{ fontSize: 16 }} />}
                    label="Narration Audio"
                    ready={assets?.narration_ready ?? false}
                  />
                  <Divider sx={{ borderColor: "rgba(255,255,255,0.04)", my: 0.5 }} />
                  <AssetRow
                    icon={<SubIcon sx={{ fontSize: 16 }} />}
                    label="Subtitles (SRT)"
                    ready={assets?.subtitles_ready ?? false}
                  />
                  {assets?.estimated_duration ? (
                    <Box
                      sx={{
                        mt: 1.5,
                        p: 1.25,
                        bgcolor: "rgba(108,99,255,0.07)",
                        borderRadius: 1.5,
                        border: "1px solid rgba(108,99,255,0.15)",
                      }}
                    >
                      <Typography variant="caption" color="text.secondary" display="block">
                        Estimated output duration
                      </Typography>
                      <Typography variant="h6" fontWeight={700} color="primary.light">
                        {formatDuration(assets.estimated_duration)}
                      </Typography>
                    </Box>
                  ) : null}
                </>
              )}
            </CardContent>
          </Card>

          {/* Narrator clips */}
          <NarratorClipsPanel projectId={currentProject.id} />

          {/* Progress card */}
          <ProgressCard
            title="Video Render"
            status={videoReady ? "completed" : videoProgress.status}
            progress={videoReady ? 100 : videoProgress.progress}
            completed={videoReady ? videoProgress.total : videoProgress.completed}
            total={videoProgress.total || assets?.images_ready || 0}
          />
        </Grid>

        {/* Middle: scene progress */}
        <Grid item xs={12} md={4}>
          <Card sx={{ height: "100%" }}>
            <CardContent sx={{ p: 2 }}>
              <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 2 }}>
                <Typography variant="subtitle1" fontWeight={700}>
                  Scene Progress
                </Typography>
                {isRunning && (
                  <Chip
                    label={`${videoProgress.completed}/${videoProgress.total || assets?.images_ready || "?"}`}
                    size="small"
                    color="warning"
                    sx={{ height: 20, fontSize: "0.65rem" }}
                  />
                )}
              </Box>
              <SceneProgressList
                totalScenes={videoProgress.total || assets?.images_ready || 0}
                completedScenes={videoReady ? (videoProgress.total || assets?.images_ready || 0) : videoProgress.completed}
                currentScene={currentSceneNum}
                isRunning={isRunning}
              />
            </CardContent>
          </Card>
        </Grid>

        {/* Right: video preview */}
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent sx={{ p: 2 }}>
              <Typography variant="subtitle1" fontWeight={700} sx={{ mb: 2 }}>
                {videoReady ? "Output Preview" : "Preview"}
              </Typography>
              <VideoPreview
                projectId={currentProject.id}
                videoReady={videoReady}
                manifest={videoStatus?.manifest ?? null}
              />

              {videoReady && (
                <Box sx={{ mt: 2, display: "flex", flexDirection: "column", gap: 1 }}>
                  <Button
                    fullWidth
                    variant="contained"
                    color="success"
                    startIcon={<ExportIcon />}
                    onClick={handleDownload}
                  >
                    Download MP4
                  </Button>
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      </> /* end activeTab === 0 */}
    </Box>
  );
}
