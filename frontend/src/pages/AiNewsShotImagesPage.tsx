import React, { useState, useCallback, useRef, useEffect } from "react";

// Module-level version counter for cache-busting after replace/regenerate.
// key = `${projectId}:${label}:${sceneId}`
const _shotImageVersions: Record<string, number> = {};

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
  AutoAwesome as GenerateIcon,
  Refresh as RegenerateIcon,
  ZoomIn as ZoomIcon,
  CheckCircle as DoneIcon,
  Error as ErrorIcon,
  HourglassEmpty as PendingIcon,
  DeleteForever as DeleteIcon,
  FileUpload as UploadIcon,
  StopCircle as StopIcon,
  Smartphone as ShotIcon,
} from "@mui/icons-material";
import { useProjectStore } from "../store";
import { useComfyUIStatus } from "../hooks/useImages";
import { useWebSocket } from "../hooks/useWebSocket";
import { aiNewsApi, SectionContent } from "../api/aiNews";
import { servicesApi } from "../api/services";
import { useQuery } from "@tanstack/react-query";
import { settingsApi } from "../api/settings";
import DeleteConfirmDialog from "../components/common/DeleteConfirmDialog";
import ComfyUIControl from "../components/common/ComfyUIControl";
import AiNewsSectionTabs from "../components/ai-news/AiNewsSectionTabs";

// ---------------------------------------------------------------------------
// Helpers
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
  const lines = imagePrompts.split("\n").filter((l) => l.trim().length > 0);
  return lines[sceneId - 1] ?? "";
}

function expectedSceneCount(s: SectionContent): number {
  if (!s.scenes_json) return 0;
  try { return (JSON.parse(s.scenes_json) as unknown[]).length; } catch { return 0; }
}

// ---------------------------------------------------------------------------
// Shot scene card — 9:16 version of the AI-news scene card
// ---------------------------------------------------------------------------
interface ShotSceneCardProps {
  projectId: string;
  label: string;
  sceneId: number;
  isSelected: boolean;
  isRegenerating: boolean;
  isReplacing: boolean;
  onSelect: () => void;
  onRegenerate: () => void;
  onReplace: (file: File) => void;
}

function ShotSceneCard({
  projectId, label, sceneId, isSelected,
  isRegenerating, isReplacing, onSelect, onRegenerate, onReplace,
}: ShotSceneCardProps) {
  const [imgError, setImgError] = useState(false);
  const [imgLoaded, setImgLoaded] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const vKey = `${projectId}:${label}:${sceneId}`;
  const version = _shotImageVersions[vKey];
  const base = aiNewsApi.getSectionImageVerticalUrl(projectId, label, sceneId);
  const imageUrl = version ? `${base}?v=${version}` : base;

  return (
    <Box
      onClick={onSelect}
      sx={{
        position: "relative",
        cursor: "pointer",
        borderRadius: 2,
        overflow: "hidden",
        border: isSelected ? "2px solid #00E676" : "2px solid transparent",
        aspectRatio: "9/16",
        bgcolor: "#080810",
        transition: "border-color 0.15s ease",
        "&:hover .scene-actions": { opacity: 1 },
        "&:hover": { borderColor: isSelected ? "#00E676" : "rgba(0,230,118,0.5)" },
      }}
    >
      {!imgError ? (
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
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%" }}>
          <ErrorIcon sx={{ color: "error.main", fontSize: 20 }} />
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
      {!imgError && (
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
            sx={{ bgcolor: "rgba(0,230,118,0.5)", color: "white" }}>
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
// Shot preview panel — 9:16 version of the AI-news preview panel
// ---------------------------------------------------------------------------
interface ShotPreviewPanelProps {
  projectId: string;
  label: string;
  sceneId: number | null;
  prompt: string;
  sectionTitle: string;
  isRegenerating: boolean;
  onRegenerate: () => void;
}

function ShotPreviewPanel({
  projectId, label, sceneId, prompt,
  sectionTitle, isRegenerating, onRegenerate,
}: ShotPreviewPanelProps) {
  const [imgError, setImgError] = useState(false);

  if (!sceneId) {
    return (
      <Box sx={{
        height: 320, display: "flex", flexDirection: "column",
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
  const version = _shotImageVersions[vKey];
  const base = aiNewsApi.getSectionImageVerticalUrl(projectId, label, sceneId);
  const imageUrl = version ? `${base}?v=${version}` : base;

  return (
    <Box>
      {/* Image */}
      <Box sx={{ width: "100%", maxWidth: 220, mx: "auto", aspectRatio: "9/16", borderRadius: 2, overflow: "hidden", bgcolor: "#080810", mb: 1.5 }}>
        {!imgError ? (
          <img src={imageUrl} alt={`Scene ${sceneId}`} onError={() => setImgError(true)}
            style={{ width: "100%", height: "100%", objectFit: "cover" }} />
        ) : (
          <Box sx={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 1 }}>
            <ErrorIcon sx={{ color: "error.main" }} />
            <Typography variant="caption" color="text.disabled">Could not load image</Typography>
          </Box>
        )}
      </Box>

      {/* Scene info */}
      <Box sx={{ mb: 1.5 }}>
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 0.5 }}>
          <Typography variant="subtitle2" fontWeight={700}>Scene #{sceneId}</Typography>
          <Chip label="Ready" size="small" color="success" variant="outlined" sx={{ height: 18, fontSize: "0.62rem" }} />
        </Box>
        <Typography variant="caption" color="text.secondary" display="block">{sectionTitle}</Typography>
      </Box>

      {/* Prompt */}
      {prompt && (
        <Box sx={{
          p: 1.25, bgcolor: "rgba(0,230,118,0.06)",
          border: "1px solid rgba(0,230,118,0.15)", borderRadius: 1.5, mb: 1.5,
        }}>
          <Typography variant="caption" color="success.main" fontWeight={600} display="block" sx={{ mb: 0.25 }}>
            FLUX PROMPT (9:16)
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
        fullWidth variant="outlined" size="small" color="success"
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
export default function AiNewsShotImagesPage() {
  const currentProject = useProjectStore((s) => s.currentProject);
  const { data: comfyStatus } = useComfyUIStatus();
  const { data: appSettings } = useQuery({ queryKey: ["settings"], queryFn: settingsApi.get, staleTime: 60_000 });
  const imageBackend = appSettings?.gemini?.image_backend ?? "flux";
  const comfyOnline = comfyStatus?.online ?? false;

  const [sectionLabel, setSectionLabel] = useState<string | null>(null);
  const [selectedSceneId, setSelectedSceneId] = useState<number | null>(null);
  const [sectionGenerating, setSectionGenerating] = useState<Set<string>>(new Set());
  const sectionQueueRef = useRef<SectionContent[]>([]);
  const [regenIds, setRegenIds] = useState<Set<string>>(new Set());
  const [replaceIds, setReplaceIds] = useState<Set<string>>(new Set());
  const [, forceUpdate] = useState(0);
  const [sectionDeleteOpen, setSectionDeleteOpen] = useState(false);
  const [sectionDeleting, setSectionDeleting] = useState(false);
  const [allDeleteOpen, setAllDeleteOpen] = useState(false);
  const [allDeleting, setAllDeleting] = useState(false);

  const sectionsQuery = useQuery({
    queryKey: ["ai-news-sections-content", currentProject?.id ?? ""],
    queryFn: () => aiNewsApi.getSectionsContent(currentProject!.id),
    enabled: !!currentProject?.id,
    staleTime: 0,
  });
  // Shot (9:16) images only exist for story sections — intro and outro never
  // get shot content.
  const sections = (sectionsQuery.data ?? []).filter((s) => s.type === "story");
  const selectedSection = sectionLabel ? sections.find((s) => s.label === sectionLabel) : null;
  const sectionsRefetch = sectionsQuery.refetch;

  const fireNextRef = useRef<() => void>(() => {});
  fireNextRef.current = () => {
    if (!currentProject || sectionQueueRef.current.length === 0) return;
    const next = sectionQueueRef.current.shift()!;
    aiNewsApi.generateSectionImagesVertical(currentProject.id, next.label).catch((err: unknown) => {
      console.error(`Section ${next.label} vertical images failed to start:`, err);
      setSectionGenerating((prev) => { const n = new Set(prev); n.delete(next.label); return n; });
      fireNextRef.current();
    });
  };

  const handleWs = useCallback(
    (event: string, data: Record<string, unknown>) => {
      if (String(data.job_type ?? "") !== "section_images_vertical") return;
      const label = String(data.section ?? "");
      if ((event === "job_completed" || event === "job_failed") && label) {
        setSectionGenerating((prev) => { const n = new Set(prev); n.delete(label); return n; });
        sectionsRefetch();
        fireNextRef.current();
      }
    },
    [sectionsRefetch],
  );
  useWebSocket({ projectId: currentProject?.id, onMessage: handleWs });

  useEffect(() => {
    if (!sectionGenerating.size) return;
    const id = setInterval(() => sectionsRefetch(), 10_000);
    return () => clearInterval(id);
  }, [sectionGenerating.size, sectionsRefetch]);

  const isSectionComplete = (s: SectionContent) =>
    s.image_prompts !== null &&
    expectedSceneCount(s) > 0 &&
    s.vertical_image_scene_ids.length >= expectedSceneCount(s);

  const withImages  = sections.filter((s) => s.vertical_image_scene_ids.length > 0).length;
  const fullyDone   = sections.filter(isSectionComplete).length;
  const withPrompts = sections.filter((s) => s.image_prompts !== null).length;
  const isAnyGen    = sectionGenerating.size > 0;
  const canGenerate = !isAnyGen && withPrompts > 0 &&
    sections.some((s) => s.image_prompts !== null && s.vertical_image_scene_ids.length < expectedSceneCount(s));

  const viewIds   = selectedSection?.vertical_image_scene_ids ?? [];
  const viewLabel = sectionLabel ?? "";

  const totalSectionScenes = (() => {
    if (!selectedSection?.scenes_json) return 0;
    try { return (JSON.parse(selectedSection.scenes_json) as unknown[]).length; }
    catch { return 0; }
  })();

  const selectedScenePrompt = parseSectionPrompt(
    selectedSection?.image_prompts ?? null,
    selectedSceneId ?? 0,
  );

  const allSectionsWithImages = sections.filter((s) => s.vertical_image_scene_ids.length > 0);

  const generateAllSections = async () => {
    if (!currentProject || !sections.length) return;
    const pending = sections.filter(
      (s) => s.image_prompts !== null && s.vertical_image_scene_ids.length < expectedSceneCount(s),
    );
    if (!pending.length) return;

    setSectionGenerating(new Set(pending.map((s) => s.label)));
    sectionQueueRef.current = pending.slice(1);
    try {
      await aiNewsApi.generateSectionImagesVertical(currentProject.id, pending[0].label);
    } catch (err: unknown) {
      console.error(`First section ${pending[0].label} failed to start:`, err);
      setSectionGenerating((prev) => { const n = new Set(prev); n.delete(pending[0].label); return n; });
      fireNextRef.current();
    }
  };

  const handleSceneRegenerate = useCallback(
    async (label: string, sceneId: number) => {
      if (!currentProject) return;
      const key = `${label}:${sceneId}`;
      if (regenIds.has(key)) return;
      setRegenIds((prev) => new Set(prev).add(key));
      try {
        await aiNewsApi.regenerateSectionImageVertical(currentProject.id, label, sceneId);
        const poll = setInterval(() => {
          sectionsQuery.refetch().then(({ data }) => {
            const sec = data?.find((s) => s.label === label);
            if (sec?.vertical_image_scene_ids.includes(sceneId)) {
              _shotImageVersions[`${currentProject.id}:${label}:${sceneId}`] = Date.now();
              setRegenIds((prev) => { const n = new Set(prev); n.delete(key); return n; });
              forceUpdate((n) => n + 1);
              clearInterval(poll);
            }
          });
        }, 4000);
        setTimeout(() => {
          clearInterval(poll);
          setRegenIds((prev) => { const n = new Set(prev); n.delete(key); return n; });
        }, 180_000);
      } catch (err) {
        console.error(`Failed to regenerate vertical scene ${sceneId} in ${label}:`, err);
        setRegenIds((prev) => { const n = new Set(prev); n.delete(key); return n; });
      }
    },
    [currentProject, regenIds, sectionsQuery]
  );

  const handleSceneReplace = useCallback(
    async (label: string, sceneId: number, file: File) => {
      if (!currentProject) return;
      const key = `${label}:${sceneId}`;
      if (replaceIds.has(key)) return;
      setReplaceIds((prev) => new Set(prev).add(key));
      try {
        await aiNewsApi.uploadSectionImageVertical(currentProject.id, label, sceneId, file);
        _shotImageVersions[`${currentProject.id}:${label}:${sceneId}`] = Date.now();
        forceUpdate((n) => n + 1);
        sectionsQuery.refetch();
      } catch (err) {
        console.error(`Failed to replace vertical scene ${sceneId} in ${label}:`, err);
      } finally {
        setReplaceIds((prev) => { const n = new Set(prev); n.delete(key); return n; });
      }
    },
    [currentProject, replaceIds, sectionsQuery]
  );

  const handleAllDelete = async () => {
    if (!currentProject) return;
    setAllDeleting(true);
    try {
      await aiNewsApi.deleteAllSectionImagesVertical(currentProject.id);
      setSelectedSceneId(null);
      sectionsQuery.refetch();
    } catch (err) {
      console.error("Failed to delete all vertical section images:", err);
    } finally {
      setAllDeleting(false);
      setAllDeleteOpen(false);
    }
  };

  const handleSectionDelete = async () => {
    if (!currentProject || !sectionLabel) return;
    setSectionDeleting(true);
    try {
      await aiNewsApi.deleteSectionImagesVertical(currentProject.id, sectionLabel);
      setSelectedSceneId(null);
      sectionsQuery.refetch();
    } catch (err) {
      console.error(`Failed to delete vertical images for section ${sectionLabel}:`, err);
    } finally {
      setSectionDeleting(false);
      setSectionDeleteOpen(false);
    }
  };

  // ── Guards ────────────────────────────────────────────────────────────────

  if (!currentProject) {
    return <Box sx={{ p: 3 }}><Alert severity="info">Open or create a project first.</Alert></Box>;
  }
  if (currentProject.project_type !== "ai_news") {
    return <Box sx={{ p: 3 }}><Alert severity="info">This page is only available for AI News projects.</Alert></Box>;
  }

  return (
    <Box>
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", mb: 2.5 }}>
        <Box>
          <Typography variant="h4" fontWeight={800} gutterBottom>Shot Image Generation</Typography>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <Chip label="AI NEWS" color="warning" size="small" variant="outlined" sx={{ fontSize: "0.65rem" }} />
            <Typography variant="body2" color="text.secondary">
              {withImages}/{sections.length} sections with 9:16 shot images
              {isAnyGen && ` · generating ${sectionGenerating.size} section(s)…`}
            </Typography>
          </Box>
        </Box>
        <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
          {imageBackend === "flux" && <ComfyUIControl />}

          {isAnyGen && (
            <Tooltip title="Stop generating and clear ComfyUI queue">
              <Button
                variant="outlined" color="error" size="large"
                startIcon={<StopIcon />}
                onClick={async () => {
                  setSectionGenerating(new Set());
                  try { await servicesApi.clearComfyUIQueue(); } catch { /* ignore */ }
                }}
              >
                Stop
              </Button>
            </Tooltip>
          )}

          {withImages > 0 && !isAnyGen && (
            <Button
              variant="outlined" color="error" size="large"
              startIcon={<DeleteIcon />}
              onClick={() => setAllDeleteOpen(true)}
            >
              Delete All
            </Button>
          )}

          <Tooltip title={!comfyOnline && imageBackend === "flux" ? "Start ComfyUI first" : canGenerate ? "Generate 9:16 shot images for all sections that are missing them" : "All sections already have shot images"}>
            <span>
              <Button
                variant="contained" size="large"
                startIcon={<GenerateIcon />}
                onClick={generateAllSections}
                disabled={isAnyGen || !canGenerate || (imageBackend === "flux" && !comfyOnline)}
                sx={{ bgcolor: "success.main", "&:hover": { bgcolor: "success.dark" } }}
              >
                {isAnyGen
                  ? `Generating… (${sectionGenerating.size} left)`
                  : fullyDone < sections.length ? "Generate Missing Shot Images" : "Generate All Shot Images"}
              </Button>
            </span>
          </Tooltip>
        </Box>
      </Box>

      {/* ── Section tabs ──────────────────────────────────────────────────── */}
      <AiNewsSectionTabs
        sections={sections}
        selected={sectionLabel}
        onSelect={(lbl) => { setSectionLabel(lbl); setSelectedSceneId(null); }}
      />

      {/* ── Stats row ─────────────────────────────────────────────────────── */}
      {sectionLabel && (
        <Grid container spacing={1.5} sx={{ mb: 2 }}>
          {[
            { label: "Total Scenes", value: totalSectionScenes || viewIds.length, color: "text.primary" },
            { label: "Generated",    value: viewIds.length, color: "success.main" },
            { label: "Missing",      value: Math.max(0, (totalSectionScenes || viewIds.length) - viewIds.length), color: "warning.main" },
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
            Generating 9:16 shot images for {selectedSection?.title ?? viewLabel}…
          </Typography>
        </Box>
      )}

      {/* ── Gallery + Preview ─────────────────────────────────────────────── */}
      <Grid container spacing={2}>
        {/* Left: image gallery */}
        <Grid item xs={12} md={8}>
          <Card>
            <CardContent sx={{ p: 2 }}>
              <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1.5 }}>
                <Typography variant="subtitle1" fontWeight={700}>
                  {sectionLabel ? `${selectedSection?.title ?? sectionLabel} — Shot Images (9:16)` : "All Sections — Shot Images (9:16)"}
                </Typography>
                <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                  {sectionGenerating.has(viewLabel) && (
                    <Chip icon={<CircularProgress size={10} />} label="Generating…" size="small" color="primary" variant="outlined" sx={{ fontSize: "0.65rem" }} />
                  )}
                  {sectionLabel && viewIds.length > 0 && (
                    <Typography variant="caption" color="text.secondary">{viewIds.length} images</Typography>
                  )}
                  {sectionLabel && viewIds.length > 0 && (
                    <Tooltip title={`Delete all shot images for ${selectedSection?.title ?? sectionLabel}`}>
                      <IconButton size="small" color="error" onClick={() => setSectionDeleteOpen(true)} sx={{ opacity: 0.7, "&:hover": { opacity: 1 } }}>
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  )}
                </Box>
              </Box>

              {sectionLabel !== null ? (
                viewIds.length === 0 ? (
                  <Box sx={{ py: 6, textAlign: "center", color: "text.disabled", border: "1px dashed rgba(255,255,255,0.06)", borderRadius: 2 }}>
                    {sectionGenerating.has(viewLabel)
                      ? <CircularProgress sx={{ mb: 1 }} />
                      : <PendingIcon sx={{ fontSize: 40, mb: 1 }} />}
                    <Typography variant="body2" sx={{ mb: 1.5 }}>
                      {sectionGenerating.has(viewLabel)
                        ? "Generating shot images for this section…"
                        : selectedSection?.image_prompts
                        ? 'No shot images yet — click "Generate This Section" to start'
                        : "No image prompts for this section yet — generate section content first"}
                    </Typography>
                    {!sectionGenerating.has(viewLabel) && selectedSection?.image_prompts && (
                      <Button
                        variant="outlined" size="small" color="success" startIcon={<GenerateIcon />}
                        onClick={async () => {
                          setSectionGenerating((prev) => new Set(prev).add(viewLabel));
                          try { await aiNewsApi.generateSectionImagesVertical(currentProject.id, viewLabel); }
                          catch { setSectionGenerating((prev) => { const n = new Set(prev); n.delete(viewLabel); return n; }); }
                        }}
                      >
                        Generate This Section
                      </Button>
                    )}
                  </Box>
                ) : (
                  <Grid container spacing={1.5}>
                    {viewIds.map((sceneId) => {
                      const rKey = `${viewLabel}:${sceneId}`;
                      return (
                        <Grid item xs={6} sm={4} md={3} key={sceneId}>
                          <ShotSceneCard
                            projectId={currentProject.id}
                            label={viewLabel}
                            sceneId={sceneId}
                            isSelected={selectedSceneId === sceneId}
                            isRegenerating={regenIds.has(rKey)}
                            isReplacing={replaceIds.has(rKey)}
                            onSelect={() => setSelectedSceneId(selectedSceneId === sceneId ? null : sceneId)}
                            onRegenerate={() => handleSceneRegenerate(viewLabel, sceneId)}
                            onReplace={(f) => handleSceneReplace(viewLabel, sceneId, f)}
                          />
                        </Grid>
                      );
                    })}
                  </Grid>
                )
              ) : (
                allSectionsWithImages.length === 0 ? (
                  <Box sx={{ py: 6, textAlign: "center", color: "text.disabled", border: "1px dashed rgba(255,255,255,0.06)", borderRadius: 2 }}>
                    <PendingIcon sx={{ fontSize: 40, mb: 1 }} />
                    <Typography variant="body2">No shot images yet — click "Generate All Shot Images" to start</Typography>
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
                          <Chip label={`${sec.vertical_image_scene_ids.length} images`} size="small" sx={{ height: 16, fontSize: "0.6rem" }} />
                        </Box>
                        <Grid container spacing={1}>
                          {sec.vertical_image_scene_ids.slice(0, 6).map((sceneId) => {
                            const url = aiNewsApi.getSectionImageVerticalUrl(currentProject.id, sec.label, sceneId);
                            return (
                              <Grid item xs={2} key={`${sec.label}-${sceneId}`}>
                                <Box
                                  onClick={() => { setSectionLabel(sec.label); setSelectedSceneId(sceneId); }}
                                  sx={{ aspectRatio: "9/16", borderRadius: 1, overflow: "hidden", cursor: "pointer", "&:hover": { opacity: 0.8 } }}
                                >
                                  <Box component="img" src={url} sx={{ width: "100%", height: "100%", objectFit: "cover" }} />
                                </Box>
                              </Grid>
                            );
                          })}
                          {sec.vertical_image_scene_ids.length > 6 && (
                            <Grid item xs={2}>
                              <Box
                                onClick={() => setSectionLabel(sec.label)}
                                sx={{
                                  aspectRatio: "9/16", borderRadius: 1, bgcolor: "rgba(255,255,255,0.04)",
                                  border: "1px dashed rgba(255,255,255,0.12)",
                                  display: "flex", alignItems: "center", justifyContent: "center",
                                  cursor: "pointer", "&:hover": { bgcolor: "rgba(255,255,255,0.07)" },
                                }}
                              >
                                <Typography variant="caption" color="text.disabled">
                                  +{sec.vertical_image_scene_ids.length - 6} more
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

        {/* Right: preview panel */}
        <Grid item xs={12} md={4}>
          <Card sx={{ position: "sticky", top: 80 }}>
            <CardContent sx={{ p: 2 }}>
              <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1.5 }}>
                <ShotIcon sx={{ fontSize: 14, mr: 0.5, verticalAlign: "middle", color: "success.main" }} />
                Preview
              </Typography>
              <ShotPreviewPanel
                projectId={currentProject.id}
                label={viewLabel}
                sceneId={selectedSceneId}
                prompt={selectedScenePrompt}
                sectionTitle={selectedSection?.title ?? viewLabel}
                isRegenerating={selectedSceneId ? regenIds.has(`${viewLabel}:${selectedSceneId}`) : false}
                onRegenerate={() => selectedSceneId && handleSceneRegenerate(viewLabel, selectedSceneId)}
              />
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* ── Delete dialogs ────────────────────────────────────────────────── */}
      <DeleteConfirmDialog
        open={allDeleteOpen}
        title="Delete All Shot Images"
        description="Delete all generated 9:16 shot images across every section? You will need to re-generate them."
        loading={allDeleting}
        onConfirm={handleAllDelete}
        onCancel={() => setAllDeleteOpen(false)}
      />
      <DeleteConfirmDialog
        open={sectionDeleteOpen}
        title={`Delete Shot Images — ${selectedSection?.title ?? sectionLabel ?? ""}`}
        description="Delete all 9:16 shot images for this section? You can re-generate them at any time."
        loading={sectionDeleting}
        onConfirm={handleSectionDelete}
        onCancel={() => setSectionDeleteOpen(false)}
      />
    </Box>
  );
}
