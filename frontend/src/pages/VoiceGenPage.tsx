import React, { useState, useRef, useCallback, useEffect } from "react";
import {
  Box,
  Typography,
  Card,
  CardContent,
  Button,
  Grid,
  LinearProgress,
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction,
  IconButton,
  Tooltip,
  Chip,
  Alert,
  Skeleton,
  CircularProgress,
  Divider,
  Collapse,
} from "@mui/material";
import {
  RecordVoiceOver as VoiceIcon,
  PlayArrow as PlayIcon,
  Pause as PauseIcon,
  Stop as StopIcon,
  Refresh as RegenerateIcon,
  CheckCircle as DoneIcon,
  HourglassEmpty as PendingIcon,
  Error as ErrorIcon,
  Mic as MicIcon,
  MicOff as MicOffIcon,
  VolumeUp as VolumeIcon,
  DeleteForever as DeleteIcon,
  FileUpload as UploadIcon,
  AddCircleOutline as AddPartIcon,
  MergeType as MergeIcon,
  Delete as DeletePartIcon,
  DragIndicator as DragIcon,
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
} from "@mui/icons-material";
import { useProjectStore } from "../store";
import { useTriggerJob } from "../hooks/useJobs";
import { useProjectVoice, usePiperStatus, useRegenerateSceneVoice, VOICE_KEYS } from "../hooks/useVoice";
import { voiceApi, SceneAudioInfo, AudioPart } from "../api/voice";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { aiNewsApi } from "../api/aiNews";
import ProgressCard from "../components/common/ProgressCard";
import StatusBadge from "../components/common/StatusBadge";
import DeleteConfirmDialog from "../components/common/DeleteConfirmDialog";
import AiNewsSectionTabs from "../components/ai-news/AiNewsSectionTabs";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function formatDuration(seconds: number): string {
  if (!seconds || seconds <= 0) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

// ---------------------------------------------------------------------------
// Piper status chip
// ---------------------------------------------------------------------------
function PiperStatusChip() {
  const { data, isLoading } = usePiperStatus();

  if (isLoading) return <Chip label="Checking Piper…" size="small" sx={{ height: 22 }} />;

  const ready = data?.ready ?? false;
  const label = ready
    ? `Piper Ready${data?.version ? ` · ${data.version.slice(0, 20)}` : ""}`
    : data?.executable_found
    ? "Piper: Model missing"
    : "Piper Not Found";

  return (
    <Tooltip
      title={
        ready
          ? `Piper executable: ${data?.executable_path}\nModel: ${data?.model_path}`
          : data?.executable_found
          ? `Executable found but model missing. Set model path in Settings → Piper.`
          : `Piper not found at "${data?.executable}". Install Piper and add to PATH.`
      }
    >
      <Chip
        icon={ready ? <MicIcon sx={{ fontSize: "12px !important" }} /> : <MicOffIcon sx={{ fontSize: "12px !important" }} />}
        label={label}
        size="small"
        sx={{
          height: 24,
          fontSize: "0.7rem",
          bgcolor: ready ? "rgba(0,230,118,0.1)" : "rgba(255,82,82,0.1)",
          color: ready ? "success.main" : "error.main",
          border: `1px solid ${ready ? "rgba(0,230,118,0.3)" : "rgba(255,82,82,0.3)"}`,
        }}
      />
    </Tooltip>
  );
}

// ---------------------------------------------------------------------------
// Inline audio player (one per scene)
// ---------------------------------------------------------------------------
interface AudioPlayerProps {
  src: string;
  isPlaying: boolean;
  onPlay: () => void;
  onPause: () => void;
  duration: number;
}

function AudioPlayer({ src, isPlaying, onPlay, onPause, duration }: AudioPlayerProps) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [currentTime, setCurrentTime] = useState(0);

  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;
    if (isPlaying) {
      el.play().catch(() => {});
    } else {
      el.pause();
    }
  }, [isPlaying]);

  const progress = duration > 0 ? (currentTime / duration) * 100 : 0;

  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 160 }}>
      <audio
        ref={audioRef}
        src={src}
        onTimeUpdate={(e) => setCurrentTime((e.target as HTMLAudioElement).currentTime)}
        onEnded={onPause}
        preload="metadata"
      />
      <IconButton
        size="small"
        onClick={isPlaying ? onPause : onPlay}
        sx={{ color: "primary.main", flexShrink: 0 }}
      >
        {isPlaying ? <PauseIcon fontSize="small" /> : <PlayIcon fontSize="small" />}
      </IconButton>
      <Box sx={{ flex: 1, minWidth: 80 }}>
        <LinearProgress variant="determinate" value={progress} sx={{ height: 3, borderRadius: 2 }} />
        <Typography variant="caption" color="text.disabled" sx={{ fontSize: "0.6rem" }}>
          {formatDuration(currentTime)} / {formatDuration(duration)}
        </Typography>
      </Box>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Scene row in the list
// ---------------------------------------------------------------------------
interface SceneRowProps {
  scene: SceneAudioInfo;
  projectId: string;
  isPlaying: boolean;
  isRegenerating: boolean;
  onPlay: () => void;
  onPause: () => void;
  onRegenerate: () => void;
}

function SceneRow({ scene, projectId, isPlaying, isRegenerating, onPlay, onPause, onRegenerate }: SceneRowProps) {
  const audioUrl = voiceApi.getSceneAudioUrl(projectId, scene.scene_id);

  return (
    <ListItem
      sx={{
        borderRadius: 2,
        mb: 0.75,
        border: `1px solid ${isPlaying ? "rgba(108,99,255,0.35)" : "rgba(255,255,255,0.05)"}`,
        bgcolor: isPlaying ? "rgba(108,99,255,0.07)" : "transparent",
        transition: "all 0.15s ease",
        alignItems: "flex-start",
        gap: 1,
        pr: "100px !important",
      }}
    >
      {/* Status icon */}
      <Box sx={{ pt: 0.75, flexShrink: 0 }}>
        {scene.status === "ready" ? (
          <DoneIcon sx={{ fontSize: 16, color: "success.main" }} />
        ) : isRegenerating ? (
          <CircularProgress size={14} />
        ) : (
          <PendingIcon sx={{ fontSize: 16, color: "text.disabled" }} />
        )}
      </Box>

      {/* Scene info + narration */}
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.25 }}>
          <Typography variant="body2" fontWeight={600} noWrap>
            Scene {scene.scene_id}
          </Typography>
          {scene.scene_title && scene.scene_title !== `Scene ${scene.scene_id}` && (
            <Typography variant="caption" color="text.secondary" noWrap>
              · {scene.scene_title}
            </Typography>
          )}
          {scene.duration > 0 && (
            <Chip
              label={formatDuration(scene.duration)}
              size="small"
              sx={{ height: 16, fontSize: "0.6rem", bgcolor: "rgba(255,255,255,0.05)" }}
            />
          )}
        </Box>

        {scene.narration && (
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{
              display: "-webkit-box",
              WebkitLineClamp: 2,
              WebkitBoxOrient: "vertical",
              overflow: "hidden",
              lineHeight: 1.5,
              mb: 0.5,
            }}
          >
            {scene.narration}
          </Typography>
        )}

        {scene.status === "ready" && (
          <AudioPlayer
            src={audioUrl}
            isPlaying={isPlaying}
            onPlay={onPlay}
            onPause={onPause}
            duration={scene.duration}
          />
        )}
      </Box>

      {/* Actions */}
      <Box sx={{ position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)", display: "flex", gap: 0.5 }}>
        <Tooltip title="Regenerate">
          <span>
            <IconButton
              size="small"
              onClick={onRegenerate}
              disabled={isRegenerating}
              sx={{ color: "text.secondary" }}
            >
              {isRegenerating ? <CircularProgress size={14} /> : <RegenerateIcon fontSize="small" />}
            </IconButton>
          </span>
        </Tooltip>
      </Box>
    </ListItem>
  );
}

// ---------------------------------------------------------------------------
// AI News per-section scene row
// ---------------------------------------------------------------------------
interface AiNewsVoiceSceneRowProps {
  sceneId: number;
  narration: string;
  isGenerated: boolean;
  isPlaying: boolean;
  audioUrl: string;
  onPlay: () => void;
  onPause: () => void;
}

function AiNewsVoiceSceneRow({ sceneId, narration, isGenerated, isPlaying, audioUrl, onPlay, onPause }: AiNewsVoiceSceneRowProps) {
  return (
    <ListItem
      sx={{
        borderRadius: 2,
        mb: 0.75,
        border: `1px solid ${isPlaying ? "rgba(108,99,255,0.35)" : "rgba(255,255,255,0.05)"}`,
        bgcolor: isPlaying ? "rgba(108,99,255,0.07)" : "transparent",
        transition: "all 0.15s ease",
        alignItems: "flex-start",
        gap: 1,
        pr: "48px !important",
      }}
    >
      {/* Status icon */}
      <Box sx={{ pt: 0.75, flexShrink: 0 }}>
        {isGenerated
          ? <DoneIcon sx={{ fontSize: 16, color: "success.main" }} />
          : <PendingIcon sx={{ fontSize: 16, color: "text.disabled" }} />}
      </Box>

      {/* Scene info */}
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.25 }}>
          <Chip
            label={`#${sceneId}`}
            size="small"
            sx={{ height: 18, fontSize: "0.6rem", bgcolor: "rgba(255,255,255,0.05)" }}
          />
        </Box>
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
            lineHeight: 1.5,
          }}
        >
          {narration}
        </Typography>
        {isGenerated && isPlaying && (
          <Box sx={{ mt: 0.5 }}>
            <audio src={audioUrl} autoPlay onEnded={onPause} />
            <LinearProgress sx={{ height: 2, borderRadius: 1, mt: 0.5 }} />
          </Box>
        )}
      </Box>

      {/* Play button */}
      <Box sx={{ position: "absolute", right: 6, top: "50%", transform: "translateY(-50%)" }}>
        {isGenerated && (
          <IconButton size="small" onClick={isPlaying ? onPause : onPlay} sx={{ color: "primary.main" }}>
            {isPlaying ? <PauseIcon fontSize="small" /> : <PlayIcon fontSize="small" />}
          </IconButton>
        )}
      </Box>
    </ListItem>
  );
}

// ---------------------------------------------------------------------------
// Multi-part narration uploader
// ---------------------------------------------------------------------------
function MultiPartUploader({ projectId, onMerged }: { projectId: string; onMerged: () => void }) {
  const [parts, setParts] = useState<AudioPart[]>([]);
  const [totalDuration, setTotalDuration] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [uploadingNames, setUploadingNames] = useState<string[]>([]);
  const [merging, setMerging] = useState(false);
  const [mergeError, setMergeError] = useState<string | null>(null);
  const [playingIdx, setPlayingIdx] = useState<number | null>(null);
  const [expanded, setExpanded] = useState(true);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const dragOver = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await voiceApi.listParts(projectId);
      setParts(res.parts);
      setTotalDuration(res.total_duration);
    } catch {
      // ignore
    }
  }, [projectId]);

  useEffect(() => { refresh(); }, [refresh]);

  const handleFilesSelected = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setUploading(true);
    setUploadingNames(Array.from(files).map((f) => f.name));
    try {
      for (const file of Array.from(files)) {
        await voiceApi.uploadPart(projectId, file);
      }
      await refresh();
    } finally {
      setUploading(false);
      setUploadingNames([]);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleDelete = async (index: number) => {
    if (playingIdx === index) { audioRef.current?.pause(); setPlayingIdx(null); }
    await voiceApi.deletePart(projectId, index);
    await refresh();
  };

  const handlePlay = (index: number) => {
    if (playingIdx === index) {
      audioRef.current?.pause();
      setPlayingIdx(null);
    } else {
      if (audioRef.current) {
        audioRef.current.src = voiceApi.getPartAudioUrl(projectId, index);
        audioRef.current.play();
      }
      setPlayingIdx(index);
    }
  };

  // Drag-and-drop reorder
  const handleDragStart = (e: React.DragEvent, index: number) => {
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", String(index));
  };
  const handleDrop = async (e: React.DragEvent, dropIndex: number) => {
    e.preventDefault();
    const dragIndex = parseInt(e.dataTransfer.getData("text/plain"), 10);
    if (dragIndex === dropIndex) return;
    const order = parts.map((_, i) => i);
    order.splice(dropIndex, 0, order.splice(dragIndex, 1)[0]);
    const res = await voiceApi.reorderParts(projectId, order);
    setParts(res.parts);
    setTotalDuration(res.total_duration);
  };

  const handleMerge = async () => {
    setMerging(true);
    setMergeError(null);
    try {
      await voiceApi.mergeParts(projectId);
      onMerged();
    } catch (err: any) {
      setMergeError(err?.response?.data?.detail || "Merge failed");
    } finally {
      setMerging(false);
    }
  };

  return (
    <Card sx={{ mb: 3 }}>
      <audio ref={audioRef} onEnded={() => setPlayingIdx(null)} />
      <CardContent sx={{ p: 2 }}>
        {/* Header */}
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: expanded ? 2 : 0 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <MergeIcon sx={{ color: "primary.main", fontSize: 20 }} />
            <Typography variant="subtitle1" fontWeight={700}>
              Multi-Part Narration Upload
            </Typography>
            {parts.length > 0 && (
              <Chip
                label={`${parts.length} part${parts.length > 1 ? "s" : ""} · ${formatDuration(totalDuration)}`}
                size="small"
                color="primary"
                variant="outlined"
              />
            )}
          </Box>
          <IconButton size="small" onClick={() => setExpanded((v) => !v)}>
            {expanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
          </IconButton>
        </Box>

        <Collapse in={expanded}>
          {/* Drop zone */}
          <Box
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => { e.preventDefault(); handleFilesSelected(e.dataTransfer.files); }}
            onClick={() => !uploading && fileInputRef.current?.click()}
            sx={{
              border: "2px dashed",
              borderColor: "divider",
              borderRadius: 2,
              py: 2.5,
              px: 2,
              textAlign: "center",
              cursor: uploading ? "wait" : "pointer",
              mb: 2,
              transition: "border-color 0.2s",
              "&:hover": { borderColor: "primary.main" },
            }}
          >
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept="audio/*,.wav,.mp3,.m4a,.ogg,.flac,.aac"
              style={{ display: "none" }}
              onChange={(e) => handleFilesSelected(e.target.files)}
            />
            {uploading ? (
              <Box>
                <CircularProgress size={20} sx={{ mb: 0.5 }} />
                <Typography variant="caption" color="text.secondary" display="block">
                  Uploading {uploadingNames.join(", ")}…
                </Typography>
              </Box>
            ) : (
              <Box>
                <AddPartIcon sx={{ color: "text.disabled", fontSize: 28, mb: 0.5 }} />
                <Typography variant="body2" color="text.secondary">
                  Click or drop audio files here (select multiple)
                </Typography>
                <Typography variant="caption" color="text.disabled">
                  WAV · MP3 · M4A · OGG · FLAC · AAC
                </Typography>
              </Box>
            )}
          </Box>

          {/* Parts list */}
          {parts.length > 0 && (
            <>
              <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: "block" }}>
                Drag rows to reorder · Parts are concatenated in order shown
              </Typography>
              <List dense disablePadding sx={{ mb: 2 }}>
                {parts.map((part, i) => (
                  <ListItem
                    key={part.index}
                    draggable
                    onDragStart={(e) => handleDragStart(e, i)}
                    onDragOver={(e) => { e.preventDefault(); dragOver.current = i; }}
                    onDrop={(e) => handleDrop(e, i)}
                    sx={{
                      border: "1px solid",
                      borderColor: "divider",
                      borderRadius: 1,
                      mb: 0.5,
                      bgcolor: "background.paper",
                      cursor: "grab",
                      "&:active": { cursor: "grabbing" },
                    }}
                  >
                    <DragIcon sx={{ color: "text.disabled", mr: 1, fontSize: 18 }} />
                    <Chip
                      label={i + 1}
                      size="small"
                      sx={{ mr: 1, minWidth: 28, fontWeight: 700 }}
                    />
                    <ListItemText
                      primary={part.original_name}
                      secondary={formatDuration(part.duration)}
                      primaryTypographyProps={{ variant: "body2", noWrap: true }}
                      secondaryTypographyProps={{ variant: "caption" }}
                    />
                    <ListItemSecondaryAction>
                      <Tooltip title={playingIdx === i ? "Pause" : "Play"}>
                        <IconButton size="small" onClick={() => handlePlay(i)}>
                          {playingIdx === i ? <PauseIcon fontSize="small" /> : <PlayIcon fontSize="small" />}
                        </IconButton>
                      </Tooltip>
                      <Tooltip title="Remove">
                        <IconButton size="small" color="error" onClick={() => handleDelete(i)}>
                          <DeletePartIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </ListItemSecondaryAction>
                  </ListItem>
                ))}
              </List>

              {mergeError && (
                <Alert severity="error" sx={{ mb: 1.5, py: 0.5 }} onClose={() => setMergeError(null)}>
                  {mergeError}
                </Alert>
              )}

              <Button
                fullWidth
                variant="contained"
                startIcon={merging ? <CircularProgress size={16} color="inherit" /> : <MergeIcon />}
                onClick={handleMerge}
                disabled={merging || parts.length < 1}
              >
                {merging
                  ? "Merging…"
                  : `Merge ${parts.length} Part${parts.length > 1 ? "s" : ""} → Use as Narration`}
              </Button>
            </>
          )}
        </Collapse>
      </CardContent>
    </Card>
  );
}


// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function VoiceGenPage() {
  const currentProject = useProjectStore((s) => s.currentProject);
  const generationProgress = useProjectStore((s) => s.generationProgress);
  const triggerJob = useTriggerJob();
  const regenerateVoice = useRegenerateSceneVoice();

  const isAiNews = currentProject?.project_type === "ai_news";
  const queryClient = useQueryClient();
  const { data: voiceData, isLoading } = useProjectVoice(currentProject?.id);
  const [playingSceneId, setPlayingSceneId] = useState<number | null>(null);
  const [regeneratingIds, setRegeneratingIds] = useState<Set<number>>(new Set());
  const mergedAudioRef = useRef<HTMLAudioElement>(null);
  const [mergedPlaying, setMergedPlaying] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const uploadInputRef = useRef<HTMLInputElement>(null);

  const [sectionLabel, setSectionLabel] = useState<string | null>(null);
  const [playingSectionAudio, setPlayingSectionAudio] = useState<string | null>(null);
  const sectionsContentQuery = useQuery({
    queryKey: ["ai-news-sections-content", currentProject?.id ?? ""],
    queryFn: () => aiNewsApi.getSectionsContent(currentProject!.id),
    enabled: isAiNews && !!currentProject?.id,
    staleTime: 0,
  });
  const sectionsContent = sectionsContentQuery.data ?? [];
  const selectedSection = sectionLabel ? sectionsContent.find((s) => s.label === sectionLabel) : null;

  const [sectionVoiceGenerating, setSectionVoiceGenerating] = useState<Set<string>>(new Set());
  const sectionVoicePollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [sectionVoiceDeleteOpen, setSectionVoiceDeleteOpen] = useState(false);
  const [sectionVoiceDeleting, setSectionVoiceDeleting] = useState(false);
  const [allSectionVoiceDeleteOpen, setAllSectionVoiceDeleteOpen] = useState(false);
  const [allSectionVoiceDeleting, setAllSectionVoiceDeleting] = useState(false);

  useEffect(() => {
    return () => { if (sectionVoicePollRef.current) clearInterval(sectionVoicePollRef.current); };
  }, []);

  const voiceProgress = generationProgress.voice;
  const isRunning = voiceProgress.status === "running";
  const total = voiceData?.total ?? 0;
  const generated = voiceData?.generated ?? 0;
  const totalDuration = voiceData?.total_duration ?? 0;
  const scenes = voiceData?.scenes ?? [];

  const handleGenerateAll = async () => {
    if (!currentProject) return;
    try {
      await triggerJob.mutateAsync({ projectId: currentProject.id, jobType: "voice" });
    } catch (err) {
      console.error("Voice generation failed:", err);
    }
  };

  const handleUploadSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !currentProject) return;
    e.target.value = "";
    setIsUploading(true);
    try {
      await voiceApi.uploadNarration(currentProject.id, file);
      queryClient.invalidateQueries({ queryKey: VOICE_KEYS.project(currentProject.id) });
    } catch (err) {
      console.error("Upload narration failed:", err);
    } finally {
      setIsUploading(false);
    }
  };

  const handleDelete = async () => {
    if (!currentProject) return;
    setDeleting(true);
    try {
      await voiceApi.deleteOutputs(currentProject.id);
      queryClient.invalidateQueries({ queryKey: VOICE_KEYS.project(currentProject.id) });
      setPlayingSceneId(null);
      setMergedPlaying(false);
    } catch (err) {
      console.error("Failed to delete voice:", err);
    } finally {
      setDeleting(false);
      setDeleteOpen(false);
    }
  };

  const handleRegenerate = useCallback(
    async (scene: SceneAudioInfo) => {
      if (!currentProject || regeneratingIds.has(scene.scene_id)) return;
      setRegeneratingIds((prev) => new Set(prev).add(scene.scene_id));
      try {
        await regenerateVoice.mutateAsync({ projectId: currentProject.id, sceneId: scene.scene_id });
      } catch (err) {
        console.error(`Regenerate voice scene ${scene.scene_id} failed:`, err);
      } finally {
        setTimeout(() => {
          setRegeneratingIds((prev) => {
            const next = new Set(prev);
            next.delete(scene.scene_id);
            return next;
          });
        }, 6000);
      }
    },
    [currentProject, regenerateVoice, regeneratingIds]
  );

  const triggerSectionVoice = useCallback(async (label: string) => {
    if (!currentProject || sectionVoiceGenerating.has(label)) return;
    setSectionVoiceGenerating((prev) => new Set(prev).add(label));
    try {
      await aiNewsApi.generateSectionVoice(currentProject.id, label);
    } catch (err) {
      console.error(`Voice gen failed for ${label}:`, err);
      setSectionVoiceGenerating((prev) => { const n = new Set(prev); n.delete(label); return n; });
      return;
    }
    const poll = setInterval(() => {
      sectionsContentQuery.refetch().then(({ data }) => {
        const sec = data?.find((s) => s.label === label);
        if (sec && (sec.voice_scene_ids.length > 0 || sec.has_narration)) {
          setSectionVoiceGenerating((prev) => { const n = new Set(prev); n.delete(label); return n; });
          clearInterval(poll);
        }
      });
    }, 5000);
    // Safety timeout 10 min
    setTimeout(() => {
      clearInterval(poll);
      setSectionVoiceGenerating((prev) => { const n = new Set(prev); n.delete(label); return n; });
    }, 600_000);
  }, [currentProject, sectionVoiceGenerating, sectionsContentQuery]);

  const generateAllSectionVoice = async () => {
    if (!currentProject || !sectionsContent.length) return;
    let labels: string[];
    try {
      const res = await aiNewsApi.generateMissingSectionsVoice(currentProject.id);
      if (res.status === "nothing_to_do" || !res.labels.length) return;
      labels = res.labels;
    } catch (err) {
      console.error("Failed to start sequential voice generation:", err);
      return;
    }
    // Mark all pending sections as generating
    setSectionVoiceGenerating(new Set(labels));
    // Single poll — removes each label as its audio appears
    if (sectionVoicePollRef.current) clearInterval(sectionVoicePollRef.current);
    sectionVoicePollRef.current = setInterval(() => {
      sectionsContentQuery.refetch().then(({ data }) => {
        if (!data) return;
        setSectionVoiceGenerating((prev) => {
          const next = new Set(prev);
          for (const lbl of [...prev]) {
            const sec = data.find((s) => s.label === lbl);
            if (sec && (sec.voice_scene_ids.length > 0 || sec.has_narration)) next.delete(lbl);
          }
          if (next.size === 0 && sectionVoicePollRef.current) {
            clearInterval(sectionVoicePollRef.current);
            sectionVoicePollRef.current = null;
          }
          return next;
        });
      });
    }, 6000);
  };

  const reGenerateAllSectionVoice = async () => {
    if (!currentProject || !sectionsContent.length || isAiNews === false) return;
    // Delete all existing section voice first
    try {
      await aiNewsApi.deleteAllSectionVoice(currentProject.id);
      setPlayingSectionAudio(null);
    } catch (err) {
      console.error("Re-gen: delete all failed:", err);
      return;
    }
    // Then generate all (backend now sees 0 WAVs → all sections pending)
    let labels: string[];
    try {
      const res = await aiNewsApi.generateMissingSectionsVoice(currentProject.id);
      if (!res.labels || !res.labels.length) return;
      labels = res.labels;
    } catch (err) {
      console.error("Re-gen: generate failed:", err);
      sectionsContentQuery.refetch();
      return;
    }
    setSectionVoiceGenerating(new Set(labels));
    if (sectionVoicePollRef.current) clearInterval(sectionVoicePollRef.current);
    sectionVoicePollRef.current = setInterval(() => {
      sectionsContentQuery.refetch().then(({ data }) => {
        if (!data) return;
        setSectionVoiceGenerating((prev) => {
          const next = new Set(prev);
          for (const lbl of [...prev]) {
            const sec = data.find((s) => s.label === lbl);
            if (sec && (sec.voice_scene_ids.length > 0 || sec.has_narration)) next.delete(lbl);
          }
          if (next.size === 0 && sectionVoicePollRef.current) {
            clearInterval(sectionVoicePollRef.current);
            sectionVoicePollRef.current = null;
          }
          return next;
        });
      });
    }, 6000);
  };

  const handleSectionVoiceDelete = async () => {
    if (!currentProject || !sectionLabel) return;
    setSectionVoiceDeleting(true);
    try {
      await aiNewsApi.deleteSectionVoice(currentProject.id, sectionLabel);
      setPlayingSectionAudio(null);
      sectionsContentQuery.refetch();
    } catch (err) {
      console.error("Failed to delete section voice:", err);
    } finally {
      setSectionVoiceDeleting(false);
      setSectionVoiceDeleteOpen(false);
    }
  };

  const handleAllSectionVoiceDelete = async () => {
    if (!currentProject) return;
    setAllSectionVoiceDeleting(true);
    try {
      await aiNewsApi.deleteAllSectionVoice(currentProject.id);
      setPlayingSectionAudio(null);
      sectionsContentQuery.refetch();
    } catch (err) {
      console.error("Failed to delete all section voice:", err);
    } finally {
      setAllSectionVoiceDeleting(false);
      setAllSectionVoiceDeleteOpen(false);
    }
  };

  const toggleMergedPlay = () => {
    const el = mergedAudioRef.current;
    if (!el) return;
    if (mergedPlaying) { el.pause(); setMergedPlaying(false); }
    else { el.play(); setMergedPlaying(true); }
  };

  if (!currentProject) {
    return (
      <Box sx={{ textAlign: "center", py: 8 }}>
        <Typography color="text.secondary">No project selected.</Typography>
      </Box>
    );
  }

  const mergedAudioUrl = voiceApi.getMergedAudioUrl(currentProject.id);

  // ── AI News layout ──────────────────────────────────────────────────────────
  if (isAiNews) {
    const withVoice  = sectionsContent.filter((s) => s.voice_scene_ids.length > 0 || s.has_narration).length;
    const isAnyVoiceGen = sectionVoiceGenerating.size > 0;
    const allSectionsHaveVoice = sectionsContent.length > 0 && withVoice === sectionsContent.length;
    const canGenerate   = !isAnyVoiceGen && sectionsContent.some(
      (s) => s.scenes_json !== null && s.voice_scene_ids.length === 0 && !s.has_narration,
    );
    const viewLabel    = sectionLabel ?? "";
    const viewVoiceIds = selectedSection?.voice_scene_ids ?? [];

    // Parse narration scenes from selected section's scenes_json
    const sectionScenes: Array<{ scene_id: number; narration: string }> = (() => {
      if (!selectedSection?.scenes_json) return [];
      try {
        const raw = JSON.parse(selectedSection.scenes_json) as Array<Record<string, unknown>>;
        return (Array.isArray(raw) ? raw : [])
          .map((s, i) => ({
            scene_id: (s.scene_id as number | undefined) ?? i + 1,
            narration: ((s.narration as string | undefined) ?? "").trim(),
          }))
          .filter((s) => s.narration.length > 0);
      } catch { return []; }
    })();

    const allSectionsWithVoice = sectionsContent.filter(
      (s) => s.voice_scene_ids.length > 0 || s.has_narration,
    );

    return (
      <Box>
        {/* ── Header ─────────────────────────────────────────────────────── */}
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", mb: 2.5 }}>
          <Box>
            <Typography variant="h4" fontWeight={800} gutterBottom>Voice Generation</Typography>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
              <Chip label="AI NEWS" color="warning" size="small" variant="outlined" sx={{ fontSize: "0.65rem" }} />
              <PiperStatusChip />
              <Typography variant="body2" color="text.secondary">
                {withVoice}/{sectionsContent.length} sections with voice
                {isAnyVoiceGen && ` · generating ${sectionVoiceGenerating.size} section(s)…`}
              </Typography>
            </Box>
          </Box>
          <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
            {withVoice > 0 && (
              <Button variant="outlined" color="error" startIcon={<DeleteIcon />}
                onClick={() => setAllSectionVoiceDeleteOpen(true)}
                disabled={isAnyVoiceGen} size="large">
                Delete All
              </Button>
            )}
            {allSectionsHaveVoice && !isAnyVoiceGen && (
              <Tooltip title="Delete all section voice and regenerate from scratch">
                <Button
                  variant="outlined"
                  startIcon={<RegenerateIcon />}
                  onClick={reGenerateAllSectionVoice}
                  size="large"
                >
                  Re-Generate All
                </Button>
              </Tooltip>
            )}
            <Tooltip title={canGenerate ? "Generate voice for all sections missing audio" : "All sections have voice or no scenes found"}>
              <span>
                <Button
                  variant="contained"
                  startIcon={isAnyVoiceGen ? <CircularProgress size={16} color="inherit" /> : <VoiceIcon />}
                  onClick={generateAllSectionVoice}
                  disabled={!canGenerate}
                  size="large"
                >
                  {isAnyVoiceGen
                    ? `Generating… (${sectionVoiceGenerating.size} left)`
                    : withVoice > 0 ? "Generate Missing" : "Generate All Sections"}
                </Button>
              </span>
            </Tooltip>
          </Box>
        </Box>

        {/* ── Section progress bar ─────────────────────────────────────────── */}
        {sectionVoiceGenerating.has(viewLabel) && (
          <Box sx={{ mb: 2 }}>
            <LinearProgress sx={{ borderRadius: 1, height: 6 }} />
            <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
              Generating voice for {selectedSection?.title ?? viewLabel}…
            </Typography>
          </Box>
        )}

        {/* ── Stats row ────────────────────────────────────────────────────── */}
        {sectionLabel && (
          <Grid container spacing={1.5} sx={{ mb: 2 }}>
            {[
              { label: "Narration Scenes", value: sectionScenes.length, color: "#6C63FF" },
              { label: "Generated", value: viewVoiceIds.length, color: "#00E676" },
              { label: "Remaining", value: Math.max(0, sectionScenes.length - viewVoiceIds.length), color: "#9090A8" },
            ].map(({ label: lbl, value, color }) => (
              <Grid item xs={4} key={lbl}>
                <Card variant="outlined" sx={{ textAlign: "center", py: 1, borderColor: "rgba(255,255,255,0.06)" }}>
                  <Typography variant="h6" fontWeight={800} sx={{ color, lineHeight: 1 }}>{value}</Typography>
                  <Typography variant="caption" color="text.disabled">{lbl}</Typography>
                </Card>
              </Grid>
            ))}
          </Grid>
        )}

        {/* ── Section tabs ─────────────────────────────────────────────────── */}
        <AiNewsSectionTabs
          sections={sectionsContent}
          selected={sectionLabel}
          onSelect={(lbl) => { setSectionLabel(lbl); setPlayingSectionAudio(null); }}
        />

        {/* ── Gallery + Right panel ─────────────────────────────────────────── */}
        <Grid container spacing={2}>
          {/* Left: per-section scene list */}
          <Grid item xs={12} md={8}>
            <Card>
              <CardContent sx={{ p: 2 }}>
                {/* Gallery header */}
                <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1.5 }}>
                  <Typography variant="subtitle1" fontWeight={700}>
                    {sectionLabel
                      ? `${selectedSection?.title ?? sectionLabel} — Narration`
                      : "All Sections — Narration"}
                  </Typography>
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                    {sectionVoiceGenerating.has(viewLabel) && (
                      <Chip icon={<CircularProgress size={10} />} label="Generating…" size="small" color="primary" variant="outlined" sx={{ fontSize: "0.65rem" }} />
                    )}
                    {sectionLabel && (viewVoiceIds.length > 0 || selectedSection?.has_narration) && (
                      <Tooltip title={`Delete voice for ${selectedSection?.title ?? sectionLabel}`}>
                        <IconButton size="small" color="error" onClick={() => setSectionVoiceDeleteOpen(true)}
                          sx={{ opacity: 0.7, "&:hover": { opacity: 1 } }}>
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    )}
                  </Box>
                </Box>

                {sectionLabel !== null ? (
                  // ── Per-section view ──
                  sectionScenes.length === 0 && viewVoiceIds.length === 0 && !selectedSection?.has_narration ? (
                    <Box sx={{ py: 6, textAlign: "center", color: "text.disabled", border: "1px dashed rgba(255,255,255,0.06)", borderRadius: 2 }}>
                      <VoiceIcon sx={{ fontSize: 40, mb: 1 }} />
                      <Typography variant="body2">
                        {selectedSection?.scenes_json === null
                          ? "No scene data — generate section content first"
                          : "No narration text found in scenes"}
                      </Typography>
                    </Box>
                  ) : (
                    <>
                      {/* Merged narration player */}
                      {selectedSection?.has_narration && (
                        <Box sx={{ mb: 1.5, p: 1.25, bgcolor: "rgba(0,230,118,0.06)", border: "1px solid rgba(0,230,118,0.15)", borderRadius: 1.5, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                            <DoneIcon sx={{ fontSize: 14, color: "success.main" }} />
                            <Typography variant="caption" color="success.main" fontWeight={600}>narration.wav (merged)</Typography>
                          </Box>
                          <IconButton size="small" onClick={() => setPlayingSectionAudio(playingSectionAudio === "narration.wav" ? null : "narration.wav")}>
                            {playingSectionAudio === "narration.wav" ? <PauseIcon fontSize="small" /> : <PlayIcon fontSize="small" />}
                          </IconButton>
                          {playingSectionAudio === "narration.wav" && (
                            <audio src={aiNewsApi.getSectionAudioUrl(currentProject.id, viewLabel, "narration.wav")} autoPlay onEnded={() => setPlayingSectionAudio(null)} />
                          )}
                        </Box>
                      )}

                      {/* Per-scene rows */}
                      {sectionScenes.length > 0 ? (
                        <List dense disablePadding>
                          {sectionScenes.map(({ scene_id, narration }) => {
                            const filename = `scene_${String(scene_id).padStart(3, "0")}.wav`;
                            return (
                              <AiNewsVoiceSceneRow
                                key={scene_id}
                                sceneId={scene_id}
                                narration={narration}
                                isGenerated={viewVoiceIds.includes(scene_id)}
                                isPlaying={playingSectionAudio === filename}
                                audioUrl={aiNewsApi.getSectionAudioUrl(currentProject.id, viewLabel, filename)}
                                onPlay={() => setPlayingSectionAudio(filename)}
                                onPause={() => setPlayingSectionAudio(null)}
                              />
                            );
                          })}
                        </List>
                      ) : (
                        // Has audio but no scenes_json to show narration text — show file list
                        <List dense disablePadding>
                          {viewVoiceIds.map((sid) => {
                            const filename = `scene_${String(sid).padStart(3, "0")}.wav`;
                            const isPlaying = playingSectionAudio === filename;
                            return (
                              <ListItem key={sid} sx={{ px: 1, py: 0.75, borderRadius: 1, mb: 0.5, border: "1px solid rgba(255,255,255,0.05)" }}>
                                <ListItemText primary={<Typography variant="caption" color="text.secondary">{filename}</Typography>} />
                                <ListItemSecondaryAction>
                                  <IconButton size="small" onClick={() => setPlayingSectionAudio(isPlaying ? null : filename)}>
                                    {isPlaying ? <PauseIcon fontSize="small" /> : <PlayIcon fontSize="small" />}
                                  </IconButton>
                                  {isPlaying && <audio src={aiNewsApi.getSectionAudioUrl(currentProject.id, viewLabel, filename)} autoPlay onEnded={() => setPlayingSectionAudio(null)} />}
                                </ListItemSecondaryAction>
                              </ListItem>
                            );
                          })}
                        </List>
                      )}

                      {/* Generate button inside gallery when no audio yet */}
                      {sectionScenes.length > 0 && viewVoiceIds.length === 0 && !selectedSection?.has_narration && !sectionVoiceGenerating.has(viewLabel) && (
                        <Box sx={{ mt: 2, textAlign: "center" }}>
                          <Button variant="outlined" startIcon={<VoiceIcon />} onClick={() => triggerSectionVoice(viewLabel)}>
                            Generate Voice for This Section
                          </Button>
                        </Box>
                      )}
                    </>
                  )
                ) : (
                  // ── "All" overview tab ──
                  allSectionsWithVoice.length === 0 ? (
                    <Box sx={{ py: 6, textAlign: "center", color: "text.disabled", border: "1px dashed rgba(255,255,255,0.06)", borderRadius: 2 }}>
                      <VoiceIcon sx={{ fontSize: 40, mb: 1 }} />
                      <Typography variant="body2">No section voice yet — click "Generate All Sections"</Typography>
                    </Box>
                  ) : (
                    <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
                      {sectionsContent.map((sec) => (
                        <Box
                          key={sec.label}
                          onClick={() => setSectionLabel(sec.label)}
                          sx={{ display: "flex", alignItems: "center", gap: 1, p: 1, borderRadius: 1.5, cursor: "pointer", border: "1px solid rgba(255,255,255,0.05)", "&:hover": { bgcolor: "rgba(255,255,255,0.03)" } }}
                        >
                          {sectionVoiceGenerating.has(sec.label)
                            ? <CircularProgress size={14} sx={{ flexShrink: 0 }} />
                            : (sec.voice_scene_ids.length > 0 || sec.has_narration)
                            ? <DoneIcon sx={{ fontSize: 14, color: "success.main", flexShrink: 0 }} />
                            : <PendingIcon sx={{ fontSize: 14, color: "rgba(255,255,255,0.18)", flexShrink: 0 }} />}
                          <Typography variant="body2" sx={{ flex: 1 }} noWrap>{sec.title}</Typography>
                          {sec.voice_scene_ids.length > 0 && (
                            <Chip label={`${sec.voice_scene_ids.length} scenes`} size="small" sx={{ height: 16, fontSize: "0.6rem" }} />
                          )}
                          {sec.has_narration && (
                            <Chip label="merged" size="small" color="success" variant="outlined" sx={{ height: 16, fontSize: "0.6rem" }} />
                          )}
                        </Box>
                      ))}
                    </Box>
                  )
                )}
              </CardContent>
            </Card>
          </Grid>

          {/* Right: generate panel + section progress */}
          <Grid item xs={12} md={4}>
            <Card sx={{ position: "sticky", top: 80, mb: 2 }}>
              <CardContent sx={{ p: 2 }}>
                <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1.5 }}>
                  {sectionLabel ? selectedSection?.title ?? sectionLabel : "Select a Section"}
                </Typography>

                {sectionLabel && sectionScenes.length > 0 ? (
                  <>
                    <Box sx={{ mb: 1.5 }}>
                      <LinearProgress
                        variant="determinate"
                        value={sectionScenes.length > 0 ? (viewVoiceIds.length / sectionScenes.length) * 100 : 0}
                        sx={{ height: 6, borderRadius: 1, mb: 0.5 }}
                      />
                      <Typography variant="caption" color="text.secondary">
                        {viewVoiceIds.length}/{sectionScenes.length} scenes generated
                      </Typography>
                    </Box>
                    <Button
                      fullWidth
                      variant={viewVoiceIds.length === sectionScenes.length ? "outlined" : "contained"}
                      startIcon={sectionVoiceGenerating.has(viewLabel) ? <CircularProgress size={16} color="inherit" /> : <VoiceIcon />}
                      onClick={() => triggerSectionVoice(viewLabel)}
                      disabled={sectionVoiceGenerating.has(viewLabel)}
                      size="small"
                    >
                      {sectionVoiceGenerating.has(viewLabel)
                        ? "Generating…"
                        : viewVoiceIds.length > 0
                        ? "Continue / Retry"
                        : "Generate This Section"}
                    </Button>
                  </>
                ) : (
                  <Typography variant="caption" color="text.disabled">
                    {sectionLabel
                      ? "No narration scenes — generate content first"
                      : "Select a section tab to generate voice"}
                  </Typography>
                )}
              </CardContent>
            </Card>

            {/* Section progress summary */}
            <Card>
              <CardContent sx={{ p: 2, "&:last-child": { pb: 2 } }}>
                <Typography variant="caption" fontWeight={700} color="text.secondary" sx={{ textTransform: "uppercase", fontSize: "0.65rem", letterSpacing: 0.5, display: "block", mb: 1 }}>
                  Section Progress
                </Typography>
                <Box sx={{ display: "flex", flexDirection: "column", gap: 0.75 }}>
                  {sectionsContent.map((sec) => (
                    <Box key={sec.label} sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
                      {sectionVoiceGenerating.has(sec.label)
                        ? <CircularProgress size={12} sx={{ flexShrink: 0 }} />
                        : (sec.voice_scene_ids.length > 0 || sec.has_narration)
                        ? <DoneIcon sx={{ fontSize: 12, color: "success.main", flexShrink: 0 }} />
                        : <PendingIcon sx={{ fontSize: 12, color: "rgba(255,255,255,0.18)", flexShrink: 0 }} />}
                      <Typography variant="caption" sx={{ flex: 1, fontSize: "0.68rem", color: (sec.voice_scene_ids.length > 0 || sec.has_narration) ? "text.primary" : "text.disabled" }} noWrap>
                        {sec.title}
                      </Typography>
                      {sec.voice_scene_ids.length > 0 && (
                        <Typography variant="caption" color="text.disabled" sx={{ fontSize: "0.62rem", flexShrink: 0 }}>
                          {sec.voice_scene_ids.length}
                        </Typography>
                      )}
                    </Box>
                  ))}
                </Box>
              </CardContent>
            </Card>

            {/* Piper info */}
            <Card sx={{ mt: 2 }}>
              <CardContent sx={{ p: 2 }}>
                <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1 }}>
                  <MicIcon sx={{ fontSize: 14, mr: 0.5, verticalAlign: "middle" }} />
                  Piper Setup
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
                  Download Piper from GitHub releases, add to PATH, then download a voice model (.onnx file).
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block">
                  Configure the model path in <strong>Settings → Piper TTS</strong>.
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        </Grid>

        {/* Delete confirm dialogs */}
        <DeleteConfirmDialog
          open={sectionVoiceDeleteOpen}
          title={`Delete Voice — ${selectedSection?.title ?? sectionLabel ?? ""}`}
          description={`Delete all audio files for this section? You will need to regenerate them.`}
          loading={sectionVoiceDeleting}
          onConfirm={handleSectionVoiceDelete}
          onCancel={() => setSectionVoiceDeleteOpen(false)}
        />
        <DeleteConfirmDialog
          open={allSectionVoiceDeleteOpen}
          title="Delete All Section Voice"
          description={`Delete all generated voice audio across all ${withVoice} section${withVoice !== 1 ? "s" : ""}? You will need to regenerate from scratch.`}
          loading={allSectionVoiceDeleting}
          onConfirm={handleAllSectionVoiceDelete}
          onCancel={() => setAllSectionVoiceDeleteOpen(false)}
        />
      </Box>
    );
  }

  // ── Standard (non-AI News) layout ─────────────────────────────────────────
  return (
    <Box>
      {/* Header */}
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 3 }}>
        <Box>
          <Typography variant="h4" fontWeight={800} gutterBottom>
            Voice Generation
          </Typography>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
            <Typography variant="body2" color="text.secondary">
              Generate narration audio using Piper TTS
            </Typography>
            <PiperStatusChip />
          </Box>
        </Box>
        <Box sx={{ display: "flex", gap: 1.5 }}>
          {generated > 0 && (
            <Button
              variant="outlined"
              color="error"
              startIcon={<DeleteIcon />}
              onClick={() => setDeleteOpen(true)}
              disabled={isRunning}
              size="large"
            >
              Delete All
            </Button>
          )}
          <Button
            variant="outlined"
            startIcon={isUploading ? <CircularProgress size={16} color="inherit" /> : <UploadIcon />}
            onClick={() => uploadInputRef.current?.click()}
            disabled={isRunning || isUploading}
            size="large"
          >
            {isUploading ? "Uploading…" : "Upload"}
          </Button>
          <input
            ref={uploadInputRef}
            type="file"
            accept="audio/*,.wav,.mp3,.m4a,.ogg,.flac,.aac"
            style={{ display: "none" }}
            onChange={handleUploadSelect}
          />
          <Button
            variant="contained"
            startIcon={isRunning ? <CircularProgress size={16} color="inherit" /> : <VoiceIcon />}
            onClick={handleGenerateAll}
            disabled={isRunning || triggerJob.isPending}
            size="large"
          >
            {isRunning ? "Generating…" : generated > 0 ? "Continue / Retry" : "Generate Voice"}
          </Button>
        </Box>
      </Box>

      <DeleteConfirmDialog
        open={deleteOpen}
        title="Delete All Voice Audio"
        description={`Delete all ${generated} generated scene audio files and the merged narration? You will need to regenerate them from scratch.`}
        loading={deleting}
        onConfirm={handleDelete}
        onCancel={() => setDeleteOpen(false)}
      />

      {/* Stats row */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        {[
          { label: "Total Scenes", value: total || "—", color: "#6C63FF" },
          { label: "Generated", value: generated, color: "#00E676" },
          { label: "Remaining", value: Math.max(0, total - generated), color: "#9090A8" },
          { label: "Total Duration", value: totalDuration > 0 ? formatDuration(totalDuration) : "—", color: "#00BCD4" },
        ].map((stat) => (
          <Grid item xs={6} sm={3} key={stat.label}>
            <Card>
              <CardContent sx={{ py: 1.5, px: 2, "&:last-child": { pb: 1.5 } }}>
                <Typography variant="h5" fontWeight={800} color={stat.color}>
                  {stat.value}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {stat.label}
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      {/* Running progress */}
      {isRunning && (
        <Box sx={{ mb: 3 }}>
          <Box sx={{ display: "flex", justifyContent: "space-between", mb: 0.5 }}>
            <Typography variant="caption" color="text.secondary">
              {voiceProgress.completed > 0
                ? `Generated scene ${voiceProgress.completed} of ${voiceProgress.total}…`
                : "Initialising voice generation…"}
            </Typography>
            <Typography variant="caption" fontWeight={700} color="primary.light">
              {voiceProgress.progress.toFixed(0)}%
            </Typography>
          </Box>
          <LinearProgress variant="determinate" value={voiceProgress.progress} sx={{ height: 8, borderRadius: 2 }} />
        </Box>
      )}

      {/* No scenes warning */}
      {!isLoading && total === 0 && (
        <Alert severity="warning" sx={{ mb: 3, borderRadius: 2 }}>
          No scenes found. Upload scenes.json on the Project page first.
        </Alert>
      )}

      {/* Uploaded narration notice */}
      {!isLoading && voiceData?.merged && generated === 0 && (
        <Alert severity="info" sx={{ mb: 3, borderRadius: 2 }}>
          Using uploaded narration file — individual scene audio is not available for playback. The video pipeline will use the merged file directly.
        </Alert>
      )}

      {/* Multi-part upload panel */}
      <MultiPartUploader
        projectId={currentProject.id}
        onMerged={() => queryClient.invalidateQueries({ queryKey: VOICE_KEYS.project(currentProject.id) })}
      />

      <Grid container spacing={3}>
        {/* Left: scene list */}
        <Grid item xs={12} md={8}>
          <Card>
            <CardContent sx={{ p: 2 }}>
              <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 2 }}>
                <Typography variant="subtitle1" fontWeight={700}>Scene Audio Files</Typography>
                <Typography variant="caption" color="text.secondary">{generated}/{total} generated</Typography>
              </Box>

              {isLoading ? (
                <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
                  {Array.from({ length: 6 }).map((_, i) => (
                    <Skeleton key={i} variant="rounded" height={72} />
                  ))}
                </Box>
              ) : scenes.length === 0 ? (
                <Box sx={{ py: 5, textAlign: "center", color: "text.disabled" }}>
                  <VoiceIcon sx={{ fontSize: 40, mb: 1 }} />
                  <Typography variant="body2">Upload scenes.json and generate voice</Typography>
                </Box>
              ) : (
                <List dense disablePadding>
                  {scenes.map((scene) => (
                    <SceneRow
                      key={scene.scene_id}
                      scene={scene}
                      projectId={currentProject.id}
                      isPlaying={playingSceneId === scene.scene_id}
                      isRegenerating={regeneratingIds.has(scene.scene_id)}
                      onPlay={() => { setMergedPlaying(false); setPlayingSceneId(scene.scene_id); }}
                      onPause={() => setPlayingSceneId(null)}
                      onRegenerate={() => handleRegenerate(scene)}
                    />
                  ))}
                </List>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Right: merged audio + progress */}
        <Grid item xs={12} md={4}>
          {voiceData?.merged && (
            <Card sx={{ mb: 2 }}>
              <CardContent sx={{ p: 2 }}>
                <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1.5 }}>Merged Narration</Typography>
                <Box sx={{ p: 2, bgcolor: "rgba(0,230,118,0.06)", border: "1px solid rgba(0,230,118,0.15)", borderRadius: 2 }}>
                  <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                    <Typography variant="caption" color="success.main" fontWeight={600}>narration_merged.wav</Typography>
                    <Typography variant="caption" color="text.secondary">{formatDuration(voiceData.merged.duration)}</Typography>
                  </Box>
                  <audio ref={mergedAudioRef} src={mergedAudioUrl} onEnded={() => setMergedPlaying(false)} preload="metadata" />
                  <Button fullWidth variant="outlined" color="success" size="small"
                    startIcon={mergedPlaying ? <PauseIcon /> : <PlayIcon />} onClick={toggleMergedPlay}>
                    {mergedPlaying ? "Pause Narration" : "Play Full Narration"}
                  </Button>
                </Box>
              </CardContent>
            </Card>
          )}

          <ProgressCard
            title="Voice Generation"
            status={voiceProgress.status}
            progress={total > 0 ? (generated / total) * 100 : voiceProgress.progress}
            completed={generated}
            total={total}
          />

          <Card sx={{ mt: 2 }}>
            <CardContent sx={{ p: 2 }}>
              <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1 }}>
                <MicIcon sx={{ fontSize: 14, mr: 0.5, verticalAlign: "middle" }} />
                Piper Setup
              </Typography>
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
                Download Piper from GitHub releases, add to PATH, then download a voice model (.onnx file).
              </Typography>
              <Typography variant="caption" color="text.secondary" display="block">
                Configure the model path in <strong>Settings → Piper TTS</strong>.
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
}
