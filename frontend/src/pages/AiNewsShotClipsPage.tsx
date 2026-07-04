import React, { useState, useRef, useCallback, useEffect } from "react";
import {
  Box,
  Typography,
  Grid,
  Card,
  CardContent,
  Button,
  Chip,
  IconButton,
  Tooltip,
  Alert,
  CircularProgress,
  Divider,
  Switch,
  FormControlLabel,
  Tabs,
  Tab,
  TextField,
  Snackbar,
} from "@mui/material";
import {
  Refresh as RefreshIcon,
  CheckCircle as CheckIcon,
  RadioButtonUnchecked as PendingIcon,
  Smartphone as ShortIcon,
  DeleteForever as DeleteIcon,
  RecordVoiceOver as NarratorIcon,
  BrandingWatermark as LogoIcon,
  Info as InfoIcon,
  StopCircle as StopIcon,
  Videocam as LtxIcon,
} from "@mui/icons-material";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useProjectStore } from "../store";
import { aiNewsApi, SectionStatus } from "../api/aiNews";
import { useWebSocket } from "../hooks/useWebSocket";
import { useComfyUIStatus } from "../hooks/useImages";
import ComfyUIControl from "../components/common/ComfyUIControl";
import DeleteConfirmDialog from "../components/common/DeleteConfirmDialog";
import { VideoPlayer, MediaActions, LtxSceneGrid } from "../components/ai-news/ClipMediaControls";

// ── Colours ───────────────────────────────────────────────────────────────────

function sectionColor(type: SectionStatus["type"]) {
  switch (type) {
    case "intro":  return "#6C63FF";
    case "outro":  return "#6C63FF";
    case "agenda": return "#FF9100";
    case "story":  return "#00BCD4";
  }
}

function sectionTabLabel(s: SectionStatus): string {
  if (s.type === "intro") return "Intro";
  if (s.type === "outro") return "Outro";
  if (s.type === "agenda") return "Agenda";
  return `S${s.story_num}`;
}

// ── Per-section detail view ───────────────────────────────────────────────────

interface SectionDetailProps {
  section: SectionStatus;
  projectId: string;
  isShotGenerating: boolean;
  isLtxGenerating: boolean;
  comfyOnline: boolean;
  includeNarrator: boolean;
  narratorText: string;
  includeLogo: boolean;
  ltxProgressMsg?: string;
  ltxError?: string;
  shotError?: string;
  onGenerateShot: () => void;
  onReplaceShot: (file: File) => void;
  onDeleteShot: () => void;
  onGenerateLtx: () => void;
  onDeleteLtx: () => void;
}

function SectionDetail(p: SectionDetailProps) {
  const { section, projectId, isShotGenerating, isLtxGenerating, comfyOnline, ltxProgressMsg, ltxError, shotError } = p;
  const color   = sectionColor(section.type);
  const shotUrl = aiNewsApi.getShortUrl(projectId, section.label);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>

      {/* ── Vertical LTX Video Generation ─────────────────────────────── */}
      {section.type !== "agenda" && (
        <Card sx={{ borderColor: section.has_vertical_ltx ? "rgba(0,230,118,0.4)" : "rgba(255,255,255,0.06)" }}>
          <CardContent sx={{ p: 2, "&:last-child": { pb: 2 } }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
              <LtxIcon sx={{ fontSize: 15, color: "success.main" }} />
              <Typography variant="subtitle2" fontWeight={700}>Vertical LTX Clips</Typography>
              {section.has_vertical_ltx ? (
                <Chip label="LTX ✓" size="small" sx={{ height: 16, fontSize: "0.58rem", bgcolor: "rgba(0,230,118,0.1)", color: "success.main" }} />
              ) : section.vertical_ltx_scene_count > 0 && (
                <Chip
                  label={`${section.vertical_ltx_scene_count}/${section.ltx_expected_scenes} scenes`}
                  size="small"
                  sx={{ height: 16, fontSize: "0.58rem", bgcolor: "rgba(255,145,0,0.1)", color: "warning.main" }}
                />
              )}
              {isLtxGenerating && (
                <Chip icon={<CircularProgress size={9} />} label="Generating…" size="small" color="primary" variant="outlined" sx={{ height: 16, fontSize: "0.58rem" }} />
              )}
            </Box>
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
              Animates each 9:16 shot image via ComfyUI + LTX-Video. Fully separate pass from the 16:9 clip animation — used by the Shot as its native-vertical video source.
            </Typography>
            {isLtxGenerating && ltxProgressMsg && (
              <Typography variant="caption" color="primary.main" display="block" sx={{ mb: 1, fontStyle: "italic" }}>
                {ltxProgressMsg}
              </Typography>
            )}
            {!isLtxGenerating && ltxError && (
              <Alert severity="error" sx={{ mb: 1, py: 0.25, fontSize: "0.7rem" }}>
                {ltxError}
              </Alert>
            )}
            {!isLtxGenerating && !ltxError && !section.has_vertical_ltx && section.vertical_ltx_scene_count > 0 && (
              <Alert severity="warning" sx={{ mb: 1, py: 0.25, fontSize: "0.7rem" }}>
                Only {section.vertical_ltx_scene_count} of {section.ltx_expected_scenes} scenes have a clip — click Generate again to fill in the rest (already-generated scenes are skipped).
              </Alert>
            )}
            <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap" }}>
              <Tooltip title={!section.has_vertical_images ? "Generate shot images first" : !comfyOnline ? "Start ComfyUI first (port 8188)" : section.has_vertical_ltx ? "Re-generate vertical LTX clips" : section.vertical_ltx_scene_count > 0 ? "Continue generating the remaining scenes" : "Generate vertical LTX-Video clips via ComfyUI"}>
                <span>
                  <Button
                    size="small"
                    variant={section.has_vertical_ltx ? "outlined" : "contained"}
                    startIcon={isLtxGenerating ? <CircularProgress size={12} color="inherit" /> : <LtxIcon />}
                    onClick={p.onGenerateLtx}
                    disabled={isLtxGenerating || !section.has_vertical_images || !comfyOnline}
                    sx={{
                      fontSize: "0.68rem", py: 0.4, px: 1,
                      ...(!section.has_vertical_ltx && { bgcolor: "success.main", "&:hover": { bgcolor: "success.dark" } }),
                    }}
                  >
                    {isLtxGenerating
                      ? "…"
                      : section.has_vertical_ltx
                      ? "Re-gen Vertical LTX"
                      : section.vertical_ltx_scene_count > 0
                      ? `Continue Vertical LTX (${section.vertical_ltx_scene_count}/${section.ltx_expected_scenes})`
                      : "Generate Vertical LTX"}
                  </Button>
                </span>
              </Tooltip>
              {section.has_vertical_ltx && (
                <Tooltip title="Delete vertical LTX clips for this section">
                  <IconButton size="small" color="error" sx={{ p: 0.5, opacity: 0.6, "&:hover": { opacity: 1 } }} onClick={p.onDeleteLtx}>
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              )}
            </Box>

            <LtxSceneGrid
              projectId={projectId}
              label={section.label}
              aspectRatio="9/16"
              color="#00E676"
              active={section.vertical_ltx_scene_count > 0 && !isLtxGenerating}
              fetchScenes={aiNewsApi.getSectionLtxVerticalScenes}
              sceneUrl={aiNewsApi.getSectionLtxVerticalSceneUrl}
              queryKeyPrefix="ai-news-ltx-vertical-scenes"
            />
          </CardContent>
        </Card>
      )}

      {/* ── 9:16 Shot ──────────────────────────────────────────────────── */}
      <Card>
        <CardContent sx={{ p: 2, "&:last-child": { pb: 2 } }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1.5 }}>
            <ShortIcon sx={{ fontSize: 15, color }} />
            <Typography variant="subtitle2" fontWeight={700}>Shot (9:16)</Typography>
            {section.has_vertical_ltx
              ? <Chip label="Vertical LTX" size="small" sx={{ height: 16, fontSize: "0.58rem", bgcolor: "rgba(0,230,118,0.1)", color: "success.main" }} />
              : section.has_voice && <Chip label="Voice ✓" size="small" sx={{ height: 16, fontSize: "0.58rem", bgcolor: "rgba(0,230,118,0.1)", color: "success.main" }} />}
            {!section.has_vertical_ltx && section.has_subtitles && <Chip label="Subs ✓" size="small" sx={{ height: 16, fontSize: "0.58rem", bgcolor: "rgba(0,188,212,0.1)", color: "info.main" }} />}
            {!section.has_vertical_ltx && p.includeNarrator && p.narratorText && <Chip label="Narrator" size="small" sx={{ height: 16, fontSize: "0.58rem", bgcolor: "rgba(108,99,255,0.12)", color: "#6C63FF" }} />}
            {!section.has_vertical_ltx && p.includeLogo     && <Chip label="Logo"     size="small" sx={{ height: 16, fontSize: "0.58rem", bgcolor: "rgba(255,145,0,0.1)", color: "warning.main" }} />}
            {isShotGenerating && <Chip icon={<CircularProgress size={9} />} label="Generating…" size="small" color="primary" variant="outlined" sx={{ height: 16, fontSize: "0.58rem" }} />}
          </Box>

          {section.has_short ? (
            <Box sx={{ display: "flex", gap: 2 }}>
              <Box sx={{ flex: "0 0 180px" }}>
                <VideoPlayer src={shotUrl} aspectRatio="9/16" color={color} label="9:16" maxWidth={180} />
              </Box>
              <Box sx={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "center" }}>
                <Typography variant="caption" color="text.secondary" display="block">
                  9:16 vertical shot ready
                </Typography>
              </Box>
            </Box>
          ) : (
            <Box sx={{
              height: 120, display: "flex", flexDirection: "column",
              alignItems: "center", justifyContent: "center", gap: 1,
              border: "1px dashed rgba(255,255,255,0.08)", borderRadius: 2, bgcolor: "#080810",
            }}>
              <ShortIcon sx={{ fontSize: 30, color: "rgba(255,255,255,0.08)" }} />
              <Typography variant="caption" color="text.disabled">
                {section.has_vertical_ltx ? "No shot yet — click Generate (uses vertical LTX clips)" : section.has_voice ? "No shot yet — click Generate" : "Generate voice first"}
              </Typography>
            </Box>
          )}

          {!isShotGenerating && shotError && (
            <Alert severity="error" sx={{ mt: 1, py: 0.25, fontSize: "0.7rem" }}>{shotError}</Alert>
          )}

          <MediaActions
            color={color}
            hasMedia={section.has_short}
            isGenerating={isShotGenerating}
            canGenerate={section.has_voice}
            generateLabel={section.has_vertical_ltx ? "shot (vertical LTX)" : "shot"}
            downloadUrl={shotUrl}
            downloadName={`${section.label}_shot.mp4`}
            onGenerate={p.onGenerateShot}
            onReplace={p.onReplaceShot}
            onDelete={section.has_short ? p.onDeleteShot : undefined}
          />
        </CardContent>
      </Card>
    </Box>
  );
}

// ── All-sections overview row ─────────────────────────────────────────────────

function SectionOverviewRow({
  section, isShotGen, isLtxGen, onSelect,
}: {
  section: SectionStatus;
  isShotGen: boolean;
  isLtxGen: boolean;
  onSelect: () => void;
}) {
  const color = sectionColor(section.type);
  return (
    <Box
      onClick={onSelect}
      sx={{
        display: "flex", alignItems: "center", gap: 1.5, p: 1.25,
        borderRadius: 1.5, cursor: "pointer",
        border: "1px solid rgba(255,255,255,0.05)",
        "&:hover": { bgcolor: "rgba(255,255,255,0.03)" },
      }}
    >
      <Chip
        label={section.type === "story" ? `#${section.story_num}` : section.type.toUpperCase()}
        size="small"
        sx={{ bgcolor: color + "22", color, fontSize: "0.62rem", height: 18, flexShrink: 0 }}
      />
      <Typography variant="body2" sx={{ flex: 1 }} noWrap>{section.title}</Typography>
      <Box sx={{ display: "flex", gap: 0.5, alignItems: "center", flexShrink: 0 }}>
        {/* Vertical LTX status */}
        {section.type !== "agenda" && (
          isLtxGen
            ? <CircularProgress size={11} />
            : section.has_vertical_ltx
            ? <Chip label="LTX ✓" size="small" sx={{ height: 14, fontSize: "0.55rem", bgcolor: "rgba(0,230,118,0.15)", color: "success.main" }} />
            : <Chip label="LTX —" size="small" sx={{ height: 14, fontSize: "0.55rem", bgcolor: "rgba(255,255,255,0.04)", color: "text.disabled" }} />
        )}
        {/* Shot status */}
        {isShotGen
          ? <CircularProgress size={11} />
          : section.has_short
          ? <Chip label="Shot ✓" size="small" sx={{ height: 14, fontSize: "0.55rem", bgcolor: "rgba(0,230,118,0.1)", color: "success.main" }} />
          : section.has_voice
          ? <Chip label="Shot —" size="small" sx={{ height: 14, fontSize: "0.55rem", bgcolor: "rgba(255,145,0,0.08)", color: "warning.main" }} />
          : <Chip label="No voice" size="small" sx={{ height: 14, fontSize: "0.55rem", bgcolor: "rgba(255,255,255,0.04)", color: "text.disabled" }} />}
      </Box>
    </Box>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function AiNewsShotClipsPage() {
  const currentProject = useProjectStore((s) => s.currentProject);
  const projectId = currentProject?.id ?? "";
  const queryClient = useQueryClient();

  const [sectionLabel, setSectionLabel] = useState<string | null>(null);
  const [shotGenerating, setShotGenerating] = useState<Set<string>>(new Set());
  const [ltxGenerating,  setLtxGenerating]  = useState<Set<string>>(new Set());
  const [ltxProgress,    setLtxProgress]    = useState<Record<string, string>>({});
  const [ltxErrors,      setLtxErrors]      = useState<Record<string, string>>({});
  const [shotErrors,     setShotErrors]     = useState<Record<string, string>>({});
  const [errorSnack,     setErrorSnack]     = useState<string>("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Shot options
  const [includeNarrator, setIncludeNarrator] = useState(true);
  const [narratorText, setNarratorText]       = useState("Deep Dive AI");
  const [includeLogo, setIncludeLogo]         = useState(false);

  // Delete state
  const [deleteAllOpen, setDeleteAllOpen]   = useState(false);
  const [deleteAllLoading, setDeleteAllLoading] = useState(false);
  const [shotDeleteLabel, setShotDeleteLabel] = useState<string | null>(null);
  const [shotDeleting, setShotDeleting]       = useState(false);

  useComfyUIStatus(); // keeps ComfyUIControl's cache warm

  const { data: ltxStatus } = useQuery({
    queryKey: ["ai-news-ltx-status"],
    queryFn:  aiNewsApi.getLtxStatus,
    staleTime: 15_000,
    refetchInterval: 20_000,
  });
  const ltxOnline = ltxStatus?.online ?? false;

  const { data: allSections = [], isLoading, error, refetch } = useQuery({
    queryKey: ["ai-news-sections", projectId],
    queryFn:  () => aiNewsApi.getSections(projectId),
    enabled:  !!projectId,
    staleTime: 10_000,
    refetchInterval: (shotGenerating.size > 0 || ltxGenerating.size > 0) ? 6_000 : false,
  });
  // Shot (9:16) content only exists for story sections — intro, agenda, and
  // outro never get vertical images / vertical LTX / a shot video.
  const sections = allSections.filter((s) => s.type === "story");

  // Detect completed generations via has_short / has_vertical_ltx flags
  useEffect(() => {
    const doneShots = [...shotGenerating].filter((l) => sections.find((s) => s.label === l)?.has_short);
    const doneLtx   = [...ltxGenerating].filter((l)  => sections.find((s) => s.label === l)?.has_vertical_ltx);
    if (doneShots.length) setShotGenerating((p) => { const n = new Set(p); doneShots.forEach((l) => n.delete(l)); return n; });
    if (doneLtx.length)   setLtxGenerating((p)  => { const n = new Set(p); doneLtx.forEach((l)   => n.delete(l)); return n; });
  }, [sections]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  // WS listener — clears generating state when backend finishes (success OR failure).
  const wsOnMessage = useCallback(
    (event: string, data: Record<string, unknown>) => {
      const jobType = String(data.job_type ?? "");
      const label   = String(data.section ?? "");

      // Real-time progress from vertical LTX generation
      if (event === "ltx_progress" && (jobType === "section_ltx_vertical" || jobType === "section_ltx_vertical_all")) {
        const msg = String(data.message ?? "");
        if (label) setLtxProgress((p) => ({ ...p, [label]: msg }));
        return;
      }

      if (event !== "job_completed" && event !== "job_failed") return;

      if (jobType === "section_short" && label) {
        setShotGenerating((p) => { const n = new Set(p); n.delete(label); return n; });
        if (event === "job_failed") {
          const errMsg = String((data as Record<string, unknown>).error ?? "Shot generation failed");
          setShotErrors((p) => ({ ...p, [label]: errMsg }));
          setErrorSnack(`Shot failed for '${label}': ${errMsg}`);
        } else {
          setShotErrors((p) => { const n = { ...p }; delete n[label]; return n; });
        }
        refetch();
      }
      if ((jobType === "section_ltx_vertical" || jobType === "section_ltx_vertical_all") && label) {
        setLtxGenerating((p) => { const n = new Set(p); n.delete(label); return n; });
        setLtxProgress((p) => { const n = { ...p }; delete n[label]; return n; });
        if (event === "job_failed") {
          setLtxErrors((p) => ({ ...p, [label]: String(data.error ?? "Vertical LTX generation failed") }));
        } else {
          setLtxErrors((p) => { const n = { ...p }; delete n[label]; return n; });
        }
        refetch();
        queryClient.invalidateQueries({ queryKey: ["ai-news-ltx-vertical-scenes", projectId, label] });
      }
      if (jobType === "section_ltx_vertical_all" && !label) {
        setLtxGenerating(new Set());
        setLtxProgress({});
        refetch();
        queryClient.invalidateQueries({ queryKey: ["ai-news-ltx-vertical-scenes", projectId] });
      }
    },
    [refetch, queryClient, projectId],
  );
  useWebSocket({ projectId, onMessage: wsOnMessage });

  const refreshSections = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["ai-news-sections", projectId] });
  }, [queryClient, projectId]);

  // ── Shot actions ──────────────────────────────────────────────────────────

  const triggerShot = useCallback(async (label: string) => {
    if (shotGenerating.has(label)) return;
    setShotErrors((p) => { const n = { ...p }; delete n[label]; return n; });
    setShotGenerating((p) => new Set(p).add(label));
    try {
      await aiNewsApi.generateSectionShort(projectId, label, {
        narrator_text: includeNarrator && narratorText ? narratorText : undefined,
        logo_path: includeLogo ? "logo.png" : undefined,
      });
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      const msg = detail ?? (err as Error)?.message ?? "Request failed";
      setShotErrors((p) => ({ ...p, [label]: msg }));
      setErrorSnack(`Shot error (${label}): ${msg}`);
      setShotGenerating((p) => { const n = new Set(p); n.delete(label); return n; });
    }
  }, [projectId, shotGenerating, includeNarrator, narratorText, includeLogo]);

  const handleReplaceShot = useCallback(async (label: string, file: File) => {
    try {
      await aiNewsApi.uploadSectionShort(projectId, label, file);
      refreshSections();
    } catch { /* ignore */ }
  }, [projectId, refreshSections]);

  const handleShotDelete = async () => {
    if (!shotDeleteLabel) return;
    setShotDeleting(true);
    try {
      await aiNewsApi.deleteSectionShort(projectId, shotDeleteLabel);
      refreshSections();
    } finally {
      setShotDeleting(false);
      setShotDeleteLabel(null);
    }
  };

  // ── Vertical LTX actions ──────────────────────────────────────────────────

  const triggerLtx = useCallback(async (label: string) => {
    if (ltxGenerating.has(label)) return;
    setLtxGenerating((p) => new Set(p).add(label));
    setLtxErrors((p) => { const n = { ...p }; delete n[label]; return n; });
    try {
      await aiNewsApi.generateSectionLtxVertical(projectId, label);
    } catch {
      setLtxGenerating((p) => { const n = new Set(p); n.delete(label); return n; });
    }
  }, [projectId, ltxGenerating]);

  const handleLtxDelete = useCallback(async (label: string) => {
    try {
      await aiNewsApi.deleteSectionLtxVertical(projectId, label);
      refreshSections();
      queryClient.invalidateQueries({ queryKey: ["ai-news-ltx-vertical-scenes", projectId, label] });
    } catch { /* ignore */ }
  }, [projectId, refreshSections, queryClient]);

  // ── Bulk actions ──────────────────────────────────────────────────────────

  const generateAllShots = () => {
    const pending = sections.filter((s) => !s.has_short && s.has_voice && s.type !== "agenda");
    pending.forEach((s) => triggerShot(s.label));
  };

  const generateAllLtx = async () => {
    const pending = sections.filter((s) => !s.has_vertical_ltx && s.has_vertical_images && s.type !== "agenda");
    if (pending.length === 0) return;
    pending.forEach((s) => setLtxGenerating((p) => new Set(p).add(s.label)));
    setLtxErrors({});
    try {
      await aiNewsApi.generateAllSectionsLtxVertical(projectId);
    } catch {
      setLtxGenerating(new Set());
    }
  };

  const handleDeleteAll = async () => {
    setDeleteAllLoading(true);
    try {
      await aiNewsApi.deleteAllSectionShorts(projectId);
      refreshSections();
    } finally {
      setDeleteAllLoading(false);
      setDeleteAllOpen(false);
    }
  };

  // ── Guards ────────────────────────────────────────────────────────────────

  if (!currentProject) {
    return <Box sx={{ p: 3 }}><Alert severity="info">Open or create a project first.</Alert></Box>;
  }
  if (currentProject.project_type !== "ai_news") {
    return <Box sx={{ p: 3 }}><Alert severity="info">This page is only available for AI News projects.</Alert></Box>;
  }

  // ── Computed ──────────────────────────────────────────────────────────────

  const shotsReady    = sections.filter((s) => s.has_short).length;
  const ltxReady      = sections.filter((s) => s.has_vertical_ltx).length;
  const totalSections = sections.length;
  const isAnyGen      = shotGenerating.size > 0 || ltxGenerating.size > 0;
  const hasAnyMedia   = shotsReady > 0;

  const selectedSection = sectionLabel
    ? sections.find((s) => s.label === sectionLabel) ?? null
    : null;

  const tabIndex = sectionLabel === null
    ? 0
    : (sections.findIndex((s) => s.label === sectionLabel) + 1) || 0;

  const canGenerate = !isAnyGen &&
    sections.some((s) => s.has_voice && s.type !== "agenda" && !s.has_short);

  return (
    <Box>
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", mb: 2.5 }}>
        <Box>
          <Typography variant="h4" fontWeight={800} gutterBottom>AI News Shot Clips</Typography>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <Chip label="AI NEWS" color="warning" size="small" variant="outlined" sx={{ fontSize: "0.65rem" }} />
            <Typography variant="body2" color="text.secondary">
              {ltxReady}/{totalSections - 1} vertical LTX · {shotsReady}/{totalSections} shots
              {isAnyGen && ` · ${shotGenerating.size + ltxGenerating.size} generating…`}
            </Typography>
          </Box>
        </Box>
        <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
          <ComfyUIControl />

          <Tooltip title="Refresh">
            <IconButton size="small" onClick={() => refetch()} disabled={isLoading}>
              {isLoading ? <CircularProgress size={18} /> : <RefreshIcon fontSize="small" />}
            </IconButton>
          </Tooltip>

          {/* Delete All — shots */}
          {hasAnyMedia && (
            <Button
              variant="outlined" color="error" size="large"
              startIcon={<DeleteIcon />}
              onClick={() => setDeleteAllOpen(true)}
              disabled={isAnyGen}
            >
              Delete All
            </Button>
          )}

          {/* Stop — clears stuck generating state */}
          {isAnyGen && (
            <Tooltip title="Stop tracking generation (does not cancel backend jobs already running)">
              <Button
                variant="outlined" color="error" size="large"
                startIcon={<StopIcon />}
                onClick={() => { setShotGenerating(new Set()); setLtxGenerating(new Set()); }}
              >
                Stop
              </Button>
            </Tooltip>
          )}

          {/* Generate all vertical LTX */}
          {sections.some((s) => !s.has_vertical_ltx && s.has_vertical_images && s.type !== "agenda") && (
            <Tooltip title={!ltxOnline ? "Start ComfyUI first (port 8188)" : "Animate the 9:16 shot images into native-vertical LTX clips for all ready sections"}>
              <span>
                <Button
                  variant="outlined" size="large"
                  startIcon={ltxGenerating.size > 0 ? <CircularProgress size={16} color="inherit" /> : <LtxIcon />}
                  onClick={generateAllLtx}
                  disabled={ltxGenerating.size > 0 || !ltxOnline}
                  sx={{ borderColor: "#00E676", color: "#00E676", "&:hover": { borderColor: "#00c766", bgcolor: "rgba(0,230,118,0.05)" } }}
                >
                  {ltxGenerating.size > 0 ? `LTX… (${ltxGenerating.size})` : "Generate All Vertical LTX"}
                </Button>
              </span>
            </Tooltip>
          )}

          {/* Generate shots */}
          <Tooltip title={canGenerate ? "Generate 9:16 shots for all voice-ready sections" : "All voice-ready sections already have shots"}>
            <span>
              <Button
                variant="contained" size="large"
                startIcon={shotGenerating.size > 0 ? <CircularProgress size={16} color="inherit" /> : <ShortIcon />}
                onClick={generateAllShots}
                disabled={!canGenerate}
              >
                {shotGenerating.size > 0
                  ? `Generating… (${shotGenerating.size} left)`
                  : shotsReady > 0 ? "Generate Missing Shots" : "Generate All Shots"}
              </Button>
            </span>
          </Tooltip>
        </Box>
      </Box>

      {/* ── Stats row ──────────────────────────────────────────────────────── */}
      <Grid container spacing={1.5} sx={{ mb: 2.5 }}>
        {[
          { label: "Total Sections",   value: totalSections, color: "#6C63FF" },
          { label: "Vertical LTX Ready", value: ltxReady,     color: "#00E676" },
          { label: "Shots Ready",      value: shotsReady,     color: "#FF9100" },
        ].map(({ label, value, color }) => (
          <Grid item xs={4} key={label}>
            <Card variant="outlined" sx={{ textAlign: "center", py: 1, borderColor: "rgba(255,255,255,0.06)" }}>
              <Typography variant="h6" fontWeight={800} sx={{ color, lineHeight: 1 }}>{value}</Typography>
              <Typography variant="caption" color="text.disabled">{label}</Typography>
            </Card>
          </Grid>
        ))}
      </Grid>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>Failed to load sections — is the backend running?</Alert>
      )}

      {/* ── Section tabs ────────────────────────────────────────────────────── */}
      <Box sx={{ borderBottom: 1, borderColor: "divider", mb: 2 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
          <Chip label="AI NEWS SECTIONS" size="small" color="warning" variant="outlined" sx={{ fontSize: "0.6rem", height: 18 }} />
        </Box>
        <Tabs
          value={tabIndex}
          onChange={(_, v: number) => setSectionLabel(v === 0 ? null : sections[v - 1]?.label ?? null)}
          variant="scrollable"
          scrollButtons="auto"
          sx={{
            minHeight: 32,
            "& .MuiTab-root": { minHeight: 32, py: 0.5, fontSize: "0.72rem", minWidth: 52, px: 1.5 },
          }}
        >
          <Tab label="All" />
          {sections.map((sec) => {
            const isGen = shotGenerating.has(sec.label) || ltxGenerating.has(sec.label);
            const allDone = sec.has_short && (sec.type === "agenda" || sec.has_vertical_ltx);
            return (
              <Tab
                key={sec.label}
                title={sec.title}
                label={
                  <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                    {isGen
                      ? <CircularProgress size={10} />
                      : allDone
                      ? <CheckIcon sx={{ fontSize: 10, color: "success.main" }} />
                      : sec.has_vertical_ltx
                      ? <LtxIcon sx={{ fontSize: 10, color: "success.main" }} />
                      : null}
                    {sectionTabLabel(sec)}
                  </Box>
                }
              />
            );
          })}
        </Tabs>
      </Box>

      {isLoading ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
          <CircularProgress />
        </Box>
      ) : (
        <Grid container spacing={2}>
          {/* ── Left: content area ─────────────────────────────────────────── */}
          <Grid item xs={12} md={8}>
            {sectionLabel === null ? (
              /* All sections overview */
              <Card>
                <CardContent sx={{ p: 2 }}>
                  <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1.5 }}>
                    <Typography variant="subtitle1" fontWeight={700}>All Sections</Typography>
                    <Chip
                      icon={<InfoIcon sx={{ fontSize: "12px !important" }} />}
                      label="Shots use native 9:16 vertical LTX clips when available"
                      size="small"
                      sx={{ bgcolor: "rgba(255,255,255,0.04)", color: "text.secondary", fontSize: "0.62rem", height: 20 }}
                    />
                  </Box>
                  {sections.length === 0 ? (
                    <Box sx={{ py: 6, textAlign: "center", color: "text.disabled", border: "1px dashed rgba(255,255,255,0.06)", borderRadius: 2 }}>
                      <ShortIcon sx={{ fontSize: 40, mb: 1 }} />
                      <Typography variant="body2">No sections found</Typography>
                    </Box>
                  ) : (
                    <Box sx={{ display: "flex", flexDirection: "column", gap: 0.75 }}>
                      {sections.map((sec) => (
                        <SectionOverviewRow
                          key={sec.label}
                          section={sec}
                          isShotGen={shotGenerating.has(sec.label)}
                          isLtxGen={ltxGenerating.has(sec.label)}
                          onSelect={() => setSectionLabel(sec.label)}
                        />
                      ))}
                    </Box>
                  )}
                </CardContent>
              </Card>
            ) : selectedSection ? (
              /* Per-section detail */
              <Box>
                <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1.5 }}>
                  <Typography variant="subtitle1" fontWeight={700}>{selectedSection.title}</Typography>
                  <Box sx={{ display: "flex", gap: 0.5 }}>
                    {selectedSection.has_voice      && <Chip label="Voice ✓"    size="small" sx={{ height: 20, fontSize: "0.62rem", bgcolor: "rgba(0,230,118,0.1)", color: "success.main" }} />}
                    {selectedSection.has_subtitles  && <Chip label="Subtitles ✓" size="small" sx={{ height: 20, fontSize: "0.62rem", bgcolor: "rgba(0,188,212,0.1)", color: "info.main" }} />}
                  </Box>
                </Box>
                <SectionDetail
                  section={selectedSection}
                  projectId={projectId}
                  isShotGenerating={shotGenerating.has(sectionLabel)}
                  isLtxGenerating={ltxGenerating.has(sectionLabel)}
                  comfyOnline={ltxOnline}
                  includeNarrator={includeNarrator}
                  narratorText={narratorText}
                  includeLogo={includeLogo}
                  ltxProgressMsg={ltxProgress[sectionLabel]}
                  ltxError={ltxErrors[sectionLabel]}
                  shotError={shotErrors[sectionLabel]}
                  onGenerateShot={() => triggerShot(sectionLabel)}
                  onReplaceShot={(f) => handleReplaceShot(sectionLabel, f)}
                  onDeleteShot={() => setShotDeleteLabel(sectionLabel)}
                  onGenerateLtx={() => triggerLtx(sectionLabel)}
                  onDeleteLtx={() => handleLtxDelete(sectionLabel)}
                />
              </Box>
            ) : null}
          </Grid>

          {/* ── Right: action panel + progress ─────────────────────────────── */}
          <Grid item xs={12} md={4}>
            {/* Section action card */}
            <Card sx={{ mb: 2, position: "sticky", top: 80 }}>
              <CardContent sx={{ p: 2 }}>
                <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1.5 }}>
                  {sectionLabel ? selectedSection?.title ?? sectionLabel : "Select a Section"}
                </Typography>

                {sectionLabel && selectedSection ? (
                  <>
                    {/* Status row */}
                    <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, mb: 1.5 }}>
                      {[
                        { label: "Voice",       done: selectedSection.has_voice     },
                        { label: "Shot Images", done: !!selectedSection.has_vertical_images },
                        { label: "Vert LTX",    done: selectedSection.has_vertical_ltx },
                        { label: "Shot",        done: selectedSection.has_short     },
                      ].map(({ label, done }) => (
                        <Chip
                          key={label}
                          icon={done
                            ? <CheckIcon sx={{ fontSize: "10px !important", color: "success.main !important" }} />
                            : <PendingIcon sx={{ fontSize: "10px !important" }} />}
                          label={label}
                          size="small"
                          sx={{ height: 20, fontSize: "0.62rem",
                            bgcolor: done ? "rgba(0,230,118,0.08)" : "rgba(255,255,255,0.04)",
                            color: done ? "success.main" : "text.disabled",
                          }}
                        />
                      ))}
                    </Box>

                    <Divider sx={{ mb: 1.5, borderColor: "rgba(255,255,255,0.06)" }} />

                    {/* Shot options */}
                    <Typography variant="caption" fontWeight={700} color="text.secondary"
                      sx={{ textTransform: "uppercase", fontSize: "0.62rem", display: "block", mb: 0.75 }}>
                      Shot Options
                    </Typography>

                    <Box sx={{ mb: 0.75 }}>
                      <FormControlLabel
                        control={<Switch checked={includeNarrator} onChange={(e) => setIncludeNarrator(e.target.checked)} size="small" />}
                        label={<Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}><NarratorIcon sx={{ fontSize: 13 }} /><Typography variant="caption">Channel Branding</Typography></Box>}
                        sx={{ "& .MuiFormControlLabel-label": { fontSize: "0.78rem" } }}
                      />
                      {includeNarrator && (
                        <TextField
                          size="small" fullWidth value={narratorText}
                          onChange={(e) => setNarratorText(e.target.value)}
                          placeholder="e.g. Deep Dive AI"
                          sx={{ mt: 0.5, "& .MuiInputBase-input": { fontSize: "0.8rem", py: 0.75 } }}
                        />
                      )}
                    </Box>

                    <Box sx={{ mb: 1.5 }}>
                      <FormControlLabel
                        control={<Switch checked={includeLogo} onChange={(e) => setIncludeLogo(e.target.checked)} size="small" />}
                        label={<Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}><LogoIcon sx={{ fontSize: 13 }} /><Typography variant="caption">Logo Watermark</Typography></Box>}
                        sx={{ "& .MuiFormControlLabel-label": { fontSize: "0.78rem" } }}
                      />
                      {includeLogo && (
                        <Typography variant="caption" color="text.disabled" display="block" sx={{ ml: 4, mt: 0.25, fontSize: "0.65rem" }}>
                          Place logo.png in project's input/ folder
                        </Typography>
                      )}
                    </Box>

                    {/* Quick generate buttons */}
                    <Box sx={{ display: "flex", gap: 0.75, flexDirection: "column" }}>
                      {selectedSection.type !== "agenda" && (
                        <Tooltip title={!ltxOnline ? "Start ComfyUI first (port 8188)" : ""}>
                          <span style={{ width: "100%" }}>
                            <Button fullWidth size="small"
                              variant={selectedSection.has_vertical_ltx ? "outlined" : "contained"}
                              color="success"
                              startIcon={ltxGenerating.has(sectionLabel) ? <CircularProgress size={12} color="inherit" /> : <LtxIcon />}
                              onClick={() => triggerLtx(sectionLabel)}
                              disabled={ltxGenerating.has(sectionLabel) || !selectedSection.has_vertical_images || !ltxOnline}
                            >
                              {ltxGenerating.has(sectionLabel) ? "Generating Vertical LTX…" : selectedSection.has_vertical_ltx ? "Re-gen Vertical LTX" : "Generate Vertical LTX"}
                            </Button>
                          </span>
                        </Tooltip>
                      )}
                      <Button fullWidth size="small"
                        variant={selectedSection.has_short ? "outlined" : "contained"}
                        startIcon={shotGenerating.has(sectionLabel) ? <CircularProgress size={12} color="inherit" /> : <ShortIcon />}
                        onClick={() => triggerShot(sectionLabel)}
                        disabled={shotGenerating.has(sectionLabel) || !selectedSection.has_voice}
                      >
                        {shotGenerating.has(sectionLabel) ? "Generating shot…" : selectedSection.has_short ? "Re-gen Shot" : "Generate Shot"}
                      </Button>
                    </Box>
                  </>
                ) : (
                  <Typography variant="caption" color="text.disabled">
                    Select a section tab to view and generate shots
                  </Typography>
                )}
              </CardContent>
            </Card>

            {/* Section progress */}
            <Card>
              <CardContent sx={{ p: 2, "&:last-child": { pb: 2 } }}>
                <Typography variant="caption" fontWeight={700} color="text.secondary"
                  sx={{ textTransform: "uppercase", fontSize: "0.65rem", letterSpacing: 0.5, display: "block", mb: 1 }}>
                  Section Progress
                </Typography>
                <Box sx={{ display: "flex", flexDirection: "column", gap: 0.6 }}>
                  {sections.map((sec) => {
                    const isGen = shotGenerating.has(sec.label) || ltxGenerating.has(sec.label);
                    const allDone = sec.has_short && (sec.type === "agenda" || sec.has_vertical_ltx);
                    return (
                      <Box
                        key={sec.label}
                        onClick={() => setSectionLabel(sec.label)}
                        sx={{
                          display: "flex", alignItems: "center", gap: 0.75,
                          cursor: "pointer", borderRadius: 1,
                          px: 0.5, py: 0.25,
                          bgcolor: sectionLabel === sec.label ? "rgba(0,230,118,0.08)" : "transparent",
                          "&:hover": { bgcolor: "rgba(255,255,255,0.03)" },
                        }}
                      >
                        {isGen
                          ? <CircularProgress size={12} sx={{ flexShrink: 0 }} />
                          : allDone
                          ? <CheckIcon sx={{ fontSize: 12, color: "success.main", flexShrink: 0 }} />
                          : <PendingIcon sx={{ fontSize: 12, color: "rgba(255,255,255,0.18)", flexShrink: 0 }} />}
                        <Typography
                          variant="caption"
                          sx={{ flex: 1, fontSize: "0.68rem", color: allDone ? "text.primary" : "text.disabled" }}
                          noWrap
                        >
                          {sec.title}
                        </Typography>
                        <Box sx={{ display: "flex", gap: 0.25, flexShrink: 0 }}>
                          {sec.has_vertical_ltx && <Chip label="L" size="small" sx={{ height: 12, fontSize: "0.5rem", minWidth: 16, bgcolor: "rgba(0,230,118,0.15)", color: "success.main" }} />}
                          {sec.has_short         && <Chip label="S" size="small" sx={{ height: 12, fontSize: "0.5rem", minWidth: 16, bgcolor: sectionColor(sec.type) + "22", color: sectionColor(sec.type) }} />}
                        </Box>
                      </Box>
                    );
                  })}
                </Box>
              </CardContent>
            </Card>

            {/* Info card */}
            <Card sx={{ mt: 2 }}>
              <CardContent sx={{ p: 2 }}>
                <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 0.75 }}>
                  <LtxIcon sx={{ fontSize: 13, mr: 0.5, verticalAlign: "middle", color: "success.main" }} />
                  9:16 Pipeline
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block">
                  <strong>Vertical LTX</strong> animates each 9:16 shot image (from the Shot Images page) via ComfyUI. This is the native-vertical video for the shot.
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
                  <strong>Shot (9:16)</strong> = vertical LTX video + narration. Falls back to the 16:9 clip (blurred/padded) when no vertical LTX or shot images exist yet.
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
                  Use <strong>Replace</strong> to upload a custom MP4 for any shot.
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}

      {/* ── Delete dialogs ───────────────────────────────────────────────────── */}
      <DeleteConfirmDialog
        open={deleteAllOpen}
        title="Delete All Shots"
        description={`Delete all ${shotsReady} shot${shotsReady !== 1 ? "s" : ""}? You will need to re-generate them.`}
        loading={deleteAllLoading}
        onConfirm={handleDeleteAll}
        onCancel={() => setDeleteAllOpen(false)}
      />
      <DeleteConfirmDialog
        open={!!shotDeleteLabel}
        title={`Delete Shot — ${sections.find((s) => s.label === shotDeleteLabel)?.title ?? shotDeleteLabel ?? ""}`}
        description="Delete this section's 9:16 shot? You can re-generate it at any time."
        loading={shotDeleting}
        onConfirm={handleShotDelete}
        onCancel={() => setShotDeleteLabel(null)}
      />

      <Snackbar
        open={!!errorSnack}
        autoHideDuration={8000}
        onClose={() => setErrorSnack("")}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
        message={errorSnack}
      />
    </Box>
  );
}
