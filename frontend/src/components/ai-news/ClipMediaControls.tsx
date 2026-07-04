import React, { useState, useRef } from "react";
import { Box, Chip, IconButton, Tooltip, Button, Grid, Typography } from "@mui/material";
import {
  PlayArrow as PlayIcon,
  Pause as PauseIcon,
  Download as DownloadIcon,
  DeleteForever as DeleteIcon,
  Replay as RegenerateIcon,
  FileUpload as ReplaceIcon,
} from "@mui/icons-material";
import CircularProgress from "@mui/material/CircularProgress";
import { useQuery } from "@tanstack/react-query";
import { LtxSceneClip } from "../../api/aiNews";

// ── Inline video player ───────────────────────────────────────────────────────

interface VideoPlayerProps {
  src: string;
  aspectRatio: "16/9" | "9/16";
  color: string;
  label: string;
  maxWidth?: number | string;
  /** Called when video finishes loading metadata (for seek scrubber) */
  extraOverlay?: React.ReactNode;
}

export function VideoPlayer({ src, aspectRatio, color, label, maxWidth, extraOverlay }: VideoPlayerProps) {
  const [playing, setPlaying] = useState(false);
  const ref = useRef<HTMLVideoElement>(null);

  const toggle = () => {
    if (!ref.current) return;
    if (playing) ref.current.pause();
    else ref.current.play().catch(() => {});
    setPlaying(!playing);
  };

  return (
    <Box sx={{ maxWidth: maxWidth ?? "100%", width: "100%" }}>
      <Box
        onClick={toggle}
        sx={{
          position: "relative",
          aspectRatio,
          bgcolor: "#080810",
          borderRadius: 2,
          overflow: "hidden",
          border: `1px solid ${color}44`,
          cursor: "pointer",
          "&:hover .play-overlay": { opacity: 1 },
        }}
      >
        <video
          ref={ref}
          src={src}
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
          onEnded={() => setPlaying(false)}
          preload="metadata"
        />
        <Box
          className="play-overlay"
          sx={{
            position: "absolute", inset: 0,
            display: "flex", alignItems: "center", justifyContent: "center",
            bgcolor: "rgba(0,0,0,0.25)",
            opacity: playing ? 0 : 1,
            transition: "opacity 0.2s",
          }}
        >
          {playing
            ? <PauseIcon sx={{ fontSize: 44, color: "#fff", filter: "drop-shadow(0 2px 6px rgba(0,0,0,0.9))" }} />
            : <PlayIcon  sx={{ fontSize: 44, color: "#fff", filter: "drop-shadow(0 2px 6px rgba(0,0,0,0.9))" }} />}
        </Box>
        {/* Aspect-ratio badge */}
        <Chip
          label={label}
          size="small"
          sx={{
            position: "absolute", bottom: 6, right: 6,
            height: 18, fontSize: "0.6rem",
            bgcolor: "rgba(0,0,0,0.75)", color: "#fff", pointerEvents: "none",
          }}
        />
        {extraOverlay}
      </Box>
    </Box>
  );
}

// ── Media action row (play/regenerate/replace/download/delete) ────────────────

interface MediaActionsProps {
  color: string;
  hasMedia: boolean;
  isGenerating: boolean;
  canGenerate: boolean;
  generateLabel: string;
  downloadUrl: string;
  downloadName: string;
  onGenerate: () => void;
  onReplace: (file: File) => void;
  onDelete?: () => void;
  accept?: string;
}

export function MediaActions({
  color, hasMedia, isGenerating, canGenerate,
  generateLabel, downloadUrl, downloadName,
  onGenerate, onReplace, onDelete, accept = "video/mp4",
}: MediaActionsProps) {
  const fileRef = useRef<HTMLInputElement>(null);

  return (
    <Box sx={{ display: "flex", gap: 0.5, alignItems: "center", flexWrap: "wrap", mt: 1 }}>
      {/* Generate / Regenerate */}
      <Tooltip title={hasMedia ? `Re-generate ${generateLabel}` : `Generate ${generateLabel}`}>
        <span>
          <Button
            size="small"
            variant={hasMedia ? "outlined" : "contained"}
            startIcon={isGenerating ? <CircularProgress size={12} color="inherit" /> : <RegenerateIcon />}
            onClick={onGenerate}
            disabled={isGenerating || !canGenerate}
            sx={{
              fontSize: "0.68rem", py: 0.4, px: 1,
              ...(!hasMedia && { bgcolor: color, "&:hover": { bgcolor: color + "cc" } }),
            }}
          >
            {isGenerating ? "…" : hasMedia ? "Re-gen" : "Generate"}
          </Button>
        </span>
      </Tooltip>

      {/* Replace */}
      <Tooltip title={`Replace ${generateLabel} with upload`}>
        <span>
          <Button
            size="small"
            variant="outlined"
            startIcon={<ReplaceIcon />}
            onClick={() => fileRef.current?.click()}
            sx={{ fontSize: "0.68rem", py: 0.4, px: 1 }}
          >
            Replace
          </Button>
        </span>
      </Tooltip>
      <input
        ref={fileRef}
        type="file"
        accept={accept}
        hidden
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) { onReplace(f); e.target.value = ""; }
        }}
      />

      {/* Download */}
      {hasMedia && (
        <Tooltip title={`Download ${generateLabel}`}>
          <IconButton
            size="small"
            sx={{ color: "text.secondary", p: 0.5 }}
            onClick={() => { const a = document.createElement("a"); a.href = downloadUrl; a.download = downloadName; a.click(); }}
          >
            <DownloadIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      )}

      {/* Delete */}
      {hasMedia && onDelete && (
        <Tooltip title={`Delete ${generateLabel}`}>
          <IconButton size="small" color="error" sx={{ p: 0.5, opacity: 0.6, "&:hover": { opacity: 1 } }} onClick={onDelete}>
            <DeleteIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      )}
    </Box>
  );
}

// ── Per-scene LTX clip grid (used by the LTX card on Clips + Shot Clips) ──────

interface LtxSceneGridProps {
  projectId: string;
  label: string;
  aspectRatio: "16/9" | "9/16";
  color: string;
  /** Only fetch/show once the section actually has LTX clips generated. */
  active: boolean;
  fetchScenes: (projectId: string, label: string) => Promise<{ label: string; scenes: LtxSceneClip[] }>;
  sceneUrl: (projectId: string, label: string, sceneId: number) => string;
  queryKeyPrefix: string;
}

export function LtxSceneGrid({
  projectId, label, aspectRatio, color, active, fetchScenes, sceneUrl, queryKeyPrefix,
}: LtxSceneGridProps) {
  const { data, isLoading } = useQuery({
    queryKey: [queryKeyPrefix, projectId, label],
    queryFn: () => fetchScenes(projectId, label),
    enabled: active && !!projectId && !!label,
    staleTime: 10_000,
  });
  const scenes = data?.scenes ?? [];
  const gridCols = aspectRatio === "9/16" ? 3 : 4;

  if (!active) return null;
  if (isLoading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", py: 2 }}>
        <CircularProgress size={20} />
      </Box>
    );
  }
  if (scenes.length === 0) return null;

  return (
    <Box sx={{ mt: 1.5 }}>
      <Typography variant="caption" fontWeight={700} color="text.secondary"
        sx={{ textTransform: "uppercase", fontSize: "0.6rem", letterSpacing: 0.4, display: "block", mb: 0.75 }}>
        Per-Scene Clips ({scenes.length})
      </Typography>
      <Grid container spacing={1}>
        {scenes.map((s) => (
          <Grid item xs={12 / gridCols} key={s.scene_id}>
            <VideoPlayer
              src={sceneUrl(projectId, label, s.scene_id)}
              aspectRatio={aspectRatio}
              color={color}
              label={`#${s.scene_id}`}
            />
          </Grid>
        ))}
      </Grid>
    </Box>
  );
}
