import React, { useState, useMemo, useRef, useCallback, useEffect } from "react";
import {
  Box,
  Typography,
  Card,
  CardContent,
  Button,
  Grid,
  LinearProgress,
  ButtonGroup,
  Chip,
  Alert,
  Skeleton,
  CircularProgress,
  Tooltip,
  Divider,
  TextField,
  InputAdornment,
  IconButton,
} from "@mui/material";
import {
  Subtitles as SubtitleIcon,
  FileDownload as DownloadIcon,
  Search as SearchIcon,
  CheckCircle as DoneIcon,
  HourglassEmpty as PendingIcon,
  Psychology as WhisperIcon,
  AccessTime as TimeIcon,
  TextSnippet as SrtIcon,
  DeleteForever as DeleteIcon,
  Refresh as RegenerateIcon,
} from "@mui/icons-material";
import { useProjectStore } from "../store";
import { useTriggerJob } from "../hooks/useJobs";
import {
  useSubtitleStatus,
  useSubtitleSegments,
  useSrtText,
  useWhisperStatus,
  SUBTITLE_KEYS,
} from "../hooks/useSubtitles";
import { subtitlesApi, SubtitleSegment } from "../api/subtitles";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { aiNewsApi } from "../api/aiNews";
import ProgressCard from "../components/common/ProgressCard";
import DeleteConfirmDialog from "../components/common/DeleteConfirmDialog";
import AiNewsSectionTabs from "../components/ai-news/AiNewsSectionTabs";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function formatTime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  const ms = Math.round((seconds % 1) * 1000);
  if (h > 0) return `${h}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")},${ms.toString().padStart(3, "0")}`;
  return `${m}:${s.toString().padStart(2, "0")},${ms.toString().padStart(3, "0")}`;
}

function formatDuration(seconds: number): string {
  if (seconds <= 0) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

// ---------------------------------------------------------------------------
// Whisper status chip
// ---------------------------------------------------------------------------
function WhisperStatusChip() {
  const { data, isLoading } = useWhisperStatus();

  if (isLoading) return <Chip label="Checking Whisper…" size="small" sx={{ height: 22 }} />;

  const ok = data?.available ?? false;
  const label = ok
    ? `Whisper · ${data?.configured_model ?? "base"} · ${data?.device ?? "cpu"}`
    : "Whisper Not Installed";

  return (
    <Tooltip
      title={
        ok
          ? `openai-whisper installed · model: ${data?.configured_model} · device: ${data?.device}`
          : data?.error ?? "Run: pip install openai-whisper"
      }
    >
      <Chip
        icon={<WhisperIcon sx={{ fontSize: "12px !important" }} />}
        label={label}
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
// Timeline visualisation
// ---------------------------------------------------------------------------
interface TimelineProps {
  segments: SubtitleSegment[];
  totalDuration: number;
  activeId: number | null;
  onSelect: (seg: SubtitleSegment) => void;
}

function Timeline({ segments, totalDuration, activeId, onSelect }: TimelineProps) {
  const dur = totalDuration || (segments.at(-1)?.end ?? 60);

  return (
    <Box>
      {/* Time ruler */}
      <Box sx={{ position: "relative", height: 16, mb: 0.5 }}>
        {[0, 25, 50, 75, 100].map((pct) => (
          <Typography
            key={pct}
            variant="caption"
            sx={{
              position: "absolute",
              left: `${pct}%`,
              transform: "translateX(-50%)",
              color: "text.disabled",
              fontSize: "0.6rem",
            }}
          >
            {formatDuration((dur * pct) / 100)}
          </Typography>
        ))}
      </Box>

      {/* Track */}
      <Box
        sx={{
          position: "relative",
          height: 28,
          bgcolor: "rgba(255,255,255,0.03)",
          borderRadius: 1,
          overflow: "hidden",
          border: "1px solid rgba(255,255,255,0.06)",
          cursor: "pointer",
        }}
      >
        {segments.map((seg) => {
          const left = (seg.start / dur) * 100;
          const width = Math.max(0.3, ((seg.end - seg.start) / dur) * 100);
          const isActive = seg.id === activeId;
          return (
            <Tooltip key={seg.id} title={`#${seg.id}: ${seg.text.slice(0, 60)}`} placement="top">
              <Box
                onClick={() => onSelect(seg)}
                sx={{
                  position: "absolute",
                  left: `${left}%`,
                  width: `${width}%`,
                  height: "100%",
                  bgcolor: isActive ? "primary.main" : "rgba(108,99,255,0.45)",
                  borderRight: "1px solid rgba(0,0,0,0.3)",
                  transition: "background-color 0.1s",
                  "&:hover": { bgcolor: "primary.light" },
                }}
              />
            </Tooltip>
          );
        })}
      </Box>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Segment row
// ---------------------------------------------------------------------------
interface SegmentRowProps {
  segment: SubtitleSegment;
  isActive: boolean;
  onClick: () => void;
}

function SegmentRow({ segment, isActive, onClick }: SegmentRowProps) {
  return (
    <Box
      onClick={onClick}
      sx={{
        display: "flex",
        gap: 1.5,
        py: 0.75,
        px: 1,
        borderRadius: 1.5,
        cursor: "pointer",
        border: `1px solid ${isActive ? "rgba(108,99,255,0.4)" : "transparent"}`,
        bgcolor: isActive ? "rgba(108,99,255,0.08)" : "transparent",
        "&:hover": { bgcolor: "rgba(255,255,255,0.03)" },
        transition: "all 0.1s ease",
      }}
    >
      {/* Index */}
      <Typography
        variant="caption"
        sx={{
          minWidth: 24,
          color: "text.disabled",
          fontFamily: "monospace",
          flexShrink: 0,
          lineHeight: 1.6,
        }}
      >
        {segment.id}
      </Typography>

      {/* Timestamps */}
      <Box sx={{ flexShrink: 0 }}>
        <Typography variant="caption" sx={{ fontFamily: "monospace", color: "primary.light", fontSize: "0.68rem", display: "block" }}>
          {formatTime(segment.start)}
        </Typography>
        <Typography variant="caption" sx={{ fontFamily: "monospace", color: "text.disabled", fontSize: "0.68rem", display: "block" }}>
          {formatTime(segment.end)}
        </Typography>
      </Box>

      {/* Text */}
      <Typography
        variant="body2"
        sx={{ flex: 1, lineHeight: 1.5, color: isActive ? "text.primary" : "text.secondary" }}
      >
        {segment.text}
      </Typography>

      {/* Duration chip */}
      <Chip
        label={`${(segment.end - segment.start).toFixed(1)}s`}
        size="small"
        sx={{ height: 18, fontSize: "0.6rem", flexShrink: 0, bgcolor: "rgba(255,255,255,0.05)", alignSelf: "center" }}
      />
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function SubtitlePage() {
  const currentProject = useProjectStore((s) => s.currentProject);
  const generationProgress = useProjectStore((s) => s.generationProgress);
  const triggerJob = useTriggerJob();

  const { data: statusData, isLoading: statusLoading } = useSubtitleStatus(currentProject?.id);
  const { data: segmentsData, isLoading: segsLoading } = useSubtitleSegments(currentProject?.id);
  const { data: srtText, isLoading: srtLoading } = useSrtText(currentProject?.id);

  const isAiNews = currentProject?.project_type === "ai_news";
  const queryClient = useQueryClient();
  const [searchQuery, setSearchQuery] = useState("");
  const [activeSegId, setActiveSegId] = useState<number | null>(null);
  const [view, setView] = useState<"segments" | "raw">("segments");
  const [isGenerating, setIsGenerating] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const [sectionLabel, setSectionLabel] = useState<string | null>(null);
  const sectionsContentQuery = useQuery({
    queryKey: ["ai-news-sections-content", currentProject?.id ?? ""],
    queryFn: () => aiNewsApi.getSectionsContent(currentProject!.id),
    enabled: isAiNews && !!currentProject?.id,
    staleTime: 0,
  });
  const sectionsContent = sectionsContentQuery.data ?? [];
  const selectedSection = sectionLabel ? sectionsContent.find((s) => s.label === sectionLabel) : null;

  const [sectionSubGenerating, setSectionSubGenerating] = useState<Set<string>>(new Set());
  const sectionSubPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [sectionSubDeleteOpen, setSectionSubDeleteOpen] = useState(false);
  const [sectionSubDeleting, setSectionSubDeleting] = useState(false);
  const [allSectionSubDeleteOpen, setAllSectionSubDeleteOpen] = useState(false);
  const [allSectionSubDeleting, setAllSectionSubDeleting] = useState(false);

  useEffect(() => {
    return () => { if (sectionSubPollRef.current) clearInterval(sectionSubPollRef.current); };
  }, []);

  const subtitleProgress = generationProgress.subtitles;
  const isRunning = subtitleProgress.status === "running";
  const isAnySectionSubGen = sectionSubGenerating.size > 0;
  const segments = segmentsData?.segments ?? [];
  const totalDuration = statusData?.total_duration ?? 0;

  const filteredSegments = useMemo(() => {
    if (!searchQuery.trim()) return segments;
    const q = searchQuery.toLowerCase();
    return segments.filter((s) => s.text.toLowerCase().includes(q));
  }, [segments, searchQuery]);

  const activeSegment = useMemo(
    () => segments.find((s) => s.id === activeSegId) ?? null,
    [segments, activeSegId]
  );

  // ── AI News subtitle functions ─────────────────────────────────────────────

  const generateAllSectionSubtitles = async () => {
    if (!currentProject) return;
    let labels: string[];
    try {
      const res = await aiNewsApi.generateMissingSectionsSubtitles(currentProject.id);
      if (res.status === "nothing_to_do" || !res.labels.length) return;
      labels = res.labels;
    } catch (err) {
      console.error("AI News subtitle generation failed:", err);
      return;
    }
    setSectionSubGenerating(new Set(labels));
    if (sectionSubPollRef.current) clearInterval(sectionSubPollRef.current);
    sectionSubPollRef.current = setInterval(() => {
      sectionsContentQuery.refetch().then(({ data }) => {
        if (!data) return;
        setSectionSubGenerating((prev) => {
          const next = new Set(prev);
          for (const lbl of [...prev]) {
            const sec = data.find((s) => s.label === lbl);
            if (sec?.subtitle_srt !== null && sec?.subtitle_srt !== undefined) next.delete(lbl);
          }
          if (next.size === 0 && sectionSubPollRef.current) {
            clearInterval(sectionSubPollRef.current);
            sectionSubPollRef.current = null;
          }
          return next;
        });
      });
    }, 6000);
  };

  const triggerSectionSubtitles = useCallback(async (label: string) => {
    if (!currentProject || sectionSubGenerating.has(label)) return;
    setSectionSubGenerating((prev) => new Set(prev).add(label));
    try {
      await aiNewsApi.generateSectionSubtitles(currentProject.id, label);
    } catch (err) {
      console.error(`Subtitle gen failed for ${label}:`, err);
      setSectionSubGenerating((prev) => { const n = new Set(prev); n.delete(label); return n; });
      return;
    }
    const poll = setInterval(() => {
      sectionsContentQuery.refetch().then(({ data }) => {
        const sec = data?.find((s) => s.label === label);
        if (sec?.subtitle_srt !== null && sec?.subtitle_srt !== undefined) {
          setSectionSubGenerating((prev) => { const n = new Set(prev); n.delete(label); return n; });
          clearInterval(poll);
        }
      });
    }, 5000);
    setTimeout(() => {
      clearInterval(poll);
      setSectionSubGenerating((prev) => { const n = new Set(prev); n.delete(label); return n; });
    }, 600_000);
  }, [currentProject, sectionSubGenerating, sectionsContentQuery]);

  const reGenerateAllSectionSubtitles = async () => {
    if (!currentProject || !sectionsContent.length) return;
    try {
      await aiNewsApi.deleteAllSectionSubtitles(currentProject.id);
    } catch (err) {
      console.error("Re-gen subtitles: delete all failed:", err);
      return;
    }
    let labels: string[];
    try {
      const res = await aiNewsApi.generateMissingSectionsSubtitles(currentProject.id);
      if (!res.labels || !res.labels.length) return;
      labels = res.labels;
    } catch (err) {
      console.error("Re-gen subtitles: generate failed:", err);
      sectionsContentQuery.refetch();
      return;
    }
    setSectionSubGenerating(new Set(labels));
    if (sectionSubPollRef.current) clearInterval(sectionSubPollRef.current);
    sectionSubPollRef.current = setInterval(() => {
      sectionsContentQuery.refetch().then(({ data }) => {
        if (!data) return;
        setSectionSubGenerating((prev) => {
          const next = new Set(prev);
          for (const lbl of [...prev]) {
            const sec = data.find((s) => s.label === lbl);
            if (sec?.subtitle_srt !== null && sec?.subtitle_srt !== undefined) next.delete(lbl);
          }
          if (next.size === 0 && sectionSubPollRef.current) {
            clearInterval(sectionSubPollRef.current);
            sectionSubPollRef.current = null;
          }
          return next;
        });
      });
    }, 6000);
  };

  const handleSectionSubDelete = async () => {
    if (!currentProject || !sectionLabel) return;
    setSectionSubDeleting(true);
    try {
      await aiNewsApi.deleteSectionSubtitles(currentProject.id, sectionLabel);
      sectionsContentQuery.refetch();
    } catch (err) {
      console.error("Failed to delete section subtitles:", err);
    } finally {
      setSectionSubDeleting(false);
      setSectionSubDeleteOpen(false);
    }
  };

  const handleAllSectionSubDelete = async () => {
    if (!currentProject) return;
    setAllSectionSubDeleting(true);
    try {
      await aiNewsApi.deleteAllSectionSubtitles(currentProject.id);
      sectionsContentQuery.refetch();
    } catch (err) {
      console.error("Failed to delete all section subtitles:", err);
    } finally {
      setAllSectionSubDeleting(false);
      setAllSectionSubDeleteOpen(false);
    }
  };

  // ── Standard subtitle functions ────────────────────────────────────────────

  const handleDelete = async () => {
    if (!currentProject) return;
    setDeleting(true);
    try {
      await subtitlesApi.deleteOutputs(currentProject.id);
      queryClient.invalidateQueries({ queryKey: SUBTITLE_KEYS.status(currentProject.id) });
      queryClient.invalidateQueries({ queryKey: SUBTITLE_KEYS.segments(currentProject.id) });
      queryClient.invalidateQueries({ queryKey: SUBTITLE_KEYS.srt(currentProject.id) });
    } catch (err) {
      console.error("Failed to delete subtitles:", err);
    } finally {
      setDeleting(false);
      setDeleteOpen(false);
    }
  };

  const handleDownloadSrt = () => {
    if (!currentProject) return;
    window.location.href = subtitlesApi.getSrtDownloadUrl(currentProject.id);
  };

  const handleDownloadVtt = () => {
    if (!currentProject) return;
    window.location.href = subtitlesApi.getVttDownloadUrl(currentProject.id);
  };

  if (!currentProject) {
    return (
      <Box sx={{ textAlign: "center", py: 8 }}>
        <Typography color="text.secondary">No project selected.</Typography>
      </Box>
    );
  }

  const hasSubtitles = statusData?.status === "ready";

  // ── AI News layout ──────────────────────────────────────────────────────────
  if (isAiNews) {
    const withSubs = sectionsContent.filter((s) => s.subtitle_srt !== null).length;
    const allSectionsHaveSubtitles = sectionsContent.length > 0 && withSubs === sectionsContent.length;
    const canGenerate = !isAnySectionSubGen && sectionsContent.some((s) => s.has_narration && s.subtitle_srt === null);
    const viewLabel = sectionLabel ?? "";

    return (
      <Box>
        {/* ── Header ─────────────────────────────────────────────────────── */}
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", mb: 2.5 }}>
          <Box>
            <Typography variant="h4" fontWeight={800} gutterBottom>Subtitle Generation</Typography>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
              <Chip label="AI NEWS" color="warning" size="small" variant="outlined" sx={{ fontSize: "0.65rem" }} />
              <WhisperStatusChip />
              <Typography variant="body2" color="text.secondary">
                {withSubs}/{sectionsContent.length} sections with subtitles
                {isAnySectionSubGen && ` · transcribing ${sectionSubGenerating.size} section(s)…`}
              </Typography>
            </Box>
          </Box>
          <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
            {withSubs > 0 && (
              <Button
                variant="outlined"
                color="error"
                startIcon={<DeleteIcon />}
                onClick={() => setAllSectionSubDeleteOpen(true)}
                disabled={isAnySectionSubGen}
                size="large"
              >
                Delete All
              </Button>
            )}
            {allSectionsHaveSubtitles && !isAnySectionSubGen && (
              <Tooltip title="Delete all section subtitles and re-transcribe from scratch">
                <Button
                  variant="outlined"
                  startIcon={<RegenerateIcon />}
                  onClick={reGenerateAllSectionSubtitles}
                  size="large"
                >
                  Re-Generate All
                </Button>
              </Tooltip>
            )}
            <Tooltip title={canGenerate ? "Generate subtitles for all sections missing them" : "All sections have subtitles or no audio found"}>
              <span>
                <Button
                  variant="contained"
                  startIcon={isAnySectionSubGen ? <CircularProgress size={16} color="inherit" /> : <SubtitleIcon />}
                  onClick={generateAllSectionSubtitles}
                  disabled={!canGenerate}
                  size="large"
                >
                  {isAnySectionSubGen
                    ? `Transcribing… (${sectionSubGenerating.size} left)`
                    : withSubs > 0 ? "Generate Missing" : "Generate All Sections"}
                </Button>
              </span>
            </Tooltip>
          </Box>
        </Box>

        {/* ── Section progress bar ─────────────────────────────────────────── */}
        {sectionSubGenerating.has(viewLabel) && (
          <Box sx={{ mb: 2 }}>
            <LinearProgress sx={{ borderRadius: 1, height: 6 }} />
            <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
              Transcribing subtitles for {selectedSection?.title ?? viewLabel}…
            </Typography>
          </Box>
        )}

        {/* ── Stats row ────────────────────────────────────────────────────── */}
        <Grid container spacing={1.5} sx={{ mb: 2 }}>
          {[
            { label: "Total Sections", value: sectionsContent.length, color: "#6C63FF" },
            { label: "With Subtitles", value: withSubs, color: "#00E676" },
            { label: "Remaining", value: Math.max(0, sectionsContent.length - withSubs), color: "#9090A8" },
          ].map(({ label: lbl, value, color }) => (
            <Grid item xs={4} key={lbl}>
              <Card variant="outlined" sx={{ textAlign: "center", py: 1, borderColor: "rgba(255,255,255,0.06)" }}>
                <Typography variant="h6" fontWeight={800} sx={{ color, lineHeight: 1 }}>{value}</Typography>
                <Typography variant="caption" color="text.disabled">{lbl}</Typography>
              </Card>
            </Grid>
          ))}
        </Grid>

        {/* ── Section tabs ─────────────────────────────────────────────────── */}
        <AiNewsSectionTabs
          sections={sectionsContent}
          selected={sectionLabel}
          onSelect={(lbl) => setSectionLabel(lbl)}
        />

        {/* ── Content + Right panel ─────────────────────────────────────────── */}
        <Grid container spacing={2}>
          {/* Left: SRT view */}
          <Grid item xs={12} md={8}>
            <Card>
              <CardContent sx={{ p: 2 }}>
                {/* Card header */}
                <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1.5 }}>
                  <Typography variant="subtitle1" fontWeight={700}>
                    {sectionLabel
                      ? `${selectedSection?.title ?? sectionLabel} — Subtitles`
                      : "All Sections — Subtitles"}
                  </Typography>
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                    {sectionSubGenerating.has(viewLabel) && (
                      <Chip
                        icon={<CircularProgress size={10} />}
                        label="Transcribing…"
                        size="small"
                        color="primary"
                        variant="outlined"
                        sx={{ fontSize: "0.65rem" }}
                      />
                    )}
                    {sectionLabel && selectedSection?.subtitle_srt !== null && (
                      <>
                        <Chip label="SRT Ready" size="small" color="success" sx={{ height: 20, fontSize: "0.7rem" }} />
                        <Tooltip title={`Delete subtitles for ${selectedSection?.title ?? sectionLabel}`}>
                          <IconButton
                            size="small"
                            color="error"
                            onClick={() => setSectionSubDeleteOpen(true)}
                            sx={{ opacity: 0.7, "&:hover": { opacity: 1 } }}
                          >
                            <DeleteIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      </>
                    )}
                    {sectionLabel && selectedSection?.subtitle_srt === null && (
                      <Chip label="Not Generated" size="small" color="default" sx={{ height: 20, fontSize: "0.7rem" }} />
                    )}
                  </Box>
                </Box>

                {sectionLabel !== null ? (
                  // ── Per-section view ──
                  !selectedSection?.subtitle_srt ? (
                    <Box sx={{ py: 6, textAlign: "center", color: "text.disabled", border: "1px dashed rgba(255,255,255,0.06)", borderRadius: 2 }}>
                      <SubtitleIcon sx={{ fontSize: 40, mb: 1 }} />
                      <Typography variant="body2">
                        {!selectedSection?.has_narration
                          ? "No audio — generate voice for this section first"
                          : "No subtitles yet — click Generate"}
                      </Typography>
                      {selectedSection?.has_narration && !sectionSubGenerating.has(viewLabel) && (
                        <Box sx={{ mt: 2 }}>
                          <Button
                            variant="outlined"
                            startIcon={<SubtitleIcon />}
                            onClick={() => triggerSectionSubtitles(viewLabel)}
                          >
                            Generate Subtitles for This Section
                          </Button>
                        </Box>
                      )}
                    </Box>
                  ) : (
                    <Box
                      component="pre"
                      sx={{
                        bgcolor: "#080810",
                        border: "1px solid rgba(255,255,255,0.06)",
                        borderRadius: 2,
                        p: 2,
                        maxHeight: 480,
                        overflow: "auto",
                        fontFamily: '"JetBrains Mono", "Fira Code", monospace',
                        fontSize: "0.75rem",
                        color: "#E8E8F0",
                        lineHeight: 1.9,
                        whiteSpace: "pre-wrap",
                        m: 0,
                      }}
                    >
                      {selectedSection.subtitle_srt}
                    </Box>
                  )
                ) : (
                  // ── "All" overview tab ──
                  withSubs === 0 ? (
                    <Box sx={{ py: 6, textAlign: "center", color: "text.disabled", border: "1px dashed rgba(255,255,255,0.06)", borderRadius: 2 }}>
                      <SubtitleIcon sx={{ fontSize: 40, mb: 1 }} />
                      <Typography variant="body2">No subtitles yet — click "Generate All Sections"</Typography>
                    </Box>
                  ) : (
                    <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
                      {sectionsContent.map((sec) => (
                        <Box
                          key={sec.label}
                          onClick={() => setSectionLabel(sec.label)}
                          sx={{
                            display: "flex",
                            alignItems: "center",
                            gap: 1,
                            p: 1,
                            borderRadius: 1.5,
                            cursor: "pointer",
                            border: "1px solid rgba(255,255,255,0.05)",
                            "&:hover": { bgcolor: "rgba(255,255,255,0.03)" },
                          }}
                        >
                          {sectionSubGenerating.has(sec.label)
                            ? <CircularProgress size={14} sx={{ flexShrink: 0 }} />
                            : sec.subtitle_srt !== null
                            ? <DoneIcon sx={{ fontSize: 14, color: "success.main", flexShrink: 0 }} />
                            : <PendingIcon sx={{ fontSize: 14, color: "rgba(255,255,255,0.18)", flexShrink: 0 }} />}
                          <Typography variant="body2" sx={{ flex: 1 }} noWrap>{sec.title}</Typography>
                          {sec.subtitle_srt !== null && (
                            <Chip label="SRT" size="small" color="success" variant="outlined" sx={{ height: 16, fontSize: "0.6rem" }} />
                          )}
                        </Box>
                      ))}
                    </Box>
                  )
                )}
              </CardContent>
            </Card>
          </Grid>

          {/* Right: section action + progress */}
          <Grid item xs={12} md={4}>
            <Card sx={{ position: "sticky", top: 80, mb: 2 }}>
              <CardContent sx={{ p: 2 }}>
                <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1.5 }}>
                  {sectionLabel ? selectedSection?.title ?? sectionLabel : "Select a Section"}
                </Typography>

                {sectionLabel ? (
                  <>
                    <Box sx={{ mb: 1.5 }}>
                      <LinearProgress
                        variant="determinate"
                        value={selectedSection?.subtitle_srt !== null ? 100 : 0}
                        sx={{ height: 6, borderRadius: 1, mb: 0.5 }}
                      />
                      <Typography variant="caption" color="text.secondary">
                        {selectedSection?.subtitle_srt !== null ? "Subtitles ready" : "Not generated yet"}
                      </Typography>
                    </Box>
                    {selectedSection?.has_narration ? (
                      <Button
                        fullWidth
                        variant={selectedSection.subtitle_srt !== null ? "outlined" : "contained"}
                        startIcon={sectionSubGenerating.has(viewLabel) ? <CircularProgress size={16} color="inherit" /> : <SubtitleIcon />}
                        onClick={() => triggerSectionSubtitles(viewLabel)}
                        disabled={sectionSubGenerating.has(viewLabel)}
                        size="small"
                      >
                        {sectionSubGenerating.has(viewLabel)
                          ? "Transcribing…"
                          : selectedSection.subtitle_srt !== null
                          ? "Re-generate"
                          : "Generate This Section"}
                      </Button>
                    ) : (
                      <Typography variant="caption" color="text.disabled">
                        No audio — generate voice first
                      </Typography>
                    )}
                  </>
                ) : (
                  <Typography variant="caption" color="text.disabled">
                    Select a section tab to generate subtitles
                  </Typography>
                )}
              </CardContent>
            </Card>

            {/* Section progress summary */}
            <Card>
              <CardContent sx={{ p: 2, "&:last-child": { pb: 2 } }}>
                <Typography
                  variant="caption"
                  fontWeight={700}
                  color="text.secondary"
                  sx={{ textTransform: "uppercase", fontSize: "0.65rem", letterSpacing: 0.5, display: "block", mb: 1 }}
                >
                  Section Progress
                </Typography>
                <Box sx={{ display: "flex", flexDirection: "column", gap: 0.75 }}>
                  {sectionsContent.map((sec) => (
                    <Box key={sec.label} sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
                      {sectionSubGenerating.has(sec.label)
                        ? <CircularProgress size={12} sx={{ flexShrink: 0 }} />
                        : sec.subtitle_srt !== null
                        ? <DoneIcon sx={{ fontSize: 12, color: "success.main", flexShrink: 0 }} />
                        : <PendingIcon sx={{ fontSize: 12, color: "rgba(255,255,255,0.18)", flexShrink: 0 }} />}
                      <Typography
                        variant="caption"
                        sx={{
                          flex: 1,
                          fontSize: "0.68rem",
                          color: sec.subtitle_srt !== null ? "text.primary" : "text.disabled",
                        }}
                        noWrap
                      >
                        {sec.title}
                      </Typography>
                      {sec.subtitle_srt !== null && (
                        <Typography variant="caption" color="success.main" sx={{ fontSize: "0.62rem", flexShrink: 0 }}>
                          ✓
                        </Typography>
                      )}
                    </Box>
                  ))}
                </Box>
              </CardContent>
            </Card>

            {/* Whisper info */}
            <Card sx={{ mt: 2 }}>
              <CardContent sx={{ p: 2 }}>
                <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1 }}>
                  <WhisperIcon sx={{ fontSize: 14, mr: 0.5, verticalAlign: "middle" }} />
                  Whisper Setup
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
                  Install: <code>pip install openai-whisper</code>
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block">
                  Configure the model and device in <strong>Settings → Whisper</strong>.
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        </Grid>

        {/* Delete confirm dialogs */}
        <DeleteConfirmDialog
          open={sectionSubDeleteOpen}
          title={`Delete Subtitles — ${selectedSection?.title ?? sectionLabel ?? ""}`}
          description="Delete the SRT file for this section? You will need to re-transcribe to get them back."
          loading={sectionSubDeleting}
          onConfirm={handleSectionSubDelete}
          onCancel={() => setSectionSubDeleteOpen(false)}
        />
        <DeleteConfirmDialog
          open={allSectionSubDeleteOpen}
          title="Delete All Section Subtitles"
          description={`Delete all generated subtitle files across all ${withSubs} section${withSubs !== 1 ? "s" : ""}? You will need to re-transcribe from scratch.`}
          loading={allSectionSubDeleting}
          onConfirm={handleAllSectionSubDelete}
          onCancel={() => setAllSectionSubDeleteOpen(false)}
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
            Subtitle Generation
          </Typography>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
            <Typography variant="body2" color="text.secondary">
              Transcribe audio with OpenAI Whisper
            </Typography>
            <WhisperStatusChip />
          </Box>
        </Box>

        <Box sx={{ display: "flex", gap: 1.5 }}>
          {hasSubtitles && (
            <ButtonGroup variant="outlined" size="small">
              <Tooltip title="Download SRT">
                <Button startIcon={<DownloadIcon />} onClick={handleDownloadSrt}>
                  SRT
                </Button>
              </Tooltip>
              <Tooltip title="Download VTT (WebVTT for YouTube)">
                <Button onClick={handleDownloadVtt}>VTT</Button>
              </Tooltip>
            </ButtonGroup>
          )}
          {hasSubtitles && (
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
          )}
          <Button
            variant="contained"
            startIcon={(isRunning || isGenerating) ? <CircularProgress size={16} color="inherit" /> : <SubtitleIcon />}
            onClick={async () => {
              if (!currentProject) return;
              setIsGenerating(true);
              try {
                await triggerJob.mutateAsync({ projectId: currentProject.id, jobType: "subtitle" });
              } catch (err) {
                console.error("Subtitle generation failed:", err);
              } finally {
                setIsGenerating(false);
              }
            }}
            disabled={isRunning || isGenerating}
            size="large"
          >
            {isRunning ? "Transcribing…" : hasSubtitles ? "Re-generate" : "Generate Subtitles"}
          </Button>
        </Box>
      </Box>

      <DeleteConfirmDialog
        open={deleteOpen}
        title="Delete Subtitles"
        description="Delete the generated SRT and VTT subtitle files? You will need to re-transcribe the audio to get them back."
        loading={deleting}
        onConfirm={handleDelete}
        onCancel={() => setDeleteOpen(false)}
      />

      {/* Stats row */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        {[
          { label: "Status", value: hasSubtitles ? "Ready" : "Not Generated", color: hasSubtitles ? "#00E676" : "#9090A8" },
          { label: "Segments", value: statusData?.segment_count ?? "—", color: "#6C63FF" },
          { label: "Total Duration", value: totalDuration > 0 ? formatDuration(totalDuration) : "—", color: "#00BCD4" },
          { label: "File Size", value: statusData?.srt_size ? `${(statusData.srt_size / 1024).toFixed(1)} KB` : "—", color: "#FFB300" },
        ].map((stat) => (
          <Grid item xs={6} sm={3} key={stat.label}>
            <Card>
              <CardContent sx={{ py: 1.5, px: 2, "&:last-child": { pb: 1.5 } }}>
                <Typography variant="h5" fontWeight={800} color={stat.color} noWrap>
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
              {subtitleProgress.progress < 30
                ? "Loading Whisper model…"
                : subtitleProgress.progress < 75
                ? "Transcribing audio…"
                : "Exporting SRT / VTT…"}
            </Typography>
            <Typography variant="caption" fontWeight={700} color="primary.light">
              {subtitleProgress.progress.toFixed(0)}%
            </Typography>
          </Box>
          <LinearProgress variant="determinate" value={subtitleProgress.progress} sx={{ height: 8, borderRadius: 2 }} />
        </Box>
      )}

      {!hasSubtitles && !isRunning && !statusLoading && (
        <Alert severity="info" sx={{ mb: 3, borderRadius: 2 }}>
          Generate voice first, then click <strong>Generate Subtitles</strong> to transcribe the narration audio.
        </Alert>
      )}

      <Grid container spacing={3}>
        {/* Left: subtitle content */}
        <Grid item xs={12} md={8}>
          {/* View toggle */}
          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1.5 }}>
            <ButtonGroup size="small" variant="outlined">
              <Button
                onClick={() => setView("segments")}
                variant={view === "segments" ? "contained" : "outlined"}
              >
                Segments
              </Button>
              <Button
                onClick={() => setView("raw")}
                variant={view === "raw" ? "contained" : "outlined"}
                startIcon={<SrtIcon />}
              >
                Raw SRT
              </Button>
            </ButtonGroup>

            {view === "segments" && hasSubtitles && (
              <TextField
                size="small"
                placeholder="Search subtitles…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                sx={{ width: 200 }}
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <SearchIcon sx={{ fontSize: 16, color: "text.disabled" }} />
                    </InputAdornment>
                  ),
                }}
              />
            )}
          </Box>

          <Card>
            <CardContent sx={{ p: 2 }}>
              {view === "raw" ? (
                srtLoading ? (
                  <Skeleton variant="rectangular" height={400} sx={{ borderRadius: 2 }} />
                ) : srtText ? (
                  <Box
                    component="pre"
                    sx={{
                      bgcolor: "#080810",
                      border: "1px solid rgba(255,255,255,0.06)",
                      borderRadius: 2,
                      p: 2,
                      maxHeight: 480,
                      overflow: "auto",
                      fontFamily: '"JetBrains Mono", "Fira Code", monospace',
                      fontSize: "0.75rem",
                      color: "#E8E8F0",
                      lineHeight: 1.9,
                      whiteSpace: "pre-wrap",
                      m: 0,
                    }}
                  >
                    {srtText}
                  </Box>
                ) : (
                  <Box sx={{ py: 5, textAlign: "center", color: "text.disabled" }}>
                    <SrtIcon sx={{ fontSize: 40, mb: 1 }} />
                    <Typography variant="body2">No SRT file generated yet</Typography>
                  </Box>
                )
              ) : (
                segsLoading ? (
                  <Box sx={{ display: "flex", flexDirection: "column", gap: 0.5 }}>
                    {Array.from({ length: 8 }).map((_, i) => (
                      <Skeleton key={i} variant="rounded" height={52} />
                    ))}
                  </Box>
                ) : filteredSegments.length === 0 ? (
                  <Box sx={{ py: 5, textAlign: "center", color: "text.disabled" }}>
                    <SubtitleIcon sx={{ fontSize: 40, mb: 1 }} />
                    <Typography variant="body2">
                      {searchQuery ? "No segments match your search" : "No subtitles generated yet"}
                    </Typography>
                  </Box>
                ) : (
                  <Box sx={{ maxHeight: 480, overflow: "auto" }}>
                    {filteredSegments.map((seg) => (
                      <SegmentRow
                        key={seg.id}
                        segment={seg}
                        isActive={seg.id === activeSegId}
                        onClick={() => setActiveSegId(seg.id === activeSegId ? null : seg.id)}
                      />
                    ))}
                  </Box>
                )
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Right: timeline + progress */}
        <Grid item xs={12} md={4}>
          {hasSubtitles && segments.length > 0 && (
            <Card sx={{ mb: 2 }}>
              <CardContent sx={{ p: 2 }}>
                <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1.5 }}>
                  <Typography variant="subtitle2" fontWeight={700}>Timeline</Typography>
                  <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                    <TimeIcon sx={{ fontSize: 14, color: "text.disabled" }} />
                    <Typography variant="caption" color="text.secondary">
                      {formatDuration(totalDuration)} total
                    </Typography>
                  </Box>
                </Box>

                <Timeline
                  segments={segments}
                  totalDuration={totalDuration}
                  activeId={activeSegId}
                  onSelect={(seg) => setActiveSegId(seg.id === activeSegId ? null : seg.id)}
                />

                {activeSegment && (
                  <Box
                    sx={{
                      mt: 1.5,
                      p: 1.5,
                      bgcolor: "rgba(108,99,255,0.08)",
                      border: "1px solid rgba(108,99,255,0.2)",
                      borderRadius: 1.5,
                    }}
                  >
                    <Typography variant="caption" color="primary.light" fontWeight={700} display="block">
                      #{activeSegment.id} · {formatTime(activeSegment.start)} → {formatTime(activeSegment.end)}
                    </Typography>
                    <Typography variant="body2" sx={{ mt: 0.5, lineHeight: 1.5 }}>
                      {activeSegment.text}
                    </Typography>
                  </Box>
                )}
              </CardContent>
            </Card>
          )}

          <ProgressCard
            title="Subtitle Generation"
            status={hasSubtitles ? "completed" : subtitleProgress.status}
            progress={hasSubtitles ? 100 : subtitleProgress.progress}
            completed={hasSubtitles ? statusData?.segment_count : subtitleProgress.completed}
            total={hasSubtitles ? statusData?.segment_count : subtitleProgress.total}
          />

          {hasSubtitles && (
            <Card sx={{ mt: 2 }}>
              <CardContent sx={{ p: 2 }}>
                <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1 }}>
                  Export
                </Typography>
                <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
                  <Button
                    fullWidth
                    variant="outlined"
                    size="small"
                    startIcon={<DownloadIcon />}
                    onClick={handleDownloadSrt}
                  >
                    Download SRT
                  </Button>
                  <Button
                    fullWidth
                    variant="outlined"
                    size="small"
                    startIcon={<DownloadIcon />}
                    onClick={handleDownloadVtt}
                    color="secondary"
                  >
                    Download VTT (YouTube)
                  </Button>
                </Box>
                <Typography variant="caption" color="text.disabled" display="block" sx={{ mt: 1 }}>
                  VTT format works directly with YouTube chapter editor.
                </Typography>
              </CardContent>
            </Card>
          )}
        </Grid>
      </Grid>
    </Box>
  );
}
