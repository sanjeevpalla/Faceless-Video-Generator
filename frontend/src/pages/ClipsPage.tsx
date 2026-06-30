import React, { useState, useCallback, useRef } from "react";

const _clipVersions: Record<string, number> = {};
import {
  Box,
  Typography,
  Grid,
  Card,
  CardContent,
  Button,
  LinearProgress,
  Chip,
  IconButton,
  Tooltip,
  Alert,
  Skeleton,
  CircularProgress,
} from "@mui/material";
import {
  AutoAwesome as AnimateIcon,
  Refresh as ReanimateIcon,
  PlayCircle as PlayIcon,
  CheckCircle as DoneIcon,
  Error as ErrorIcon,
  HourglassEmpty as PendingIcon,
  DeleteForever as DeleteIcon,
  MovieCreation as ClipsIcon,
  FileUpload as UploadIcon,
  Warning as StaleIcon,
  InfoOutlined as InfoIcon,
} from "@mui/icons-material";
import { useProjectStore } from "../store";
import { useProjectClips, useAnimateScene, WAN2_KEYS } from "../hooks/useWan2";
import { useComfyUIStatus } from "../hooks/useImages";
import { wan2Api, SceneClipInfo } from "../api/wan2";
import { useQueryClient } from "@tanstack/react-query";
import ProgressCard from "../components/common/ProgressCard";
import StatusBadge from "../components/common/StatusBadge";
import DeleteConfirmDialog from "../components/common/DeleteConfirmDialog";
import ComfyUIControl from "../components/common/ComfyUIControl";

// ---------------------------------------------------------------------------
// Scene clip card in the gallery grid
// ---------------------------------------------------------------------------
interface SceneClipCardProps {
  scene: SceneClipInfo;
  projectId: string;
  isSelected: boolean;
  isReanimating: boolean;
  isReplacing: boolean;
  onSelect: () => void;
  onReanimate: () => void;
  onReplace: (file: File) => void;
}

function SceneClipCard({ scene, projectId, isSelected, isReanimating, isReplacing, onSelect, onReanimate, onReplace }: SceneClipCardProps) {
  const [videoError, setVideoError] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const version = _clipVersions[`${projectId}:${scene.scene_id}`];
  const base = wan2Api.getClipUrl(projectId, scene.scene_id);
  const clipUrl = version ? `${base}?v=${version}` : base;

  return (
    <Box
      onClick={onSelect}
      sx={{
        position: "relative",
        cursor: "pointer",
        borderRadius: 2,
        overflow: "hidden",
        border: isSelected ? "2px solid #6C63FF" : "2px solid transparent",
        aspectRatio: "16/9",
        bgcolor: "#080810",
        transition: "border-color 0.15s ease",
        "&:hover .clip-actions": { opacity: 1 },
        "&:hover": { borderColor: isSelected ? "#6C63FF" : "rgba(108,99,255,0.5)" },
      }}
    >
      {/* Video thumbnail / player */}
      {scene.status === "ready" && !videoError ? (
        <video
          src={clipUrl}
          preload="metadata"
          muted
          onError={() => setVideoError(true)}
          style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
        />
      ) : isReanimating ? (
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%" }}>
          <CircularProgress size={28} />
        </Box>
      ) : (
        <Box
          sx={{
            height: "100%",
            background: `linear-gradient(135deg,
              hsl(${(scene.scene_id * 73) % 360}, 28%, 10%),
              hsl(${(scene.scene_id * 73 + 150) % 360}, 22%, 7%))`,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: 0.5,
          }}
        >
          {videoError ? (
            <ErrorIcon sx={{ color: "error.main", fontSize: 20 }} />
          ) : (
            <PendingIcon sx={{ color: "text.disabled", fontSize: 20 }} />
          )}
          <Typography variant="caption" color="text.disabled">
            {videoError ? "Load error" : "Not animated"}
          </Typography>
        </Box>
      )}

      {/* Play icon overlay for ready clips */}
      {scene.status === "ready" && !videoError && (
        <Box
          sx={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            pointerEvents: "none",
          }}
        >
          <PlayIcon sx={{ fontSize: 36, color: "rgba(255,255,255,0.6)", filter: "drop-shadow(0 2px 4px rgba(0,0,0,0.8))" }} />
        </Box>
      )}

      {/* Scene number badge */}
      <Chip
        label={`#${scene.scene_id}`}
        size="small"
        sx={{
          position: "absolute",
          top: 6,
          left: 6,
          height: 20,
          fontSize: "0.62rem",
          bgcolor: "rgba(0,0,0,0.75)",
          color: "white",
          backdropFilter: "blur(4px)",
        }}
      />

      {/* Done badge — replaced by stale badge when image changed after clip */}
      {scene.status === "ready" && !videoError && !scene.image_newer && (
        <DoneIcon
          sx={{
            position: "absolute",
            top: 6,
            right: 6,
            fontSize: 16,
            color: "success.main",
            bgcolor: "rgba(0,0,0,0.6)",
            borderRadius: "50%",
          }}
        />
      )}

      {/* Stale badge — image replaced after clip was generated */}
      {scene.image_newer && (
        <Tooltip title="Image was replaced — re-animate to sync with new image">
          <StaleIcon
            sx={{
              position: "absolute",
              top: 6,
              right: 6,
              fontSize: 18,
              color: "warning.main",
              bgcolor: "rgba(0,0,0,0.7)",
              borderRadius: "50%",
              cursor: "help",
            }}
          />
        </Tooltip>
      )}

      {/* Clip type badge */}
      {scene.status === "ready" && scene.clip_type && (
        <Chip
          label={scene.clip_type === "ltx" ? "LTX" : "Animated"}
          size="small"
          sx={{
            position: "absolute",
            bottom: 6,
            right: 6,
            height: 18,
            fontSize: "0.58rem",
            fontWeight: 700,
            bgcolor: scene.clip_type === "ltx" ? "rgba(108,99,255,0.85)" : "rgba(0,188,212,0.85)",
            color: "white",
            backdropFilter: "blur(4px)",
          }}
        />
      )}

      {/* Hover actions */}
      <Box
        className="clip-actions"
        sx={{
          position: "absolute",
          inset: 0,
          bgcolor: "rgba(0,0,0,0.55)",
          opacity: 0,
          transition: "opacity 0.2s",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: 1,
        }}
      >
        <Tooltip title="Select / preview">
          <IconButton
            size="small"
            onClick={(e) => { e.stopPropagation(); onSelect(); }}
            sx={{ bgcolor: "rgba(255,255,255,0.15)", color: "white" }}
          >
            <PlayIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        <Tooltip title="Reanimate scene">
          <IconButton
            size="small"
            onClick={(e) => { e.stopPropagation(); onReanimate(); }}
            disabled={isReanimating}
            sx={{ bgcolor: "rgba(108,99,255,0.5)", color: "white" }}
          >
            {isReanimating ? <CircularProgress size={14} color="inherit" /> : <ReanimateIcon fontSize="small" />}
          </IconButton>
        </Tooltip>
        <Tooltip title="Replace with your own video">
          <IconButton
            size="small"
            onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click(); }}
            disabled={isReplacing}
            sx={{ bgcolor: "rgba(0,188,212,0.4)", color: "white" }}
          >
            {isReplacing ? <CircularProgress size={14} color="inherit" /> : <UploadIcon fontSize="small" />}
          </IconButton>
        </Tooltip>
        <input
          ref={fileInputRef}
          type="file"
          accept="video/*"
          style={{ display: "none" }}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onReplace(f);
            e.target.value = "";
          }}
        />
      </Box>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Preview panel
// ---------------------------------------------------------------------------
interface PreviewPanelProps {
  scene: SceneClipInfo | null;
  projectId: string;
  isReanimating: boolean;
  onReanimate: () => void;
}

function PreviewPanel({ scene, projectId, isReanimating, onReanimate }: PreviewPanelProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [videoError, setVideoError] = useState(false);

  if (!scene) {
    return (
      <Box
        sx={{
          height: 220,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          bgcolor: "rgba(255,255,255,0.02)",
          borderRadius: 2,
          border: "1px dashed rgba(255,255,255,0.08)",
          gap: 1,
        }}
      >
        <ClipsIcon sx={{ fontSize: 32, color: "text.disabled" }} />
        <Typography variant="caption" color="text.disabled">
          Click a scene to preview
        </Typography>
      </Box>
    );
  }

  const version = _clipVersions[`${projectId}:${scene.scene_id}`];
  const base = wan2Api.getClipUrl(projectId, scene.scene_id);
  const clipUrl = version ? `${base}?v=${version}` : base;

  return (
    <Box>
      {/* Video player */}
      <Box
        sx={{
          width: "100%",
          aspectRatio: "16/9",
          borderRadius: 2,
          overflow: "hidden",
          bgcolor: "#080810",
          mb: 1.5,
        }}
      >
        {scene.status === "ready" && !videoError ? (
          <video
            ref={videoRef}
            key={clipUrl}
            src={clipUrl}
            controls
            onError={() => setVideoError(true)}
            style={{ width: "100%", height: "100%", objectFit: "contain" }}
          />
        ) : (
          <Box
            sx={{
              height: "100%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexDirection: "column",
              gap: 1,
            }}
          >
            {videoError ? (
              <ErrorIcon sx={{ color: "error.main" }} />
            ) : (
              <PendingIcon sx={{ color: "text.disabled" }} />
            )}
            <Typography variant="caption" color="text.disabled">
              {videoError ? "Could not load clip" : "Not animated yet"}
            </Typography>
          </Box>
        )}
      </Box>

      {/* Scene info */}
      <Box sx={{ mb: 1.5 }}>
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 0.5 }}>
          <Typography variant="subtitle2" fontWeight={700}>
            Scene #{scene.scene_id}
          </Typography>
          <StatusBadge status={scene.status} />
        </Box>
        {scene.size > 0 && (
          <Typography variant="caption" color="text.disabled">
            {(scene.size / (1024 * 1024)).toFixed(1)} MB
          </Typography>
        )}
      </Box>

      {scene.image_newer && (
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            gap: 1,
            p: 1,
            mb: 1.5,
            bgcolor: "rgba(255,167,38,0.08)",
            border: "1px solid rgba(255,167,38,0.3)",
            borderRadius: 1.5,
          }}
        >
          <StaleIcon sx={{ fontSize: 16, color: "warning.main", flexShrink: 0 }} />
          <Typography variant="caption" color="warning.main">
            Image was replaced after this clip was generated. Re-animate to sync.
          </Typography>
        </Box>
      )}

      <Button
        fullWidth
        variant="outlined"
        color={scene.image_newer ? "warning" : "primary"}
        startIcon={isReanimating ? <CircularProgress size={14} /> : <ReanimateIcon />}
        onClick={onReanimate}
        disabled={isReanimating}
        size="small"
      >
        {isReanimating ? "Queued…" : "Reanimate Scene"}
      </Button>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function ClipsPage() {
  const currentProject = useProjectStore((s) => s.currentProject);
  const generationProgress = useProjectStore((s) => s.generationProgress);
  const animateScene = useAnimateScene();
  const queryClient = useQueryClient();

  const { data: clipsData, isLoading: clipsLoading } = useProjectClips(currentProject?.id);
  const { data: comfyStatus } = useComfyUIStatus();
  const [selectedScene, setSelectedScene] = useState<SceneClipInfo | null>(null);
  const [reanimatingIds, setReanimatingIds] = useState<Set<number>>(new Set());
  const [replacingIds, setReplacingIds] = useState<Set<number>>(new Set());
  const [, forceUpdate] = useState(0);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [animating, setAnimating] = useState(false);

  const ltxSceneIds = useProjectStore((s) => s.ltxSceneIds);

  const wan2Progress = generationProgress.wan2;
  const total = clipsData?.total ?? 0;
  const animated = clipsData?.animated ?? 0;
  const scenes = clipsData?.scenes ?? [];
  const isRunning = wan2Progress?.status === "running";

  const ltxCount = ltxSceneIds.size;
  // 0 means not yet initialised (user hasn't visited Images page) — treat as all LTX
  const animCount = ltxCount > 0 ? total - ltxCount : 0;

  const handleAnimateAll = async () => {
    if (!currentProject) return;
    setAnimating(true);
    try {
      // ltxSceneIds.size === 0 → not initialised → all scenes use LTX (send undefined)
      // ltxSceneIds.size === total → all selected → send undefined (same all-LTX path)
      // otherwise → send exact list; backend uses Ken Burns for the rest
      const selectedIds =
        ltxCount === 0 || ltxCount === total
          ? undefined
          : Array.from(ltxSceneIds);
      await wan2Api.animateAll(currentProject.id, selectedIds);
    } catch (err) {
      console.error("Failed to trigger animation:", err);
    } finally {
      setAnimating(false);
    }
  };

  const handleDelete = async () => {
    if (!currentProject) return;
    setDeleting(true);
    try {
      await wan2Api.deleteOutputs(currentProject.id);
      queryClient.invalidateQueries({ queryKey: WAN2_KEYS.project(currentProject.id) });
      setSelectedScene(null);
    } catch (err) {
      console.error("Failed to delete clips:", err);
    } finally {
      setDeleting(false);
      setDeleteOpen(false);
    }
  };

  const handleReplace = useCallback(
    async (scene: SceneClipInfo, file: File) => {
      if (!currentProject || replacingIds.has(scene.scene_id)) return;
      setReplacingIds((prev) => new Set(prev).add(scene.scene_id));
      try {
        await wan2Api.replaceClip(currentProject.id, scene.scene_id, file);
        _clipVersions[`${currentProject.id}:${scene.scene_id}`] = Date.now();
        forceUpdate((n) => n + 1);
        queryClient.invalidateQueries({ queryKey: WAN2_KEYS.project(currentProject.id) });
      } catch (err) {
        console.error(`Failed to replace clip ${scene.scene_id}:`, err);
      } finally {
        setReplacingIds((prev) => {
          const next = new Set(prev);
          next.delete(scene.scene_id);
          return next;
        });
      }
    },
    [currentProject, replacingIds, queryClient]
  );

  const handleReanimate = useCallback(
    async (scene: SceneClipInfo) => {
      if (!currentProject || reanimatingIds.has(scene.scene_id)) return;
      setReanimatingIds((prev) => new Set(prev).add(scene.scene_id));
      try {
        await animateScene.mutateAsync({ projectId: currentProject.id, sceneId: scene.scene_id });
      } catch (err) {
        console.error(`Failed to reanimate scene ${scene.scene_id}:`, err);
      } finally {
        setTimeout(() => {
          setReanimatingIds((prev) => {
            const next = new Set(prev);
            next.delete(scene.scene_id);
            return next;
          });
        }, 10000);
      }
    },
    [currentProject, animateScene, reanimatingIds]
  );

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
            Clips
          </Typography>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
            <Typography variant="body2" color="text.secondary">
              Animate scene images into video clips via ComfyUI LTX-Video
            </Typography>
            <ComfyUIControl />
          </Box>
        </Box>
        <Box sx={{ display: "flex", gap: 1.5 }}>
          {animated > 0 && (
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
          {/* ComfyUI not needed only when every scene is Ken Burns (ltxCount===0 AND store was
              explicitly set that way). We conservatively require it in all other cases. */}
          <Tooltip title={!comfyStatus?.online && ltxCount !== 0 ? "Start ComfyUI first (required for LTX-Video scenes)" : ""}>
            <span>
              <Button
                variant="contained"
                startIcon={isRunning || animating ? <CircularProgress size={16} color="inherit" /> : <AnimateIcon />}
                onClick={handleAnimateAll}
                disabled={isRunning || animating || total === 0 || (ltxCount !== 0 && !comfyStatus?.online)}
                size="large"
              >
                {isRunning || animating
                  ? "Generating…"
                  : ltxCount > 0 && ltxCount < total
                    ? `Generate Clips (${ltxCount} LTX + ${animCount} Animated)`
                    : animated > 0
                      ? "Continue / Retry"
                      : "Animate All"}
              </Button>
            </span>
          </Tooltip>
        </Box>
      </Box>

      <DeleteConfirmDialog
        open={deleteOpen}
        title="Delete All Clips"
        description={`Delete all ${animated} animated clips for this project? You will need to re-run LTX-Video animation.`}
        loading={deleting}
        onConfirm={handleDelete}
        onCancel={() => setDeleteOpen(false)}
      />

      {/* Stats row */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        {[
          { label: "Total Scenes", value: total || "—", color: "#6C63FF" },
          { label: "Animated", value: animated, color: "#00E676" },
          { label: "Remaining", value: Math.max(0, total - animated), color: "#9090A8" },
          { label: "Failed", value: (wan2Progress?.status === "failed" ? 1 : 0), color: "#FF5252" },
        ].map((stat) => (
          <Grid item xs={6} sm={3} key={stat.label}>
            <Card>
              <CardContent sx={{ py: 1.5, px: 2, "&:last-child": { pb: 1.5 } }}>
                <Typography variant="h4" fontWeight={800} color={stat.color}>
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

      {/* Progress bar while running */}
      {isRunning && wan2Progress && (
        <Box sx={{ mb: 3 }}>
          <Box sx={{ display: "flex", justifyContent: "space-between", mb: 0.5 }}>
            <Typography variant="caption" color="text.secondary">
              {wan2Progress.completed > 0
                ? `Animating scene ${wan2Progress.completed} of ${wan2Progress.total}…`
                : "Initialising LTX-Video animation…"}
            </Typography>
            <Typography variant="caption" fontWeight={700} color="primary.light">
              {wan2Progress.progress.toFixed(0)}%
            </Typography>
          </Box>
          <LinearProgress variant="determinate" value={wan2Progress.progress} sx={{ height: 8, borderRadius: 2 }} />
        </Box>
      )}

      {/* No images warning */}
      {!clipsLoading && total === 0 && (
        <Alert severity="warning" sx={{ mb: 3, borderRadius: 2 }}>
          No scene images found. Generate images on the Images page first, then come back to animate them.
        </Alert>
      )}

      {/* Read-only info: shows the selection made on the Images page */}
      {total > 0 && (
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            gap: 1,
            mb: 2,
            px: 2,
            py: 0.75,
            borderRadius: 2,
            bgcolor: "rgba(108,99,255,0.05)",
            border: "1px solid rgba(108,99,255,0.14)",
          }}
        >
          <InfoIcon sx={{ fontSize: 14, color: "text.disabled", flexShrink: 0 }} />
          <Typography variant="caption" color="text.secondary">
            {ltxCount === 0 || ltxCount === total
              ? `All ${total} scenes → LTX-Video`
              : <><strong style={{ color: "#6C63FF" }}>{ltxCount}</strong> LTX-Video &nbsp;·&nbsp; <strong style={{ color: "#00BCD4" }}>{animCount}</strong> Ken Burns animated</>}
            &nbsp;—&nbsp;change selection on the <strong>Images</strong> page.
          </Typography>
        </Box>
      )}

      <Grid container spacing={2}>
        {/* Gallery */}
        <Grid item xs={12} md={8}>
          <Card>
            <CardContent sx={{ p: 2 }}>
              <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 2 }}>
                <Typography variant="subtitle1" fontWeight={700}>
                  Clip Gallery
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {animated}/{total} ready · click to preview
                </Typography>
              </Box>

              {clipsLoading ? (
                <Grid container spacing={1.5}>
                  {Array.from({ length: 9 }).map((_, i) => (
                    <Grid item xs={6} sm={4} key={i}>
                      <Skeleton variant="rectangular" sx={{ aspectRatio: "16/9", borderRadius: 2 }} />
                    </Grid>
                  ))}
                </Grid>
              ) : scenes.length === 0 ? (
                <Box
                  sx={{
                    py: 6,
                    textAlign: "center",
                    color: "text.disabled",
                    border: "1px dashed rgba(255,255,255,0.06)",
                    borderRadius: 2,
                  }}
                >
                  <ClipsIcon sx={{ fontSize: 40, mb: 1 }} />
                  <Typography variant="body2">No scenes yet — generate images first, then animate them</Typography>
                </Box>
              ) : (
                <Grid container spacing={1.5}>
                  {scenes.map((scene) => (
                    <Grid item xs={6} sm={4} key={scene.scene_id}>
                      <SceneClipCard
                        scene={scene}
                        projectId={currentProject.id}
                        isSelected={selectedScene?.scene_id === scene.scene_id}
                        isReanimating={reanimatingIds.has(scene.scene_id)}
                        isReplacing={replacingIds.has(scene.scene_id)}
                        onSelect={() => setSelectedScene(scene)}
                        onReanimate={() => handleReanimate(scene)}
                        onReplace={(file) => handleReplace(scene, file)}
                      />
                    </Grid>
                  ))}
                </Grid>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Right panel */}
        <Grid item xs={12} md={4}>
          <Card sx={{ position: "sticky", top: 80, mb: 2 }}>
            <CardContent sx={{ p: 2 }}>
              <Typography variant="subtitle1" fontWeight={700} sx={{ mb: 2 }}>
                {selectedScene ? `Scene #${selectedScene.scene_id} Preview` : "Preview"}
              </Typography>
              <PreviewPanel
                scene={selectedScene}
                projectId={currentProject.id}
                isReanimating={selectedScene ? reanimatingIds.has(selectedScene.scene_id) : false}
                onReanimate={() => selectedScene && handleReanimate(selectedScene)}
              />
            </CardContent>
          </Card>

          <ProgressCard
            title="Clip Animation"
            status={wan2Progress?.status ?? "pending"}
            progress={total > 0 ? (animated / total) * 100 : (wan2Progress?.progress ?? 0)}
            completed={animated}
            total={total}
          />
        </Grid>
      </Grid>
    </Box>
  );
}
