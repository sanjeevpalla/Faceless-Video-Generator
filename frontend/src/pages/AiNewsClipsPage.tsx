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
  LinearProgress,
  Switch,
  FormControlLabel,
  Tabs,
  Tab,
  TextField,
  Snackbar,
} from "@mui/material";
import {
  Refresh as RefreshIcon,
  PlayArrow as PlayIcon,
  Pause as PauseIcon,
  Download as DownloadIcon,
  CheckCircle as CheckIcon,
  RadioButtonUnchecked as PendingIcon,
  AutoAwesome as GenerateIcon,
  MovieCreation as ClipIcon,
  Smartphone as ShortIcon,
  DeleteForever as DeleteIcon,
  Replay as RegenerateIcon,
  FileUpload as ReplaceIcon,
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

function VideoPlayer({ src, aspectRatio, color, label, maxWidth, extraOverlay }: VideoPlayerProps) {
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

function MediaActions({
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

// ── Per-section detail view ───────────────────────────────────────────────────

interface SectionDetailProps {
  section: SectionStatus;
  projectId: string;
  isClipGenerating: boolean;
  isShortGenerating: boolean;
  isLtxGenerating: boolean;
  comfyOnline: boolean;
  includeNarrator: boolean;
  narratorText: string;
  includeLogo: boolean;
  ltxProgressMsg?: string;
  ltxError?: string;
  clipError?: string;
  onGenerateClip: () => void;
  onReplaceClip: (file: File) => void;
  onDeleteClip: () => void;
  onGenerateShort: () => void;
  onReplaceShort: (file: File) => void;
  onDeleteShort: () => void;
  onGenerateLtx: () => void;
  onDeleteLtx: () => void;
}

function SectionDetail(p: SectionDetailProps) {
  const { section, projectId, isClipGenerating, isShortGenerating, isLtxGenerating, comfyOnline, ltxProgressMsg, ltxError, clipError } = p;
  const color    = sectionColor(section.type);
  const clipUrl  = aiNewsApi.getClipUrl(projectId, section.label);
  const shortUrl = aiNewsApi.getShortUrl(projectId, section.label);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>

      {/* ── LTX Video Generation ───────────────────────────────────────── */}
      {section.type !== "agenda" && (
        <Card sx={{ borderColor: section.has_ltx ? "rgba(108,99,255,0.4)" : "rgba(255,255,255,0.06)" }}>
          <CardContent sx={{ p: 2, "&:last-child": { pb: 2 } }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
              <LtxIcon sx={{ fontSize: 15, color: "#6C63FF" }} />
              <Typography variant="subtitle2" fontWeight={700}>LTX Video Clips</Typography>
              {section.has_ltx && (
                <Chip label="LTX ✓" size="small" sx={{ height: 16, fontSize: "0.58rem", bgcolor: "rgba(108,99,255,0.12)", color: "#6C63FF" }} />
              )}
              {isLtxGenerating && (
                <Chip icon={<CircularProgress size={9} />} label="Generating…" size="small" color="primary" variant="outlined" sx={{ height: 16, fontSize: "0.58rem" }} />
              )}
            </Box>
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
              Animates each scene image via ComfyUI + LTX-Video. Used by Clips (16:9) and Shots (9:16) as the video source.
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
            <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap" }}>
              <Tooltip title={!section.has_images ? "Generate images first" : !comfyOnline ? "Start ComfyUI first (port 8188)" : section.has_ltx ? "Re-generate LTX clips" : "Generate LTX-Video clips via ComfyUI"}>
                <span>
                  <Button
                    size="small"
                    variant={section.has_ltx ? "outlined" : "contained"}
                    startIcon={isLtxGenerating ? <CircularProgress size={12} color="inherit" /> : <LtxIcon />}
                    onClick={p.onGenerateLtx}
                    disabled={isLtxGenerating || !section.has_images || !comfyOnline}
                    sx={{
                      fontSize: "0.68rem", py: 0.4, px: 1,
                      ...(!section.has_ltx && { bgcolor: "#6C63FF", "&:hover": { bgcolor: "#5853e6" } }),
                    }}
                  >
                    {isLtxGenerating ? "…" : section.has_ltx ? "Re-gen LTX" : "Generate LTX"}
                  </Button>
                </span>
              </Tooltip>
              {section.has_ltx && (
                <Tooltip title="Delete LTX clips for this section">
                  <IconButton size="small" color="error" sx={{ p: 0.5, opacity: 0.6, "&:hover": { opacity: 1 } }} onClick={p.onDeleteLtx}>
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              )}
            </Box>
          </CardContent>
        </Card>
      )}

      {/* ── 16:9 Clip ──────────────────────────────────────────────────── */}
      <Card>
        <CardContent sx={{ p: 2, "&:last-child": { pb: 2 } }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1.5 }}>
            <ClipIcon sx={{ fontSize: 15, color }} />
            <Typography variant="subtitle2" fontWeight={700}>Clip (16:9)</Typography>
            {section.has_ltx      && <Chip label="LTX ✓"    size="small" sx={{ height: 16, fontSize: "0.58rem", bgcolor: "rgba(108,99,255,0.12)", color: "#6C63FF" }} />}
            {section.has_voice     && <Chip label="Voice ✓"    size="small" sx={{ height: 16, fontSize: "0.58rem", bgcolor: "rgba(0,230,118,0.1)", color: "success.main" }} />}
            {section.has_subtitles && <Chip label="Subs ✓"     size="small" sx={{ height: 16, fontSize: "0.58rem", bgcolor: "rgba(0,188,212,0.1)", color: "info.main" }} />}
            {isClipGenerating      && <Chip icon={<CircularProgress size={9} />} label="Generating…" size="small" color="primary" variant="outlined" sx={{ height: 16, fontSize: "0.58rem" }} />}
          </Box>

          {section.has_clip ? (
            <VideoPlayer src={clipUrl} aspectRatio="16/9" color={color} label="16:9" />
          ) : (
            <Box sx={{
              aspectRatio: "16/9", display: "flex", flexDirection: "column",
              alignItems: "center", justifyContent: "center", gap: 1,
              border: "1px dashed rgba(255,255,255,0.08)", borderRadius: 2, bgcolor: "#080810",
            }}>
              <ClipIcon sx={{ fontSize: 36, color: "rgba(255,255,255,0.08)" }} />
              <Typography variant="caption" color="text.disabled" align="center">
                {section.type === "agenda" || section.has_voice ? "No clip yet — click Generate or run Video Render" : "Generate voice first"}
              </Typography>
            </Box>
          )}

          {!isClipGenerating && clipError && (
            <Alert severity="error" sx={{ mt: 1, py: 0.25, fontSize: "0.7rem" }}>{clipError}</Alert>
          )}

          <MediaActions
            color={color}
            hasMedia={section.has_clip}
            isGenerating={isClipGenerating}
            canGenerate={section.type === "agenda" || section.has_voice}
            generateLabel="clip"
            downloadUrl={clipUrl}
            downloadName={`${section.label}.mp4`}
            onGenerate={p.onGenerateClip}
            onReplace={p.onReplaceClip}
            onDelete={section.has_clip ? p.onDeleteClip : undefined}
          />
        </CardContent>
      </Card>

      {/* ── 9:16 Short ─────────────────────────────────────────────────── */}
      <Card>
        <CardContent sx={{ p: 2, "&:last-child": { pb: 2 } }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1.5 }}>
            <ShortIcon sx={{ fontSize: 15, color }} />
            <Typography variant="subtitle2" fontWeight={700}>Shot (9:16)</Typography>
            {section.has_ltx
              ? <Chip label="LTX Shot" size="small" sx={{ height: 16, fontSize: "0.58rem", bgcolor: "rgba(108,99,255,0.12)", color: "#6C63FF" }} />
              : section.has_voice && <Chip label="Voice ✓" size="small" sx={{ height: 16, fontSize: "0.58rem", bgcolor: "rgba(0,230,118,0.1)", color: "success.main" }} />}
            {!section.has_ltx && section.has_subtitles && <Chip label="Subs ✓" size="small" sx={{ height: 16, fontSize: "0.58rem", bgcolor: "rgba(0,188,212,0.1)", color: "info.main" }} />}
            {!section.has_ltx && p.includeNarrator && p.narratorText && <Chip label="Narrator" size="small" sx={{ height: 16, fontSize: "0.58rem", bgcolor: "rgba(108,99,255,0.12)", color: "#6C63FF" }} />}
            {!section.has_ltx && p.includeLogo     && <Chip label="Logo"     size="small" sx={{ height: 16, fontSize: "0.58rem", bgcolor: "rgba(255,145,0,0.1)", color: "warning.main" }} />}
            {isShortGenerating && <Chip icon={<CircularProgress size={9} />} label="Generating…" size="small" color="primary" variant="outlined" sx={{ height: 16, fontSize: "0.58rem" }} />}
          </Box>

          {section.has_short ? (
            <Box sx={{ display: "flex", gap: 2 }}>
              <Box sx={{ flex: "0 0 180px" }}>
                <VideoPlayer src={shortUrl} aspectRatio="9/16" color={color} label="9:16" maxWidth={180} />
              </Box>
              <Box sx={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "center" }}>
                <Typography variant="caption" color="text.secondary" display="block">
                  9:16 vertical short ready
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
                {section.has_ltx ? "No shot yet — click Generate (uses LTX clips)" : section.has_voice ? "No shot yet — click Generate" : "Generate voice first"}
              </Typography>
            </Box>
          )}

          <MediaActions
            color={color}
            hasMedia={section.has_short}
            isGenerating={isShortGenerating}
            canGenerate={section.has_voice}
            generateLabel={section.has_ltx ? "shot (LTX)" : "short"}
            downloadUrl={shortUrl}
            downloadName={`${section.label}_shot.mp4`}
            onGenerate={p.onGenerateShort}
            onReplace={p.onReplaceShort}
            onDelete={section.has_short ? p.onDeleteShort : undefined}
          />
        </CardContent>
      </Card>
    </Box>
  );
}

// ── All-sections overview row ─────────────────────────────────────────────────

function SectionOverviewRow({
  section, isClipGen, isShortGen, isLtxGen, onSelect,
}: {
  section: SectionStatus;
  isClipGen: boolean;
  isShortGen: boolean;
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
        {/* LTX status */}
        {section.type !== "agenda" && (
          isLtxGen
            ? <CircularProgress size={11} />
            : section.has_ltx
            ? <Chip label="LTX ✓" size="small" sx={{ height: 14, fontSize: "0.55rem", bgcolor: "rgba(108,99,255,0.15)", color: "#6C63FF" }} />
            : <Chip label="LTX —" size="small" sx={{ height: 14, fontSize: "0.55rem", bgcolor: "rgba(255,255,255,0.04)", color: "text.disabled" }} />
        )}
        {/* Clip status */}
        {isClipGen
          ? <CircularProgress size={11} />
          : section.has_clip
          ? <Chip label="Clip ✓"  size="small" sx={{ height: 14, fontSize: "0.55rem", bgcolor: color + "22", color }} />
          : <Chip label="No clip" size="small" sx={{ height: 14, fontSize: "0.55rem", bgcolor: "rgba(255,255,255,0.04)", color: "text.disabled" }} />}
        {/* Short/shot status */}
        {isShortGen
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

export default function AiNewsClipsPage() {
  const currentProject = useProjectStore((s) => s.currentProject);
  const projectId = currentProject?.id ?? "";
  const queryClient = useQueryClient();

  const [sectionLabel, setSectionLabel] = useState<string | null>(null);
  const [clipGenerating,  setClipGenerating]  = useState<Set<string>>(new Set());
  const [shortGenerating, setShortGenerating] = useState<Set<string>>(new Set());
  const [ltxGenerating,   setLtxGenerating]   = useState<Set<string>>(new Set());
  const [ltxProgress,     setLtxProgress]     = useState<Record<string, string>>({});
  const [ltxErrors,       setLtxErrors]       = useState<Record<string, string>>({});
  const [clipErrors,      setClipErrors]      = useState<Record<string, string>>({});
  const [errorSnack,      setErrorSnack]      = useState<string>("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Short options
  const [includeNarrator, setIncludeNarrator] = useState(true);
  const [narratorText, setNarratorText]       = useState("Deep Dive AI");
  const [includeLogo, setIncludeLogo]         = useState(false);

  // Delete state
  const [deleteAllOpen, setDeleteAllOpen]   = useState(false);
  const [deleteAllLoading, setDeleteAllLoading] = useState(false);
  const [clipDeleteLabel, setClipDeleteLabel]   = useState<string | null>(null);
  const [clipDeleting, setClipDeleting]         = useState(false);
  const [shortDeleteLabel, setShortDeleteLabel] = useState<string | null>(null);
  const [shortDeleting, setShortDeleting]       = useState(false);

  useComfyUIStatus(); // keeps ComfyUIControl's cache warm

  const { data: ltxStatus } = useQuery({
    queryKey: ["ai-news-ltx-status"],
    queryFn:  aiNewsApi.getLtxStatus,
    staleTime: 15_000,
    refetchInterval: 20_000,
  });
  const ltxOnline = ltxStatus?.online ?? false;

  const { data: sections = [], isLoading, error, refetch } = useQuery({
    queryKey: ["ai-news-sections", projectId],
    queryFn:  () => aiNewsApi.getSections(projectId),
    enabled:  !!projectId,
    staleTime: 10_000,
    refetchInterval: (clipGenerating.size > 0 || shortGenerating.size > 0 || ltxGenerating.size > 0) ? 6_000 : false,
  });

  // Detect completed generations via has_clip / has_short / has_ltx flags
  useEffect(() => {
    const doneClips  = [...clipGenerating].filter((l)  => sections.find((s) => s.label === l)?.has_clip);
    const doneShorts = [...shortGenerating].filter((l) => sections.find((s) => s.label === l)?.has_short);
    const doneLtx    = [...ltxGenerating].filter((l)   => sections.find((s) => s.label === l)?.has_ltx);
    if (doneClips.length)  setClipGenerating((p)  => { const n = new Set(p); doneClips.forEach((l)  => n.delete(l)); return n; });
    if (doneShorts.length) setShortGenerating((p) => { const n = new Set(p); doneShorts.forEach((l) => n.delete(l)); return n; });
    if (doneLtx.length)    setLtxGenerating((p)   => { const n = new Set(p); doneLtx.forEach((l)   => n.delete(l)); return n; });
  }, [sections]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  // WS listener — clears generating state when backend finishes (success OR failure).
  // Without this, a failed job leaves clipGenerating/shortGenerating stuck forever
  // because has_clip/has_short never becomes true.
  const wsOnMessage = useCallback(
    (event: string, data: Record<string, unknown>) => {
      const jobType = String(data.job_type ?? "");
      const label   = String(data.section ?? "");

      // Real-time progress from LTX generation
      if (event === "ltx_progress" && jobType.startsWith("section_ltx")) {
        const msg = String(data.message ?? "");
        if (label) setLtxProgress((p) => ({ ...p, [label]: msg }));
        return;
      }

      if (event !== "job_completed" && event !== "job_failed") return;

      if (jobType === "section_clip" && label) {
        setClipGenerating((p) => { const n = new Set(p); n.delete(label); return n; });
        if (event === "job_failed") {
          const errMsg = String((data as Record<string, unknown>).error ?? "Clip generation failed");
          setClipErrors((p) => ({ ...p, [label]: errMsg }));
          setErrorSnack(`Clip failed for '${label}': ${errMsg}`);
        } else {
          setClipErrors((p) => { const n = { ...p }; delete n[label]; return n; });
        }
        refetch();
      }
      if (jobType === "section_short" && label) {
        setShortGenerating((p) => { const n = new Set(p); n.delete(label); return n; });
        refetch();
      }
      if ((jobType === "section_ltx" || jobType === "section_ltx_all") && label) {
        setLtxGenerating((p) => { const n = new Set(p); n.delete(label); return n; });
        setLtxProgress((p) => { const n = { ...p }; delete n[label]; return n; });
        if (event === "job_failed") {
          setLtxErrors((p) => ({ ...p, [label]: String(data.error ?? "LTX generation failed") }));
        } else {
          setLtxErrors((p) => { const n = { ...p }; delete n[label]; return n; });
        }
        refetch();
      }
      if (jobType === "section_ltx_all" && !label) {
        setLtxGenerating(new Set());
        setLtxProgress({});
        refetch();
      }
    },
    [refetch],
  );
  useWebSocket({ projectId, onMessage: wsOnMessage });

  const refreshSections = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["ai-news-sections", projectId] });
  }, [queryClient, projectId]);

  // ── Clip actions ──────────────────────────────────────────────────────────

  const triggerClipRegenerate = useCallback(async (label: string) => {
    if (clipGenerating.has(label)) return;
    setClipErrors((p) => { const n = { ...p }; delete n[label]; return n; });
    setClipGenerating((p) => new Set(p).add(label));
    try {
      await aiNewsApi.regenerateSectionClip(projectId, label);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      const msg = detail ?? (err as Error)?.message ?? "Request failed";
      setClipErrors((p) => ({ ...p, [label]: msg }));
      setErrorSnack(`Clip error (${label}): ${msg}`);
      setClipGenerating((p) => { const n = new Set(p); n.delete(label); return n; });
    }
  }, [projectId, clipGenerating]);

  const handleReplaceClip = useCallback(async (label: string, file: File) => {
    try {
      await aiNewsApi.uploadSectionClip(projectId, label, file);
      refreshSections();
    } catch { /* ignore */ }
  }, [projectId, refreshSections]);

  const handleClipDelete = async () => {
    if (!clipDeleteLabel) return;
    setClipDeleting(true);
    try {
      await aiNewsApi.deleteSectionClip(projectId, clipDeleteLabel);
      refreshSections();
    } finally {
      setClipDeleting(false);
      setClipDeleteLabel(null);
    }
  };

  // ── Short actions ─────────────────────────────────────────────────────────

  const triggerShort = useCallback(async (label: string) => {
    if (shortGenerating.has(label)) return;
    setShortGenerating((p) => new Set(p).add(label));
    try {
      await aiNewsApi.generateSectionShort(projectId, label, {
        narrator_text: includeNarrator && narratorText ? narratorText : undefined,
        logo_path: includeLogo ? "logo.png" : undefined,
      });
    } catch {
      setShortGenerating((p) => { const n = new Set(p); n.delete(label); return n; });
    }
  }, [projectId, shortGenerating, includeNarrator, narratorText, includeLogo]);

  const handleReplaceShort = useCallback(async (label: string, file: File) => {
    try {
      await aiNewsApi.uploadSectionShort(projectId, label, file);
      refreshSections();
    } catch { /* ignore */ }
  }, [projectId, refreshSections]);

  const handleShortDelete = async () => {
    if (!shortDeleteLabel) return;
    setShortDeleting(true);
    try {
      await aiNewsApi.deleteSectionShort(projectId, shortDeleteLabel);
      refreshSections();
    } finally {
      setShortDeleting(false);
      setShortDeleteLabel(null);
    }
  };

  // ── LTX actions ───────────────────────────────────────────────────────────

  const triggerLtx = useCallback(async (label: string) => {
    if (ltxGenerating.has(label)) return;
    setLtxGenerating((p) => new Set(p).add(label));
    setLtxErrors((p) => { const n = { ...p }; delete n[label]; return n; });
    try {
      await aiNewsApi.generateSectionLtx(projectId, label);
    } catch {
      setLtxGenerating((p) => { const n = new Set(p); n.delete(label); return n; });
    }
  }, [projectId, ltxGenerating]);

  const handleLtxDelete = useCallback(async (label: string) => {
    try {
      await aiNewsApi.deleteSectionLtx(projectId, label);
      refreshSections();
    } catch { /* ignore */ }
  }, [projectId, refreshSections]);

  // ── Bulk actions ──────────────────────────────────────────────────────────

  const generateAllClipsAndShorts = () => {
    const pendingClips  = sections.filter((s) => !s.has_clip  && s.has_voice && s.type !== "agenda");
    const pendingShorts = sections.filter((s) => !s.has_short && s.has_voice && s.type !== "agenda");
    pendingClips.forEach((s)  => triggerClipRegenerate(s.label));
    pendingShorts.forEach((s) => triggerShort(s.label));
  };

  const generateAllLtx = async () => {
    const pending = sections.filter((s) => !s.has_ltx && s.has_images && s.type !== "agenda");
    if (pending.length === 0) return;
    pending.forEach((s) => setLtxGenerating((p) => new Set(p).add(s.label)));
    setLtxErrors({});
    try {
      await aiNewsApi.generateAllSectionsLtx(projectId);
    } catch {
      setLtxGenerating(new Set());
    }
  };

  const handleDeleteAll = async () => {
    setDeleteAllLoading(true);
    try {
      await Promise.all([
        aiNewsApi.deleteAllSectionClips(projectId),
        aiNewsApi.deleteAllSectionShorts(projectId),
      ]);
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

  const clipsReady    = sections.filter((s) => s.has_clip).length;
  const shortsReady   = sections.filter((s) => s.has_short).length;
  const ltxReady      = sections.filter((s) => s.has_ltx).length;
  const voiceReady    = sections.filter((s) => s.has_voice && s.type !== "agenda").length;
  const totalSections = sections.length;
  const isAnyGen      = clipGenerating.size > 0 || shortGenerating.size > 0 || ltxGenerating.size > 0;
  const hasAnyMedia   = clipsReady > 0 || shortsReady > 0;

  const selectedSection = sectionLabel
    ? sections.find((s) => s.label === sectionLabel) ?? null
    : null;

  const tabIndex = sectionLabel === null
    ? 0
    : (sections.findIndex((s) => s.label === sectionLabel) + 1) || 0;

  const canGenerate = !isAnyGen &&
    sections.some((s) => s.has_voice && s.type !== "agenda" && (!s.has_clip || !s.has_short));

  return (
    <Box>
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", mb: 2.5 }}>
        <Box>
          <Typography variant="h4" fontWeight={800} gutterBottom>AI News Clips</Typography>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <Chip label="AI NEWS" color="warning" size="small" variant="outlined" sx={{ fontSize: "0.65rem" }} />
            <Typography variant="body2" color="text.secondary">
              {ltxReady}/{totalSections - 1} LTX · {clipsReady}/{totalSections} clips · {shortsReady}/{totalSections} shots
              {isAnyGen && ` · ${clipGenerating.size + shortGenerating.size + ltxGenerating.size} generating…`}
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

          {/* Delete All — clips + shorts */}
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
                onClick={() => { setClipGenerating(new Set()); setShortGenerating(new Set()); setLtxGenerating(new Set()); }}
              >
                Stop
              </Button>
            </Tooltip>
          )}

          {/* Generate all LTX */}
          {sections.some((s) => !s.has_ltx && s.has_images && s.type !== "agenda") && (
            <Tooltip title={!ltxOnline ? "Start ComfyUI first (port 8188)" : "Generate LTX-Video clips for all image-ready sections via ComfyUI"}>
              <span>
                <Button
                  variant="outlined" size="large"
                  startIcon={ltxGenerating.size > 0 ? <CircularProgress size={16} color="inherit" /> : <LtxIcon />}
                  onClick={generateAllLtx}
                  disabled={ltxGenerating.size > 0 || !ltxOnline}
                  sx={{ borderColor: "#6C63FF", color: "#6C63FF", "&:hover": { borderColor: "#5853e6", bgcolor: "rgba(108,99,255,0.05)" } }}
                >
                  {ltxGenerating.size > 0 ? `LTX… (${ltxGenerating.size})` : "Generate All LTX"}
                </Button>
              </span>
            </Tooltip>
          )}

          {/* Generate clips & shots */}
          <Tooltip title={canGenerate ? "Generate clips + 9:16 shots for all voice-ready sections" : "All voice-ready sections already have clips and shots"}>
            <span>
              <Button
                variant="contained" size="large"
                startIcon={clipGenerating.size + shortGenerating.size > 0 ? <CircularProgress size={16} color="inherit" /> : <ShortIcon />}
                onClick={generateAllClipsAndShorts}
                disabled={!canGenerate}
              >
                {clipGenerating.size + shortGenerating.size > 0
                  ? `Generating… (${clipGenerating.size + shortGenerating.size} left)`
                  : (clipsReady > 0 || shortsReady > 0) ? "Generate Missing Clips & Shots" : "Generate All Clips & Shots"}
              </Button>
            </span>
          </Tooltip>
        </Box>
      </Box>

      {/* ── Stats row ──────────────────────────────────────────────────────── */}
      <Grid container spacing={1.5} sx={{ mb: 2.5 }}>
        {[
          { label: "Total Sections", value: totalSections,     color: "#6C63FF" },
          { label: "LTX Ready",      value: ltxReady,          color: "#9C7FFF" },
          { label: "Clips Ready",    value: clipsReady,        color: "#FF9100" },
          { label: "Shots Ready",    value: shortsReady,       color: "#00E676" },
        ].map(({ label, value, color }) => (
          <Grid item xs={3} key={label}>
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
            const isGen = clipGenerating.has(sec.label) || shortGenerating.has(sec.label) || ltxGenerating.has(sec.label);
            const allDone = sec.has_clip && sec.has_short && (sec.type === "agenda" || sec.has_ltx);
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
                      : sec.has_ltx
                      ? <LtxIcon sx={{ fontSize: 10, color: "#6C63FF" }} />
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
                      label="Clips auto-generated during Video Render · Shorts generated here or auto during render"
                      size="small"
                      sx={{ bgcolor: "rgba(255,255,255,0.04)", color: "text.secondary", fontSize: "0.62rem", height: 20 }}
                    />
                  </Box>
                  {sections.length === 0 ? (
                    <Box sx={{ py: 6, textAlign: "center", color: "text.disabled", border: "1px dashed rgba(255,255,255,0.06)", borderRadius: 2 }}>
                      <ClipIcon sx={{ fontSize: 40, mb: 1 }} />
                      <Typography variant="body2">No sections found</Typography>
                    </Box>
                  ) : (
                    <Box sx={{ display: "flex", flexDirection: "column", gap: 0.75 }}>
                      {sections.map((sec) => (
                        <SectionOverviewRow
                          key={sec.label}
                          section={sec}
                          isClipGen={clipGenerating.has(sec.label)}
                          isShortGen={shortGenerating.has(sec.label)}
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
                  isClipGenerating={clipGenerating.has(sectionLabel)}
                  isShortGenerating={shortGenerating.has(sectionLabel)}
                  isLtxGenerating={ltxGenerating.has(sectionLabel)}
                  comfyOnline={ltxOnline}
                  includeNarrator={includeNarrator}
                  narratorText={narratorText}
                  includeLogo={includeLogo}
                  ltxProgressMsg={ltxProgress[sectionLabel]}
                  ltxError={ltxErrors[sectionLabel]}
                  clipError={clipErrors[sectionLabel]}
                  onGenerateClip={() => triggerClipRegenerate(sectionLabel)}
                  onReplaceClip={(f) => handleReplaceClip(sectionLabel, f)}
                  onDeleteClip={() => setClipDeleteLabel(sectionLabel)}
                  onGenerateShort={() => triggerShort(sectionLabel)}
                  onReplaceShort={(f) => handleReplaceShort(sectionLabel, f)}
                  onDeleteShort={() => setShortDeleteLabel(sectionLabel)}
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
                        { label: "Voice",     done: selectedSection.has_voice     },
                        { label: "Subtitles", done: selectedSection.has_subtitles },
                        { label: "LTX",       done: selectedSection.has_ltx       },
                        { label: "Clip",      done: selectedSection.has_clip      },
                        { label: "Shot",      done: selectedSection.has_short     },
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

                    {/* Short options */}
                    <Typography variant="caption" fontWeight={700} color="text.secondary"
                      sx={{ textTransform: "uppercase", fontSize: "0.62rem", display: "block", mb: 0.75 }}>
                      Short Options
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
                              variant={selectedSection.has_ltx ? "outlined" : "contained"}
                              startIcon={ltxGenerating.has(sectionLabel) ? <CircularProgress size={12} color="inherit" /> : <LtxIcon />}
                              onClick={() => triggerLtx(sectionLabel)}
                              disabled={ltxGenerating.has(sectionLabel) || !selectedSection.has_images || !ltxOnline}
                              sx={!selectedSection.has_ltx ? { bgcolor: "#6C63FF", "&:hover": { bgcolor: "#5853e6" } } : {}}
                            >
                              {ltxGenerating.has(sectionLabel) ? "Generating LTX…" : selectedSection.has_ltx ? "Re-gen LTX" : "Generate LTX"}
                            </Button>
                          </span>
                        </Tooltip>
                      )}
                      <Button fullWidth size="small" variant="outlined"
                        startIcon={clipGenerating.has(sectionLabel) ? <CircularProgress size={12} color="inherit" /> : <RegenerateIcon />}
                        onClick={() => triggerClipRegenerate(sectionLabel)}
                        disabled={clipGenerating.has(sectionLabel) || (selectedSection.type !== "agenda" && !selectedSection.has_voice)}
                      >
                        {clipGenerating.has(sectionLabel) ? "Re-generating clip…" : selectedSection.has_clip ? "Re-gen Clip" : "Generate Clip"}
                      </Button>
                      <Button fullWidth size="small"
                        variant={selectedSection.has_short ? "outlined" : "contained"}
                        startIcon={shortGenerating.has(sectionLabel) ? <CircularProgress size={12} color="inherit" /> : <ShortIcon />}
                        onClick={() => triggerShort(sectionLabel)}
                        disabled={shortGenerating.has(sectionLabel) || !selectedSection.has_voice}
                      >
                        {shortGenerating.has(sectionLabel) ? "Generating shot…" : selectedSection.has_short ? "Re-gen Shot" : "Generate Shot"}
                      </Button>
                    </Box>
                  </>
                ) : (
                  <Typography variant="caption" color="text.disabled">
                    Select a section tab to view clips and generate shorts
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
                    const isGen = clipGenerating.has(sec.label) || shortGenerating.has(sec.label) || ltxGenerating.has(sec.label);
                    const allDone = sec.has_clip && sec.has_short && (sec.type === "agenda" || sec.has_ltx);
                    return (
                      <Box
                        key={sec.label}
                        onClick={() => setSectionLabel(sec.label)}
                        sx={{
                          display: "flex", alignItems: "center", gap: 0.75,
                          cursor: "pointer", borderRadius: 1,
                          px: 0.5, py: 0.25,
                          bgcolor: sectionLabel === sec.label ? "rgba(108,99,255,0.08)" : "transparent",
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
                          {sec.has_ltx   && <Chip label="L" size="small" sx={{ height: 12, fontSize: "0.5rem", minWidth: 16, bgcolor: "rgba(108,99,255,0.15)", color: "#6C63FF" }} />}
                          {sec.has_clip  && <Chip label="C" size="small" sx={{ height: 12, fontSize: "0.5rem", minWidth: 16, bgcolor: sectionColor(sec.type) + "22", color: sectionColor(sec.type) }} />}
                          {sec.has_short && <Chip label="S" size="small" sx={{ height: 12, fontSize: "0.5rem", minWidth: 16, bgcolor: "rgba(0,230,118,0.1)", color: "success.main" }} />}
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
                  <LtxIcon sx={{ fontSize: 13, mr: 0.5, verticalAlign: "middle", color: "#6C63FF" }} />
                  New Architecture
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block">
                  <strong>LTX Video</strong> animates each scene image via ComfyUI. This is the base video for clips and shots.
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
                  <strong>Clips (16:9)</strong> = LTX video + narration + subtitles. Used for the final assembled video.
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
                  <strong>Shots (9:16)</strong> = LTX video + narration only. Clean — no subtitles, no narrator overlay.
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
                  Use <strong>Replace</strong> to upload a custom MP4 for any clip or shot.
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}

      {/* ── Delete dialogs ───────────────────────────────────────────────────── */}
      <DeleteConfirmDialog
        open={deleteAllOpen}
        title="Delete All Clips & Shorts"
        description={`Delete all ${clipsReady} clip${clipsReady !== 1 ? "s" : ""} and ${shortsReady} short${shortsReady !== 1 ? "s" : ""}? You will need to re-generate them.`}
        loading={deleteAllLoading}
        onConfirm={handleDeleteAll}
        onCancel={() => setDeleteAllOpen(false)}
      />
      <DeleteConfirmDialog
        open={!!clipDeleteLabel}
        title={`Delete Clip — ${sections.find((s) => s.label === clipDeleteLabel)?.title ?? clipDeleteLabel ?? ""}`}
        description="Delete this section's 16:9 clip? You can re-generate it at any time."
        loading={clipDeleting}
        onConfirm={handleClipDelete}
        onCancel={() => setClipDeleteLabel(null)}
      />
      <DeleteConfirmDialog
        open={!!shortDeleteLabel}
        title={`Delete Short — ${sections.find((s) => s.label === shortDeleteLabel)?.title ?? shortDeleteLabel ?? ""}`}
        description="Delete this section's 9:16 short? You can re-generate it at any time."
        loading={shortDeleting}
        onConfirm={handleShortDelete}
        onCancel={() => setShortDeleteLabel(null)}
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
