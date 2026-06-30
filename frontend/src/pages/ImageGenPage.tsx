import React, { useState, useCallback, useRef, useEffect } from "react";

// Module-level version counters for cache-busting after replace/regenerate.
// Standard: key = `${projectId}:${sceneId}`
const _imageVersions: Record<string, number> = {};
// AI News: key = `${projectId}:${label}:${sceneId}`
const _aiNewsSectionVersions: Record<string, number> = {};
import {
  Box,
  Typography,
  Grid,
  Card,
  CardContent,
  Button,
  Checkbox,
  Divider,
  LinearProgress,
  Chip,
  IconButton,
  Tooltip,
  Alert,
  Skeleton,
  CircularProgress,
  Tabs,
  Tab,
} from "@mui/material";
import {
  AutoAwesome as GenerateIcon,
  Refresh as RegenerateIcon,
  ZoomIn as ZoomIcon,
  CheckCircle as DoneIcon,
  Error as ErrorIcon,
  HourglassEmpty as PendingIcon,
  DeleteForever as DeleteIcon,
  FileUpload as UploadIcon,
  SelectAll as SelectAllIcon,
  AutoFixHigh as KenBurnsIcon,
  MovieCreation as ClipsIcon,
  AutoAwesomeMotion as GeminiIcon,
  Movie as VideoTabIcon,
  Smartphone as ShortTabIcon,
  StopCircle as StopIcon,
} from "@mui/icons-material";
import { useProjectStore } from "../store";
import { useTriggerJob } from "../hooks/useJobs";
import { useProjectImages, useComfyUIStatus, useRegenerateScene, IMAGE_KEYS } from "../hooks/useImages";
import { useWebSocket } from "../hooks/useWebSocket";
import { imagesApi, SceneImageInfo } from "../api/images";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { settingsApi } from "../api/settings";
import { aiNewsApi, SectionContent } from "../api/aiNews";
import { servicesApi } from "../api/services";
import ProgressCard from "../components/common/ProgressCard";
import StatusBadge from "../components/common/StatusBadge";
import DeleteConfirmDialog from "../components/common/DeleteConfirmDialog";
import ComfyUIControl from "../components/common/ComfyUIControl";
import AiNewsSectionTabs from "../components/ai-news/AiNewsSectionTabs";

// ---------------------------------------------------------------------------
// Scene image card in the gallery grid
// ---------------------------------------------------------------------------
interface SceneCardProps {
  scene: SceneImageInfo;
  projectId: string;
  isSelected: boolean;
  isLtxSelected: boolean;
  isRegenerating: boolean;
  isReplacing: boolean;
  onSelect: () => void;
  onToggleLtx: () => void;
  onRegenerate: () => void;
  onReplace: (file: File) => void;
}

function SceneCard({ scene, projectId, isSelected, isLtxSelected, isRegenerating, isReplacing, onSelect, onToggleLtx, onRegenerate, onReplace }: SceneCardProps) {
  const [imgError, setImgError] = useState(false);
  const [imgLoaded, setImgLoaded] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const version = _imageVersions[`${projectId}:${scene.scene_id}`];
  const base = imagesApi.getSceneImageUrl(projectId, scene.scene_id);
  const imageUrl = version ? `${base}?v=${version}` : base;

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
        "&:hover .scene-actions": { opacity: 1 },
        "&:hover": { borderColor: isSelected ? "#6C63FF" : "rgba(108,99,255,0.5)" },
      }}
    >
      {/* Image */}
      {scene.status === "ready" && !imgError ? (
        <>
          {!imgLoaded && (
            <Skeleton variant="rectangular" sx={{ position: "absolute", inset: 0, transform: "none" }} />
          )}
          <img
            src={imageUrl}
            alt={`Scene ${scene.scene_id}`}
            onLoad={() => setImgLoaded(true)}
            onError={() => setImgError(true)}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
              display: imgLoaded ? "block" : "none",
            }}
          />
        </>
      ) : scene.status === "generating" || isRegenerating ? (
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%" }}>
          <CircularProgress size={28} />
        </Box>
      ) : (
        <Box
          sx={{
            height: "100%",
            background: `linear-gradient(135deg,
              hsl(${(scene.scene_id * 47) % 360}, 30%, 12%),
              hsl(${(scene.scene_id * 47 + 120) % 360}, 25%, 8%))`,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: 0.5,
          }}
        >
          {imgError ? (
            <ErrorIcon sx={{ color: "error.main", fontSize: 20 }} />
          ) : (
            <PendingIcon sx={{ color: "text.disabled", fontSize: 20 }} />
          )}
          <Typography variant="caption" color="text.disabled">
            {imgError ? "Load error" : "Not generated"}
          </Typography>
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

      {/* Status badge */}
      {scene.status === "ready" && !imgError && (
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

      {/* Clip mode badge — shows intended clip generation method */}
      <Chip
        label={isLtxSelected ? "LTX" : "Animated"}
        size="small"
        sx={{
          position: "absolute",
          bottom: 6,
          right: 6,
          height: 18,
          fontSize: "0.58rem",
          fontWeight: 700,
          bgcolor: isLtxSelected ? "rgba(108,99,255,0.85)" : "rgba(0,188,212,0.85)",
          color: "white",
          backdropFilter: "blur(4px)",
          pointerEvents: "none",
        }}
      />

      {/* LTX selection checkbox */}
      <Tooltip title={isLtxSelected ? "LTX-Video selected — click to switch to Ken Burns animated clip" : "Click to use LTX-Video AI animation for this scene"}>
        <Checkbox
          checked={isLtxSelected}
          size="small"
          onClick={(e) => { e.stopPropagation(); onToggleLtx(); }}
          onChange={() => {}}
          sx={{
            position: "absolute",
            bottom: 2,
            left: 2,
            p: 0.5,
            color: "rgba(255,255,255,0.55)",
            "&.Mui-checked": { color: "#6C63FF" },
          }}
        />
      </Tooltip>

      {/* Hover actions */}
      <Box
        className="scene-actions"
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
            <ZoomIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        <Tooltip title="Regenerate scene">
          <IconButton
            size="small"
            onClick={(e) => { e.stopPropagation(); onRegenerate(); }}
            disabled={isRegenerating}
            sx={{ bgcolor: "rgba(108,99,255,0.5)", color: "white" }}
          >
            {isRegenerating ? <CircularProgress size={14} color="inherit" /> : <RegenerateIcon fontSize="small" />}
          </IconButton>
        </Tooltip>
        <Tooltip title="Replace with your own image">
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
          accept="image/*"
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
// Preview panel (right side)
// ---------------------------------------------------------------------------
interface PreviewPanelProps {
  scene: SceneImageInfo | null;
  projectId: string;
  isRegenerating: boolean;
  onRegenerate: () => void;
}

function PreviewPanel({ scene, projectId, isRegenerating, onRegenerate }: PreviewPanelProps) {
  const [imgError, setImgError] = useState(false);

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
        <ZoomIcon sx={{ fontSize: 32, color: "text.disabled" }} />
        <Typography variant="caption" color="text.disabled">
          Click a scene to preview
        </Typography>
      </Box>
    );
  }

  const version = _imageVersions[`${projectId}:${scene.scene_id}`];
  const base = imagesApi.getSceneImageUrl(projectId, scene.scene_id);
  const imageUrl = version ? `${base}?v=${version}` : base;

  return (
    <Box>
      {/* Image preview */}
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
        {scene.status === "ready" && !imgError ? (
          <img
            src={imageUrl}
            alt={`Scene ${scene.scene_id}`}
            onError={() => setImgError(true)}
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
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
            {imgError ? (
              <ErrorIcon sx={{ color: "error.main" }} />
            ) : (
              <PendingIcon sx={{ color: "text.disabled" }} />
            )}
            <Typography variant="caption" color="text.disabled">
              {imgError ? "Could not load image" : "Not generated yet"}
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
        {scene.scene_title && (
          <Typography variant="caption" color="text.secondary" display="block">
            {scene.scene_title}
          </Typography>
        )}
        {scene.size > 0 && (
          <Typography variant="caption" color="text.disabled">
            {(scene.size / 1024).toFixed(0)} KB
          </Typography>
        )}
      </Box>

      {/* Prompt */}
      {scene.prompt && (
        <Box
          sx={{
            p: 1.25,
            bgcolor: "rgba(108,99,255,0.06)",
            border: "1px solid rgba(108,99,255,0.15)",
            borderRadius: 1.5,
            mb: 1.5,
          }}
        >
          <Typography variant="caption" color="primary.light" fontWeight={600} display="block" sx={{ mb: 0.25 }}>
            FLUX PROMPT
          </Typography>
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{
              display: "-webkit-box",
              WebkitLineClamp: 4,
              WebkitBoxOrient: "vertical",
              overflow: "hidden",
              lineHeight: 1.5,
            }}
          >
            {scene.prompt}
          </Typography>
        </Box>
      )}

      <Button
        fullWidth
        variant="outlined"
        startIcon={isRegenerating ? <CircularProgress size={14} /> : <RegenerateIcon />}
        onClick={onRegenerate}
        disabled={isRegenerating}
        size="small"
      >
        {isRegenerating ? "Queued…" : "Regenerate Scene"}
      </Button>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Portrait (9:16) image card — simulates blur-background short layout
// ---------------------------------------------------------------------------
interface PortraitCardProps {
  imageUrl: string;
  sceneId: number;
  isSelected: boolean;
  onClick: () => void;
}

function PortraitCard({ imageUrl, sceneId, isSelected, onClick }: PortraitCardProps) {
  return (
    <Box
      onClick={onClick}
      sx={{
        position: "relative",
        aspectRatio: "9/16",
        borderRadius: 1.5,
        overflow: "hidden",
        cursor: "pointer",
        bgcolor: "#080810",
        border: isSelected ? "2px solid" : "2px solid transparent",
        borderColor: isSelected ? "primary.main" : "transparent",
        "&:hover": { opacity: 0.88 },
      }}
    >
      {/* Blurred background fills the entire 9:16 container */}
      <Box
        sx={{
          position: "absolute", inset: 0,
          backgroundImage: `url(${imageUrl})`,
          backgroundSize: "cover",
          backgroundPosition: "center",
          filter: "blur(18px) saturate(0.75)",
          transform: "scale(1.2)",
        }}
      />
      {/* Sharp image centered */}
      <Box
        sx={{
          position: "absolute", inset: 0,
          display: "flex", alignItems: "center", justifyContent: "center",
        }}
      >
        <Box
          component="img"
          src={imageUrl}
          alt={`Scene ${sceneId}`}
          sx={{ width: "100%", height: "auto" }}
        />
      </Box>
      {/* Scene badge */}
      <Chip
        label={`#${sceneId}`}
        size="small"
        sx={{
          position: "absolute", top: 4, left: 4,
          height: 16, fontSize: "0.6rem",
          bgcolor: "rgba(0,0,0,0.7)", color: "white",
        }}
      />
      {isSelected && (
        <DoneIcon sx={{ position: "absolute", top: 4, right: 4, fontSize: 15, color: "success.main" }} />
      )}
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Helpers for AI News section images
// ---------------------------------------------------------------------------
function parseSectionPrompt(imagePrompts: string | null, sceneId: number): string {
  if (!imagePrompts) return "";
  const blocks = imagePrompts.split(/\n\s*\n/);
  for (const block of blocks) {
    const idMatch = block.match(/SCENE[_\s]0*(\d+)/i);
    if (idMatch && parseInt(idMatch[1], 10) === sceneId) {
      const promptMatch = block.match(/PROMPT:\s*([\s\S]+)/i);
      if (promptMatch) return promptMatch[1].trim();
    }
  }
  // Fallback: nth line for plain-prompt format
  const lines = imagePrompts.split("\n").filter((l) => l.trim().length > 0);
  return lines[sceneId - 1] ?? "";
}

// ---------------------------------------------------------------------------
// AI News scene card — mirrors SceneCard but for section images (no LTX)
// ---------------------------------------------------------------------------
interface AiNewsSceneCardProps {
  projectId: string;
  label: string;
  sceneId: number;
  isGenerated: boolean;
  isSelected: boolean;
  isRegenerating: boolean;
  isReplacing: boolean;
  onSelect: () => void;
  onRegenerate: () => void;
  onReplace: (file: File) => void;
}

function AiNewsSceneCard({
  projectId, label, sceneId, isGenerated, isSelected,
  isRegenerating, isReplacing, onSelect, onRegenerate, onReplace,
}: AiNewsSceneCardProps) {
  const [imgError, setImgError] = useState(false);
  const [imgLoaded, setImgLoaded] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const vKey = `${projectId}:${label}:${sceneId}`;
  const version = _aiNewsSectionVersions[vKey];
  const base = aiNewsApi.getSectionImageUrl(projectId, label, sceneId);
  const imageUrl = version ? `${base}?v=${version}` : base;

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
        "&:hover .scene-actions": { opacity: 1 },
        "&:hover": { borderColor: isSelected ? "#6C63FF" : "rgba(108,99,255,0.5)" },
      }}
    >
      {isGenerated && !imgError ? (
        <>
          {!imgLoaded && (
            <Skeleton variant="rectangular" sx={{ position: "absolute", inset: 0, transform: "none" }} />
          )}
          <img
            src={imageUrl}
            alt={`Scene ${sceneId}`}
            onLoad={() => setImgLoaded(true)}
            onError={() => setImgError(true)}
            style={{ width: "100%", height: "100%", objectFit: "cover", display: imgLoaded ? "block" : "none" }}
          />
        </>
      ) : isRegenerating ? (
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%" }}>
          <CircularProgress size={28} />
        </Box>
      ) : (
        <Box
          sx={{
            height: "100%",
            background: `linear-gradient(135deg,
              hsl(${(sceneId * 47) % 360}, 30%, 12%),
              hsl(${(sceneId * 47 + 120) % 360}, 25%, 8%))`,
            display: "flex", flexDirection: "column",
            alignItems: "center", justifyContent: "center", gap: 0.5,
          }}
        >
          {imgError
            ? <ErrorIcon sx={{ color: "error.main", fontSize: 20 }} />
            : <PendingIcon sx={{ color: "text.disabled", fontSize: 20 }} />}
          <Typography variant="caption" color="text.disabled">
            {imgError ? "Load error" : "Not generated"}
          </Typography>
        </Box>
      )}

      {/* Scene number badge */}
      <Chip
        label={`#${sceneId}`}
        size="small"
        sx={{
          position: "absolute", top: 6, left: 6, height: 20,
          fontSize: "0.62rem", bgcolor: "rgba(0,0,0,0.75)", color: "white",
          backdropFilter: "blur(4px)",
        }}
      />

      {/* Done checkmark */}
      {isGenerated && !imgError && (
        <DoneIcon
          sx={{
            position: "absolute", top: 6, right: 6, fontSize: 16,
            color: "success.main", bgcolor: "rgba(0,0,0,0.6)", borderRadius: "50%",
          }}
        />
      )}

      {/* Hover actions */}
      <Box
        className="scene-actions"
        sx={{
          position: "absolute", inset: 0, bgcolor: "rgba(0,0,0,0.55)",
          opacity: 0, transition: "opacity 0.2s",
          display: "flex", alignItems: "center", justifyContent: "center", gap: 1,
        }}
      >
        <Tooltip title="Select / preview">
          <IconButton size="small" onClick={(e) => { e.stopPropagation(); onSelect(); }}
            sx={{ bgcolor: "rgba(255,255,255,0.15)", color: "white" }}>
            <ZoomIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        <Tooltip title="Regenerate this scene">
          <IconButton size="small" onClick={(e) => { e.stopPropagation(); onRegenerate(); }}
            disabled={isRegenerating}
            sx={{ bgcolor: "rgba(108,99,255,0.5)", color: "white" }}>
            {isRegenerating ? <CircularProgress size={14} color="inherit" /> : <RegenerateIcon fontSize="small" />}
          </IconButton>
        </Tooltip>
        <Tooltip title="Replace with your own image">
          <IconButton size="small" onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click(); }}
            disabled={isReplacing}
            sx={{ bgcolor: "rgba(0,188,212,0.4)", color: "white" }}>
            {isReplacing ? <CircularProgress size={14} color="inherit" /> : <UploadIcon fontSize="small" />}
          </IconButton>
        </Tooltip>
        <input
          ref={fileInputRef} type="file" accept="image/*" style={{ display: "none" }}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) onReplace(f); e.target.value = ""; }}
        />
      </Box>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// AI News preview panel — mirrors PreviewPanel with section prompt display
// ---------------------------------------------------------------------------
interface AiNewsPreviewPanelProps {
  projectId: string;
  label: string;
  sceneId: number | null;
  isGenerated: boolean;
  prompt: string;
  sectionTitle: string;
  isRegenerating: boolean;
  onRegenerate: () => void;
}

function AiNewsPreviewPanel({
  projectId, label, sceneId, isGenerated, prompt,
  sectionTitle, isRegenerating, onRegenerate,
}: AiNewsPreviewPanelProps) {
  const [imgError, setImgError] = useState(false);

  if (!sceneId) {
    return (
      <Box sx={{
        height: 220, display: "flex", flexDirection: "column",
        alignItems: "center", justifyContent: "center",
        bgcolor: "rgba(255,255,255,0.02)", borderRadius: 2,
        border: "1px dashed rgba(255,255,255,0.08)", gap: 1,
      }}>
        <ZoomIcon sx={{ fontSize: 32, color: "text.disabled" }} />
        <Typography variant="caption" color="text.disabled">Click a scene to preview</Typography>
      </Box>
    );
  }

  const vKey = `${projectId}:${label}:${sceneId}`;
  const version = _aiNewsSectionVersions[vKey];
  const base = aiNewsApi.getSectionImageUrl(projectId, label, sceneId);
  const imageUrl = version ? `${base}?v=${version}` : base;

  return (
    <Box>
      {/* Image */}
      <Box sx={{ width: "100%", aspectRatio: "16/9", borderRadius: 2, overflow: "hidden", bgcolor: "#080810", mb: 1.5 }}>
        {isGenerated && !imgError ? (
          <img src={imageUrl} alt={`Scene ${sceneId}`} onError={() => setImgError(true)}
            style={{ width: "100%", height: "100%", objectFit: "cover" }} />
        ) : (
          <Box sx={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 1 }}>
            {imgError
              ? <ErrorIcon sx={{ color: "error.main" }} />
              : <PendingIcon sx={{ color: "text.disabled" }} />}
            <Typography variant="caption" color="text.disabled">
              {imgError ? "Could not load image" : "Not generated yet"}
            </Typography>
          </Box>
        )}
      </Box>

      {/* Scene info */}
      <Box sx={{ mb: 1.5 }}>
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 0.5 }}>
          <Typography variant="subtitle2" fontWeight={700}>Scene #{sceneId}</Typography>
          <Chip
            label={isGenerated ? "Ready" : "Pending"}
            size="small"
            color={isGenerated ? "success" : "default"}
            variant="outlined"
            sx={{ height: 18, fontSize: "0.62rem" }}
          />
        </Box>
        <Typography variant="caption" color="text.secondary" display="block">{sectionTitle}</Typography>
      </Box>

      {/* Prompt */}
      {prompt && (
        <Box sx={{
          p: 1.25, bgcolor: "rgba(108,99,255,0.06)",
          border: "1px solid rgba(108,99,255,0.15)", borderRadius: 1.5, mb: 1.5,
        }}>
          <Typography variant="caption" color="primary.light" fontWeight={600} display="block" sx={{ mb: 0.25 }}>
            FLUX PROMPT
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{
            display: "-webkit-box", WebkitLineClamp: 4,
            WebkitBoxOrient: "vertical", overflow: "hidden", lineHeight: 1.5,
          }}>
            {prompt}
          </Typography>
        </Box>
      )}

      <Button
        fullWidth variant="outlined" size="small"
        startIcon={isRegenerating ? <CircularProgress size={14} /> : <RegenerateIcon />}
        onClick={onRegenerate}
        disabled={isRegenerating}
      >
        {isRegenerating ? "Queued…" : "Regenerate Scene"}
      </Button>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function ImageGenPage() {
  const currentProject = useProjectStore((s) => s.currentProject);
  const generationProgress = useProjectStore((s) => s.generationProgress);
  const ltxSceneIds = useProjectStore((s) => s.ltxSceneIds);
  const setLtxSceneIds = useProjectStore((s) => s.setLtxSceneIds);
  const toggleLtxSceneId = useProjectStore((s) => s.toggleLtxSceneId);
  const triggerJob = useTriggerJob();
  const regenerateScene = useRegenerateScene();
  const queryClient = useQueryClient();
  const { data: comfyStatus } = useComfyUIStatus();
  const { data: appSettings } = useQuery({ queryKey: ["settings"], queryFn: settingsApi.get, staleTime: 60_000 });
  const imageBackend = appSettings?.gemini?.image_backend ?? "flux";

  const isAiNews = currentProject?.project_type === "ai_news";
  const { data: imagesData, isLoading: imagesLoading } = useProjectImages(currentProject?.id);
  const [selectedScene, setSelectedScene] = useState<SceneImageInfo | null>(null);
  const [regeneratingIds, setRegeneratingIds] = useState<Set<number>>(new Set());
  const [replacingIds, setReplacingIds] = useState<Set<number>>(new Set());
  const [, forceUpdate] = useState(0);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const ltxInitRef = useRef(false);

  const [sectionLabel, setSectionLabel] = useState<string | null>(null);
  const [selectedSectionImageId, setSelectedSectionImageId] = useState<number | null>(null);
  const [mainTab, setMainTab] = useState<"video" | "short">("video");
  const [sectionGenerating, setSectionGenerating] = useState<Set<string>>(new Set());
  const sectionPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const sectionQueueRef = useRef<SectionContent[]>([]);
  // Per-scene regenerating/replacing: key = `${label}:${sceneId}`
  const [sectionRegenIds, setSectionRegenIds] = useState<Set<string>>(new Set());
  const [sectionReplaceIds, setSectionReplaceIds] = useState<Set<string>>(new Set());
  const [, aiNewsForceUpdate] = useState(0);
  const [sectionDeleteOpen, setSectionDeleteOpen] = useState(false);
  const [sectionDeleting, setSectionDeleting] = useState(false);
  const [allSectionDeleteOpen, setAllSectionDeleteOpen] = useState(false);
  const [allSectionDeleting, setAllSectionDeleting] = useState(false);

  const sectionsContentQuery = useQuery({
    queryKey: ["ai-news-sections-content", currentProject?.id ?? ""],
    queryFn: () => aiNewsApi.getSectionsContent(currentProject!.id),
    enabled: isAiNews && !!currentProject?.id,
    staleTime: 0,
  });
  const sectionsContent = sectionsContentQuery.data ?? [];
  const selectedSection = sectionLabel ? sectionsContent.find((s) => s.label === sectionLabel) : null;

  // Cleanup polling on unmount
  useEffect(() => {
    return () => { if (sectionPollRef.current) clearInterval(sectionPollRef.current); };
  }, []);

  // WS: when a section_images job completes or fails, clear it from sectionGenerating
  // and fire the next queued section (sequential queue to avoid ComfyUI overload).
  // Use .refetch directly — it's stable across renders in React Query, unlike the whole query object.
  // Putting the whole sectionsContentQuery in deps causes handleMessage → connect to change on every
  // refetch, which triggers a WS reconnect loop and sets wsConnected=false ("Offline" badge).
  const sectionsRefetch = sectionsContentQuery.refetch;

  // Ref-based queue runner so it's always fresh and can self-recurse without stale closures.
  // Fires the next section in sectionQueueRef; on API error (e.g. 400 = no prompts yet),
  // removes it from sectionGenerating and immediately tries the one after it.
  const fireNextSectionRef = useRef<() => void>(() => {});
  fireNextSectionRef.current = () => {
    if (!currentProject || sectionQueueRef.current.length === 0) return;
    const next = sectionQueueRef.current.shift()!;
    aiNewsApi.generateSectionImages(currentProject.id, next.label).catch((err: unknown) => {
      console.error(`Section ${next.label} images failed to start:`, err);
      setSectionGenerating((prev) => { const n = new Set(prev); n.delete(next.label); return n; });
      fireNextSectionRef.current(); // skip to the section after the failed one
    });
  };

  const handleSectionImagesWs = useCallback(
    (event: string, data: Record<string, unknown>) => {
      if (String(data.job_type ?? "") !== "section_images") return;
      const label = String(data.section ?? "");
      if ((event === "job_completed" || event === "job_failed") && label) {
        setSectionGenerating((prev) => { const n = new Set(prev); n.delete(label); return n; });
        sectionsRefetch();
        fireNextSectionRef.current();
      }
    },
    [sectionsRefetch],
  );
  useWebSocket({ projectId: currentProject?.id, onMessage: handleSectionImagesWs });

  // Fallback refetch while generating — keeps image counts live if WS events are missed
  useEffect(() => {
    if (!sectionGenerating.size) return;
    const id = setInterval(() => sectionsRefetch(), 10_000);
    return () => clearInterval(id);
  }, [sectionGenerating.size, sectionsRefetch]);

  const imgProgress = generationProgress.images;
  const total = imagesData?.total ?? 0;
  const generated = imagesData?.generated ?? 0;
  const scenes = imagesData?.scenes ?? [];
  const isRunning = imgProgress.status === "running";
  const comfyOnline = comfyStatus?.online ?? false;

  // Reset init flag when project changes so we re-initialise on next load
  useEffect(() => {
    ltxInitRef.current = false;
  }, [currentProject?.id]);

  // On first load, default all scenes to LTX-Video
  useEffect(() => {
    if (!ltxInitRef.current && scenes.length > 0 && ltxSceneIds.size === 0) {
      setLtxSceneIds(new Set(scenes.map((s) => s.scene_id)));
      ltxInitRef.current = true;
    } else if (scenes.length > 0) {
      ltxInitRef.current = true;
    }
  }, [scenes, ltxSceneIds.size, setLtxSceneIds]);

  const ltxCount = ltxSceneIds.size;
  const animCount = total - ltxCount;

  const handleGenerateAll = async () => {
    if (!currentProject) return;
    try {
      await triggerJob.mutateAsync({ projectId: currentProject.id, jobType: "image" });
    } catch (err) {
      console.error("Failed to trigger image generation:", err);
    }
  };

  const [geminiGenerating, setGeminiGenerating] = useState(false);
  const [geminiError, setGeminiError] = useState<string | null>(null);

  const handleGenerateGemini = async () => {
    if (!currentProject) return;
    setGeminiGenerating(true);
    setGeminiError(null);
    try {
      await imagesApi.generateWithGemini(currentProject.id);
    } catch (err: unknown) {
      setGeminiError(err instanceof Error ? err.message : "Failed to start Gemini image generation");
    } finally {
      setGeminiGenerating(false);
    }
  };

  // Helper: expected scene count from scenes_json (hoisted for use in generateAllSections)
  const expectedSceneCount = (s: SectionContent): number => {
    if (!s.scenes_json) return 0;
    try { return (JSON.parse(s.scenes_json) as unknown[]).length; } catch { return 0; }
  };

  const generateAllSections = async () => {
    if (!currentProject || !sectionsContent.length) return;
    const pending = sectionsContent.filter(
      (s) => s.image_prompts !== null && s.image_scene_ids.length < expectedSceneCount(s),
    );
    if (!pending.length) return;

    setSectionGenerating(new Set(pending.map((s) => s.label)));

    // Process one section at a time: fire the first, queue the rest.
    // When each section finishes (via WS job_completed/job_failed), the next is dequeued.
    // This keeps ComfyUI focused on one section's scenes and avoids any queue-overflow timeouts.
    sectionQueueRef.current = pending.slice(1);
    try {
      await aiNewsApi.generateSectionImages(currentProject.id, pending[0].label);
    } catch (err: unknown) {
      // First section failed to start (e.g. 400 — no image_prompts.txt yet).
      // Remove it from generating and let the ref-based runner try the next one.
      console.error(`First section ${pending[0].label} failed to start:`, err);
      setSectionGenerating((prev) => { const n = new Set(prev); n.delete(pending[0].label); return n; });
      fireNextSectionRef.current();
    }
  };

  const handleSectionSceneRegenerate = useCallback(
    async (label: string, sceneId: number) => {
      if (!currentProject) return;
      const key = `${label}:${sceneId}`;
      if (sectionRegenIds.has(key)) return;
      setSectionRegenIds((prev) => new Set(prev).add(key));
      try {
        await aiNewsApi.regenerateSectionImage(currentProject.id, label, sceneId);
        // Poll until the scene appears in image_scene_ids
        const poll = setInterval(() => {
          sectionsContentQuery.refetch().then(({ data }) => {
            const sec = data?.find((s) => s.label === label);
            if (sec?.image_scene_ids.includes(sceneId)) {
              _aiNewsSectionVersions[`${currentProject.id}:${label}:${sceneId}`] = Date.now();
              setSectionRegenIds((prev) => { const n = new Set(prev); n.delete(key); return n; });
              aiNewsForceUpdate((n) => n + 1);
              clearInterval(poll);
            }
          });
        }, 4000);
        // Timeout after 3 min
        setTimeout(() => {
          clearInterval(poll);
          setSectionRegenIds((prev) => { const n = new Set(prev); n.delete(key); return n; });
        }, 180_000);
      } catch (err) {
        console.error(`Failed to regenerate scene ${sceneId} in ${label}:`, err);
        setSectionRegenIds((prev) => { const n = new Set(prev); n.delete(key); return n; });
      }
    },
    [currentProject, sectionRegenIds, sectionsContentQuery]
  );

  const handleSectionSceneReplace = useCallback(
    async (label: string, sceneId: number, file: File) => {
      if (!currentProject) return;
      const key = `${label}:${sceneId}`;
      if (sectionReplaceIds.has(key)) return;
      setSectionReplaceIds((prev) => new Set(prev).add(key));
      try {
        await aiNewsApi.uploadSectionImage(currentProject.id, label, sceneId, file);
        _aiNewsSectionVersions[`${currentProject.id}:${label}:${sceneId}`] = Date.now();
        aiNewsForceUpdate((n) => n + 1);
        sectionsContentQuery.refetch();
      } catch (err) {
        console.error(`Failed to replace scene ${sceneId} in ${label}:`, err);
      } finally {
        setSectionReplaceIds((prev) => { const n = new Set(prev); n.delete(key); return n; });
      }
    },
    [currentProject, sectionReplaceIds, sectionsContentQuery]
  );

  const handleAllSectionDelete = async () => {
    if (!currentProject) return;
    setAllSectionDeleting(true);
    try {
      await aiNewsApi.deleteAllSectionImages(currentProject.id);
      setSelectedSectionImageId(null);
      sectionsContentQuery.refetch();
    } catch (err) {
      console.error("Failed to delete all section images:", err);
    } finally {
      setAllSectionDeleting(false);
      setAllSectionDeleteOpen(false);
    }
  };

  const handleSectionDelete = async () => {
    if (!currentProject || !sectionLabel) return;
    setSectionDeleting(true);
    try {
      await aiNewsApi.deleteSectionImages(currentProject.id, sectionLabel);
      setSelectedSectionImageId(null);
      sectionsContentQuery.refetch();
    } catch (err) {
      console.error(`Failed to delete images for section ${sectionLabel}:`, err);
    } finally {
      setSectionDeleting(false);
      setSectionDeleteOpen(false);
    }
  };

  const handleDelete = async () => {
    if (!currentProject) return;
    setDeleting(true);
    try {
      await imagesApi.deleteOutputs(currentProject.id);
      queryClient.invalidateQueries({ queryKey: IMAGE_KEYS.project(currentProject.id) });
      setSelectedScene(null);
    } catch (err) {
      console.error("Failed to delete images:", err);
    } finally {
      setDeleting(false);
      setDeleteOpen(false);
    }
  };

  const handleReplace = useCallback(
    async (scene: SceneImageInfo, file: File) => {
      if (!currentProject || replacingIds.has(scene.scene_id)) return;
      setReplacingIds((prev) => new Set(prev).add(scene.scene_id));
      try {
        await imagesApi.replaceSceneImage(currentProject.id, scene.scene_id, file);
        _imageVersions[`${currentProject.id}:${scene.scene_id}`] = Date.now();
        forceUpdate((n) => n + 1);
        queryClient.invalidateQueries({ queryKey: IMAGE_KEYS.project(currentProject.id) });
      } catch (err) {
        console.error(`Failed to replace scene ${scene.scene_id}:`, err);
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

  const handleRegenerate = useCallback(
    async (scene: SceneImageInfo) => {
      if (!currentProject || regeneratingIds.has(scene.scene_id)) return;
      setRegeneratingIds((prev) => new Set(prev).add(scene.scene_id));
      try {
        await regenerateScene.mutateAsync({
          projectId: currentProject.id,
          sceneId: scene.scene_id,
        });
      } catch (err) {
        console.error(`Failed to regenerate scene ${scene.scene_id}:`, err);
      } finally {
        // Keep regenerating state until the image polling confirms it's ready
        setTimeout(() => {
          setRegeneratingIds((prev) => {
            const next = new Set(prev);
            next.delete(scene.scene_id);
            return next;
          });
        }, 8000);
      }
    },
    [currentProject, regenerateScene, regeneratingIds]
  );

  if (!currentProject) {
    return (
      <Box sx={{ textAlign: "center", py: 8 }}>
        <Typography color="text.secondary">No project selected.</Typography>
      </Box>
    );
  }

  // ── AI News layout ────────────────────────────────────────────────────────
  if (isAiNews) {
    // A section is "complete" only when it has ALL expected images
    const isSectionComplete = (s: SectionContent) =>
      s.image_prompts !== null &&
      expectedSceneCount(s) > 0 &&
      s.image_scene_ids.length >= expectedSceneCount(s);

    const withImages   = sectionsContent.filter((s) => s.image_scene_ids.length > 0).length;
    const fullyDone    = sectionsContent.filter(isSectionComplete).length;
    const withPrompts  = sectionsContent.filter((s) => s.image_prompts !== null).length;
    const isAnyGen     = sectionGenerating.size > 0;
    // canGenerate: any section that has prompts but is missing at least one image
    const canGenerate  = !isAnyGen && withPrompts > 0 &&
      sectionsContent.some((s) => s.image_prompts !== null && s.image_scene_ids.length < expectedSceneCount(s));

    // Images for the current view
    const viewIds   = selectedSection?.image_scene_ids ?? [];
    const viewLabel = sectionLabel ?? "";

    // Compute total expected scenes in the selected section (parsed from scenes_json)
    const totalSectionScenes = (() => {
      if (!selectedSection?.scenes_json) return 0;
      try { return (JSON.parse(selectedSection.scenes_json) as unknown[]).length; }
      catch { return 0; }
    })();

    const selectedScenePrompt = parseSectionPrompt(
      selectedSection?.image_prompts ?? null,
      selectedSectionImageId ?? 0,
    );

    // "All" tab: flatten all section images into one list with section grouping
    const allSectionsWithImages = sectionsContent.filter((s) => s.image_scene_ids.length > 0);

    return (
      <Box>
        {/* ── Header ─────────────────────────────────────────────────────── */}
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", mb: 2.5 }}>
          <Box>
            <Typography variant="h4" fontWeight={800} gutterBottom>Image Generation</Typography>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
              <Chip label="AI NEWS" color="warning" size="small" variant="outlined" sx={{ fontSize: "0.65rem" }} />
              <Typography variant="body2" color="text.secondary">
                {withImages}/{sectionsContent.length} sections with images
                {isAnyGen && ` · generating ${sectionGenerating.size} section(s)…`}
              </Typography>
            </Box>
          </Box>
          <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
            {imageBackend === "flux" && <ComfyUIControl />}

            {/* Stop Generation — cancels frontend tracking AND clears ComfyUI queue */}
            {isAnyGen && (
              <Tooltip title="Stop generating and clear ComfyUI queue">
                <Button
                  variant="outlined"
                  color="error"
                  size="large"
                  startIcon={<StopIcon />}
                  onClick={async () => {
                    // Clear frontend state immediately
                    setSectionGenerating(new Set());
                    if (sectionPollRef.current) {
                      clearInterval(sectionPollRef.current);
                      sectionPollRef.current = null;
                    }
                    // Clear ComfyUI queue
                    try { await servicesApi.clearComfyUIQueue(); } catch { /* ignore */ }
                  }}
                >
                  Stop
                </Button>
              </Tooltip>
            )}

            {withImages > 0 && !isAnyGen && (
              <Button
                variant="outlined"
                color="error"
                startIcon={<DeleteIcon />}
                onClick={() => setAllSectionDeleteOpen(true)}
                size="large"
              >
                Delete All
              </Button>
            )}
            <Tooltip title={!comfyOnline && imageBackend === "flux" ? "Start ComfyUI first" : canGenerate ? "Generate images for all sections that are missing images" : "All sections already have images"}>
              <span>
                <Button
                  variant="contained"
                  startIcon={<GenerateIcon />}
                  onClick={generateAllSections}
                  disabled={isAnyGen || !canGenerate || (imageBackend === "flux" && !comfyOnline)}
                  size="large"
                >
                  {isAnyGen
                    ? `Generating… (${sectionGenerating.size} left)`
                    : fullyDone < sectionsContent.length ? "Generate Missing Scenes" : "Generate All Sections"}
                </Button>
              </span>
            </Tooltip>
          </Box>
        </Box>

        {/* ── Main tabs: Video / Short ────────────────────────────────────── */}
        <Tabs
          value={mainTab}
          onChange={(_, v: "video" | "short") => { setMainTab(v); setSelectedSectionImageId(null); }}
          sx={{
            mb: 0,
            borderBottom: 1,
            borderColor: "divider",
            "& .MuiTab-root": { minHeight: 40, fontSize: "0.8rem", py: 1 },
          }}
        >
          <Tab
            value="video"
            label="Video"
            icon={<VideoTabIcon sx={{ fontSize: 16 }} />}
            iconPosition="start"
          />
          <Tab
            value="short"
            label="Short (9:16)"
            icon={<ShortTabIcon sx={{ fontSize: 16 }} />}
            iconPosition="start"
          />
        </Tabs>

        {/* ── Section sub-tabs ────────────────────────────────────────────── */}
        <AiNewsSectionTabs
          sections={sectionsContent}
          selected={sectionLabel}
          onSelect={(lbl) => { setSectionLabel(lbl); setSelectedSectionImageId(null); }}
        />

        {/* ── Stats row ───────────────────────────────────────────────────── */}
        {sectionLabel && (
          <Grid container spacing={1.5} sx={{ mb: 2 }}>
            {[
              { label: "Total Scenes", value: totalSectionScenes || viewIds.length, color: "text.primary" },
              { label: "Generated", value: viewIds.length, color: "success.main" },
              { label: "Missing", value: Math.max(0, (totalSectionScenes || viewIds.length) - viewIds.length), color: "warning.main" },
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

        {/* ── Section progress bar ─────────────────────────────────────────── */}
        {sectionGenerating.has(viewLabel) && (
          <Box sx={{ mb: 2 }}>
            <LinearProgress sx={{ borderRadius: 1, height: 6 }} />
            <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
              Generating images for {selectedSection?.title ?? viewLabel}…
            </Typography>
          </Box>
        )}

        {/* ── Gallery + Preview ───────────────────────────────────────────── */}
        <Grid container spacing={2}>
          {/* Left: image gallery */}
          <Grid item xs={12} md={8}>
            <Card>
              <CardContent sx={{ p: 2 }}>
                {/* Gallery header */}
                <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1.5 }}>
                  <Typography variant="subtitle1" fontWeight={700}>
                    {sectionLabel
                      ? `${selectedSection?.title ?? sectionLabel} — ${mainTab === "video" ? "Video Images" : "Short Preview (9:16)"}`
                      : mainTab === "video" ? "All Sections — Video Images" : "All Sections — Short Preview (9:16)"}
                  </Typography>
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                    {sectionGenerating.has(viewLabel) && (
                      <Chip icon={<CircularProgress size={10} />} label="Generating…" size="small" color="primary" variant="outlined" sx={{ fontSize: "0.65rem" }} />
                    )}
                    {sectionLabel && viewIds.length > 0 && (
                      <Typography variant="caption" color="text.secondary">
                        {viewIds.length} {mainTab === "video" ? "images" : "previews"}
                      </Typography>
                    )}
                    {sectionLabel && viewIds.length > 0 && (
                      <Tooltip title={`Delete all images for ${selectedSection?.title ?? sectionLabel}`}>
                        <IconButton
                          size="small"
                          color="error"
                          onClick={() => setSectionDeleteOpen(true)}
                          sx={{ opacity: 0.7, "&:hover": { opacity: 1 } }}
                        >
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    )}
                  </Box>
                </Box>

                {/* Per-section view */}
                {sectionLabel !== null ? (
                  viewIds.length === 0 ? (
                    <Box sx={{ py: 6, textAlign: "center", color: "text.disabled", border: "1px dashed rgba(255,255,255,0.06)", borderRadius: 2 }}>
                      {sectionGenerating.has(viewLabel)
                        ? <CircularProgress sx={{ mb: 1 }} />
                        : <PendingIcon sx={{ fontSize: 40, mb: 1 }} />}
                      <Typography variant="body2" sx={{ mb: 1.5 }}>
                        {sectionGenerating.has(viewLabel)
                          ? "Generating images for this section…"
                          : selectedSection?.image_prompts
                          ? 'No images yet — click "Generate This Section" to start'
                          : "No image prompts for this section yet — generate section content first"}
                      </Typography>
                      {!sectionGenerating.has(viewLabel) && selectedSection?.image_prompts && (
                        <Button
                          variant="outlined" size="small" startIcon={<GenerateIcon />}
                          onClick={async () => {
                            setSectionGenerating((prev) => new Set(prev).add(viewLabel));
                            try { await aiNewsApi.generateSectionImages(currentProject.id, viewLabel); }
                            catch { setSectionGenerating((prev) => { const n = new Set(prev); n.delete(viewLabel); return n; }); }
                            // WS handler (handleSectionImagesWs) clears sectionGenerating on completion
                          }}
                        >
                          Generate This Section
                        </Button>
                      )}
                    </Box>
                  ) : mainTab === "video" ? (
                    /* Video: 16:9 grid with AiNewsSceneCard */
                    <Grid container spacing={1.5}>
                      {viewIds.map((sceneId) => {
                        const rKey = `${viewLabel}:${sceneId}`;
                        return (
                          <Grid item xs={6} sm={4} key={sceneId}>
                            <AiNewsSceneCard
                              projectId={currentProject.id}
                              label={viewLabel}
                              sceneId={sceneId}
                              isGenerated={true}
                              isSelected={selectedSectionImageId === sceneId}
                              isRegenerating={sectionRegenIds.has(rKey)}
                              isReplacing={sectionReplaceIds.has(rKey)}
                              onSelect={() => setSelectedSectionImageId(selectedSectionImageId === sceneId ? null : sceneId)}
                              onRegenerate={() => handleSectionSceneRegenerate(viewLabel, sceneId)}
                              onReplace={(f) => handleSectionSceneReplace(viewLabel, sceneId, f)}
                            />
                          </Grid>
                        );
                      })}
                    </Grid>
                  ) : (
                    /* Short: 9:16 portrait grid */
                    <Grid container spacing={1.5}>
                      {viewIds.map((sceneId) => {
                        const url = aiNewsApi.getSectionImageUrl(currentProject.id, viewLabel, sceneId);
                        return (
                          <Grid item xs={6} sm={4} md={3} key={sceneId}>
                            <PortraitCard
                              imageUrl={url}
                              sceneId={sceneId}
                              isSelected={selectedSectionImageId === sceneId}
                              onClick={() => setSelectedSectionImageId(selectedSectionImageId === sceneId ? null : sceneId)}
                            />
                          </Grid>
                        );
                      })}
                    </Grid>
                  )
                ) : (
                  /* "All" tab: sections overview */
                  allSectionsWithImages.length === 0 ? (
                    <Box sx={{ py: 6, textAlign: "center", color: "text.disabled", border: "1px dashed rgba(255,255,255,0.06)", borderRadius: 2 }}>
                      <PendingIcon sx={{ fontSize: 40, mb: 1 }} />
                      <Typography variant="body2">No section images yet — click "Generate All Sections" to start</Typography>
                    </Box>
                  ) : (
                    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
                      {allSectionsWithImages.map((sec) => (
                        <Box key={sec.label}>
                          <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
                            <Typography variant="caption" fontWeight={700} color="text.secondary" sx={{ textTransform: "uppercase", fontSize: "0.68rem", letterSpacing: 0.5 }}>
                              {sec.title}
                            </Typography>
                            {sectionGenerating.has(sec.label) && <CircularProgress size={10} />}
                            <Chip label={`${sec.image_scene_ids.length} images`} size="small" sx={{ height: 16, fontSize: "0.6rem" }} />
                          </Box>
                          <Grid container spacing={1}>
                            {sec.image_scene_ids.slice(0, mainTab === "video" ? 4 : 6).map((sceneId) => {
                              const url = aiNewsApi.getSectionImageUrl(currentProject.id, sec.label, sceneId);
                              return (
                                <Grid item xs={mainTab === "video" ? 3 : 2} key={`${sec.label}-${sceneId}`}>
                                  {mainTab === "video" ? (
                                    <Box
                                      onClick={() => { setSectionLabel(sec.label); setSelectedSectionImageId(sceneId); }}
                                      sx={{ aspectRatio: "16/9", borderRadius: 1, overflow: "hidden", cursor: "pointer", "&:hover": { opacity: 0.8 } }}
                                    >
                                      <Box component="img" src={url} sx={{ width: "100%", height: "100%", objectFit: "cover" }} />
                                    </Box>
                                  ) : (
                                    <PortraitCard
                                      imageUrl={url} sceneId={sceneId} isSelected={false}
                                      onClick={() => { setSectionLabel(sec.label); setSelectedSectionImageId(sceneId); }}
                                    />
                                  )}
                                </Grid>
                              );
                            })}
                            {sec.image_scene_ids.length > (mainTab === "video" ? 4 : 6) && (
                              <Grid item xs={mainTab === "video" ? 3 : 2}>
                                <Box
                                  onClick={() => setSectionLabel(sec.label)}
                                  sx={{
                                    aspectRatio: mainTab === "video" ? "16/9" : "9/16",
                                    borderRadius: 1, bgcolor: "rgba(255,255,255,0.04)",
                                    border: "1px dashed rgba(255,255,255,0.12)",
                                    display: "flex", alignItems: "center", justifyContent: "center",
                                    cursor: "pointer", "&:hover": { bgcolor: "rgba(255,255,255,0.07)" },
                                  }}
                                >
                                  <Typography variant="caption" color="text.disabled">
                                    +{sec.image_scene_ids.length - (mainTab === "video" ? 4 : 6)} more
                                  </Typography>
                                </Box>
                              </Grid>
                            )}
                          </Grid>
                        </Box>
                      ))}
                    </Box>
                  )
                )}
              </CardContent>
            </Card>
          </Grid>

          {/* Right: preview + section progress */}
          <Grid item xs={12} md={4}>
            {/* Upgraded preview panel */}
            <Card sx={{ position: "sticky", top: 80, mb: 2 }}>
              <CardContent sx={{ p: 2 }}>
                <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1.5 }}>
                  {selectedSectionImageId ? `Scene #${selectedSectionImageId}` : "Preview"}
                  {mainTab === "short" && selectedSectionImageId && (
                    <Chip label="9:16 Short" size="small" icon={<ShortTabIcon sx={{ fontSize: "11px !important" }} />}
                      sx={{ ml: 1, height: 18, fontSize: "0.6rem", bgcolor: "rgba(108,99,255,0.2)", color: "primary.light" }} />
                  )}
                </Typography>

                {mainTab === "video" && sectionLabel ? (
                  <AiNewsPreviewPanel
                    projectId={currentProject.id}
                    label={sectionLabel}
                    sceneId={selectedSectionImageId}
                    isGenerated={selectedSectionImageId !== null && viewIds.includes(selectedSectionImageId)}
                    prompt={selectedScenePrompt}
                    sectionTitle={selectedSection?.title ?? sectionLabel}
                    isRegenerating={selectedSectionImageId !== null && sectionRegenIds.has(`${sectionLabel}:${selectedSectionImageId}`)}
                    onRegenerate={() => {
                      if (selectedSectionImageId && sectionLabel)
                        handleSectionSceneRegenerate(sectionLabel, selectedSectionImageId);
                    }}
                  />
                ) : selectedSectionImageId && sectionLabel && mainTab === "short" ? (
                  /* Portrait preview */
                  <Box sx={{ maxWidth: 220, mx: "auto" }}>
                    <PortraitCard
                      imageUrl={aiNewsApi.getSectionImageUrl(currentProject.id, sectionLabel, selectedSectionImageId)}
                      sceneId={selectedSectionImageId}
                      isSelected={false}
                      onClick={() => {}}
                    />
                  </Box>
                ) : (
                  <Box sx={{
                    height: mainTab === "video" ? 160 : 260,
                    display: "flex", alignItems: "center", justifyContent: "center",
                    bgcolor: "rgba(255,255,255,0.02)", borderRadius: 2,
                    border: "1px dashed rgba(255,255,255,0.08)",
                  }}>
                    <Typography variant="caption" color="text.disabled">
                      {sectionLabel ? "Click an image to preview" : "Select a section tab first"}
                    </Typography>
                  </Box>
                )}

                {/* Section generate shortcut when no images exist yet */}
                {sectionLabel && !sectionGenerating.has(sectionLabel) && viewIds.length === 0 && selectedSection?.image_prompts && mainTab === "video" && (
                  <Button
                    fullWidth variant="outlined" size="small"
                    startIcon={<GenerateIcon />}
                    onClick={async () => {
                      setSectionGenerating((prev) => new Set(prev).add(sectionLabel));
                      try { await aiNewsApi.generateSectionImages(currentProject.id, sectionLabel); }
                      catch { setSectionGenerating((prev) => { const n = new Set(prev); n.delete(sectionLabel); return n; }); }
                      // WS handler (handleSectionImagesWs) clears sectionGenerating on completion
                    }}
                    sx={{ mt: 1.5, fontSize: "0.72rem" }}
                  >
                    Generate This Section
                  </Button>
                )}
              </CardContent>
            </Card>

            {/* Per-section progress summary */}
            <Card>
              <CardContent sx={{ p: 2, "&:last-child": { pb: 2 } }}>
                <Typography variant="caption" fontWeight={700} color="text.secondary" sx={{ textTransform: "uppercase", fontSize: "0.65rem", letterSpacing: 0.5, display: "block", mb: 1 }}>
                  Section Progress
                </Typography>
                <Box sx={{ display: "flex", flexDirection: "column", gap: 0.75 }}>
                  {sectionsContent.map((sec) => (
                    <Box key={sec.label} sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
                      {sectionGenerating.has(sec.label) ? (
                        <CircularProgress size={12} sx={{ flexShrink: 0 }} />
                      ) : sec.image_scene_ids.length > 0 ? (
                        <DoneIcon sx={{ fontSize: 12, color: "success.main", flexShrink: 0 }} />
                      ) : (
                        <PendingIcon sx={{ fontSize: 12, color: "rgba(255,255,255,0.18)", flexShrink: 0 }} />
                      )}
                      <Typography variant="caption" sx={{ flex: 1, fontSize: "0.68rem", color: sec.image_scene_ids.length > 0 ? "text.primary" : "text.disabled" }} noWrap>
                        {sec.title}
                      </Typography>
                      {sec.image_scene_ids.length > 0 && (
                        <Typography variant="caption" color="text.disabled" sx={{ fontSize: "0.62rem", flexShrink: 0 }}>
                          {sec.image_scene_ids.length}
                        </Typography>
                      )}
                    </Box>
                  ))}
                </Box>
              </CardContent>
            </Card>
          </Grid>
        </Grid>

        <DeleteConfirmDialog
          open={sectionDeleteOpen}
          title={`Delete Images — ${selectedSection?.title ?? sectionLabel ?? ""}`}
          description={`Delete all ${viewIds.length} generated image${viewIds.length !== 1 ? "s" : ""} for this section? You will need to regenerate them.`}
          loading={sectionDeleting}
          onConfirm={handleSectionDelete}
          onCancel={() => setSectionDeleteOpen(false)}
        />

        <DeleteConfirmDialog
          open={allSectionDeleteOpen}
          title="Delete All Section Images"
          description={`Delete all generated images across all ${withImages} section${withImages !== 1 ? "s" : ""}? You will need to regenerate them from scratch.`}
          loading={allSectionDeleting}
          onConfirm={handleAllSectionDelete}
          onCancel={() => setAllSectionDeleteOpen(false)}
        />
      </Box>
    );
  }

  // ── Standard (non-AI News) layout ────────────────────────────────────────
  return (
    <Box>
      {/* Header */}
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 3 }}>
        <Box>
          <Typography variant="h4" fontWeight={800} gutterBottom>
            Image Generation
          </Typography>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
            <Typography variant="body2" color="text.secondary">
              {imageBackend === "gemini"
                ? "Generate scene images via Gemini (cloud, 15 RPM free)"
                : "Generate scene images via ComfyUI FLUX Dev"}
            </Typography>
            {imageBackend === "flux" && <ComfyUIControl />}
          </Box>
        </Box>
        <Box sx={{ display: "flex", gap: 1.5 }}>
          {generated > 0 && (
            <Button
              variant="outlined"
              color="error"
              startIcon={<DeleteIcon />}
              onClick={() => setDeleteOpen(true)}
              disabled={isRunning || geminiGenerating}
              size="large"
            >
              Delete All
            </Button>
          )}
          {imageBackend === "gemini" ? (
            <Button
              variant="contained"
              color="warning"
              startIcon={geminiGenerating ? <CircularProgress size={16} color="inherit" /> : <GeminiIcon />}
              onClick={handleGenerateGemini}
              disabled={geminiGenerating || isRunning}
              size="large"
            >
              {geminiGenerating ? "Queuing…" : generated > 0 ? "Re-generate (Gemini)" : "Generate All (Gemini)"}
            </Button>
          ) : (
            <Tooltip title={!comfyOnline ? "Start ComfyUI first" : ""}>
              <span>
                <Button
                  variant="contained"
                  startIcon={isRunning ? <CircularProgress size={16} color="inherit" /> : <GenerateIcon />}
                  onClick={handleGenerateAll}
                  disabled={isRunning || triggerJob.isPending || !comfyOnline}
                  size="large"
                >
                  {isRunning ? "Generating…" : generated > 0 ? "Continue / Retry" : "Generate All"}
                </Button>
              </span>
            </Tooltip>
          )}
        </Box>
      </Box>

      {geminiError && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setGeminiError(null)}>
          {geminiError}
        </Alert>
      )}

      <DeleteConfirmDialog
        open={deleteOpen}
        title="Delete All Images"
        description={`Delete all ${generated} generated scene images for this project? You will need to regenerate them from scratch.`}
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
          { label: "Failed", value: scenes.filter((s) => s.status === "failed").length, color: "#FF5252" },
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
      {isRunning && (
        <Box sx={{ mb: 3 }}>
          <Box sx={{ display: "flex", justifyContent: "space-between", mb: 0.5 }}>
            <Typography variant="caption" color="text.secondary">
              {imgProgress.completed > 0
                ? `Generating scene ${imgProgress.completed + 1} of ${imgProgress.total}…`
                : "Initialising generation…"}
            </Typography>
            <Typography variant="caption" fontWeight={700} color="primary.light">
              {imgProgress.progress.toFixed(0)}%
            </Typography>
          </Box>
          <LinearProgress variant="determinate" value={imgProgress.progress} sx={{ height: 8, borderRadius: 2 }} />
        </Box>
      )}

      {/* No prompts warning */}
      {!imagesLoading && total === 0 && (
        <Alert severity="warning" sx={{ mb: 3, borderRadius: 2 }}>
          No image_prompts.txt found in project input. Upload the file on the Project page first.
        </Alert>
      )}

      {/* Clip generation mode toolbar */}
      {total > 0 && (
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            gap: 1.5,
            mb: 2,
            px: 2,
            py: 1,
            borderRadius: 2,
            bgcolor: "rgba(108,99,255,0.06)",
            border: "1px solid rgba(108,99,255,0.18)",
          }}
        >
          <ClipsIcon sx={{ fontSize: 16, color: "primary.light", flexShrink: 0 }} />
          <Typography variant="caption" color="text.secondary" sx={{ flex: 1 }}>
            <strong style={{ color: "#6C63FF" }}>{ltxCount}</strong> scenes → LTX-Video AI clip&nbsp;&nbsp;·&nbsp;&nbsp;
            <strong style={{ color: "#00BCD4" }}>{animCount}</strong> scenes → Ken Burns animated clip.
            Toggle checkboxes below to choose per scene.
          </Typography>
          <Divider orientation="vertical" flexItem sx={{ mx: 0.5 }} />
          <Tooltip title="Select all scenes for LTX-Video AI animation">
            <Button
              size="small"
              startIcon={<SelectAllIcon />}
              onClick={() => setLtxSceneIds(new Set(scenes.map((s) => s.scene_id)))}
              disabled={ltxCount === total}
              sx={{ minWidth: 0, fontSize: "0.72rem" }}
            >
              All LTX
            </Button>
          </Tooltip>
          <Tooltip title="All scenes get Ken Burns animated clips (no ComfyUI needed)">
            <Button
              size="small"
              startIcon={<KenBurnsIcon />}
              onClick={() => setLtxSceneIds(new Set())}
              disabled={ltxCount === 0}
              sx={{ minWidth: 0, fontSize: "0.72rem" }}
            >
              All Animated
            </Button>
          </Tooltip>
        </Box>
      )}

      <Grid container spacing={2}>
        {/* Gallery */}
        <Grid item xs={12} md={8}>
          <Card>
            <CardContent sx={{ p: 2 }}>
              <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 2 }}>
                <Typography variant="subtitle1" fontWeight={700}>Scene Gallery</Typography>
                <Typography variant="caption" color="text.secondary">
                  {generated}/{total} ready · click to preview
                </Typography>
              </Box>

              {imagesLoading ? (
                <Grid container spacing={1.5}>
                  {Array.from({ length: 9 }).map((_, i) => (
                    <Grid item xs={6} sm={4} key={i}>
                      <Skeleton variant="rectangular" sx={{ aspectRatio: "16/9", borderRadius: 2 }} />
                    </Grid>
                  ))}
                </Grid>
              ) : scenes.length === 0 ? (
                <Box sx={{ py: 6, textAlign: "center", color: "text.disabled", border: "1px dashed rgba(255,255,255,0.06)", borderRadius: 2 }}>
                  <PendingIcon sx={{ fontSize: 40, mb: 1 }} />
                  <Typography variant="body2">No scenes yet — upload image_prompts.txt and generate</Typography>
                </Box>
              ) : (
                <Grid container spacing={1.5}>
                  {scenes.map((scene) => (
                    <Grid item xs={6} sm={4} key={scene.scene_id}>
                      <SceneCard
                        scene={scene}
                        projectId={currentProject.id}
                        isSelected={selectedScene?.scene_id === scene.scene_id}
                        isLtxSelected={ltxSceneIds.has(scene.scene_id)}
                        isRegenerating={regeneratingIds.has(scene.scene_id)}
                        isReplacing={replacingIds.has(scene.scene_id)}
                        onSelect={() => setSelectedScene(scene)}
                        onToggleLtx={() => toggleLtxSceneId(scene.scene_id)}
                        onRegenerate={() => handleRegenerate(scene)}
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
                isRegenerating={selectedScene ? regeneratingIds.has(selectedScene.scene_id) : false}
                onRegenerate={() => selectedScene && handleRegenerate(selectedScene)}
              />
            </CardContent>
          </Card>

          <ProgressCard
            title="Image Generation"
            status={imgProgress.status}
            progress={total > 0 ? (generated / total) * 100 : imgProgress.progress}
            completed={generated}
            total={total}
          />
        </Grid>
      </Grid>
    </Box>
  );
}
