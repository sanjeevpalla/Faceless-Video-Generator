import React, { useState, useCallback, useEffect } from "react";
import {
  Box, Typography, Grid, Card, CardContent, Button, Chip,
  LinearProgress, Alert, CircularProgress, Divider, Tooltip,
  IconButton, Collapse, TextField,
} from "@mui/material";
import {
  AutoAwesome as AutoAwesomeIcon,
  CheckCircle as CheckIcon,
  Refresh as RefreshIcon,
  Article as ScriptIcon,
  ViewDay as ScenesIcon,
  Image as ImageIcon,
  PhotoCamera as ThumbnailIcon,
  Tag as SeoIcon,
  RssFeed as RssIcon,
  Psychology as GeminiIcon,
  Edit as EditIcon,
} from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import { useProjectStore } from "../store";
import { useProject } from "../hooks/useProjects";
import { useWebSocket } from "../hooks/useWebSocket";
import { aiNewsApi, NewsStory } from "../api/aiNews";

// ── File status chips ──────────────────────────────────────────────────────────

const FILE_ITEMS = [
  { key: "script",           label: "script.md",            icon: <ScriptIcon fontSize="small" /> },
  { key: "scenes",           label: "scenes.json",          icon: <ScenesIcon fontSize="small" /> },
  { key: "image_prompts",    label: "image_prompts.txt",    icon: <ImageIcon fontSize="small" /> },
  { key: "thumbnail_prompt", label: "thumbnail_prompt.txt", icon: <ThumbnailIcon fontSize="small" /> },
  { key: "seo",              label: "seo.json",             icon: <SeoIcon fontSize="small" /> },
];

// ── Story card ─────────────────────────────────────────────────────────────────

function StoryCard({
  index,
  story,
  onChange,
  disabled,
}: {
  index: number;
  story: NewsStory;
  onChange: (field: keyof NewsStory, value: string) => void;
  disabled: boolean;
}) {
  const [editing, setEditing] = useState(!story.title);
  const hasContent = !!story.title.trim();

  return (
    <Card
      sx={{
        bgcolor: "rgba(255,255,255,0.025)",
        border: "1px solid",
        borderColor: hasContent ? "rgba(255,179,0,0.25)" : "rgba(255,255,255,0.06)",
        transition: "border-color 0.2s",
      }}
    >
      <CardContent sx={{ p: 1.5, "&:last-child": { pb: 1.5 } }}>
        {/* Number + toggle */}
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
          <Chip
            label={index + 1}
            size="small"
            color={hasContent ? "warning" : "default"}
            sx={{ width: 26, height: 22, fontSize: "0.7rem", fontWeight: 700 }}
          />
          {hasContent && !editing ? (
            <>
              <Typography variant="body2" fontWeight={600} sx={{ flex: 1 }} noWrap>
                {story.title}
              </Typography>
              <Tooltip title="Edit story">
                <IconButton size="small" onClick={() => setEditing(true)} disabled={disabled} sx={{ p: 0.5 }}>
                  <EditIcon sx={{ fontSize: 14, color: "text.disabled" }} />
                </IconButton>
              </Tooltip>
            </>
          ) : (
            <Typography variant="caption" color="text.disabled" sx={{ flex: 1 }}>
              {hasContent ? story.title.slice(0, 50) + "…" : `Story ${index + 1}`}
            </Typography>
          )}
        </Box>

        {/* Summary preview (collapsed when editing is false and content exists) */}
        {hasContent && !editing && (
          <Typography variant="caption" color="text.secondary" display="block" sx={{ ml: 4, lineHeight: 1.5 }}>
            {story.summary ? story.summary.slice(0, 120) + (story.summary.length > 120 ? "…" : "") : "No summary"}
          </Typography>
        )}

        {/* Edit form */}
        <Collapse in={editing || !hasContent}>
          <Box sx={{ mt: hasContent ? 1 : 0 }}>
            <TextField
              fullWidth
              label="Headline"
              value={story.title}
              onChange={(e) => onChange("title", e.target.value)}
              size="small"
              sx={{ mb: 1 }}
              disabled={disabled}
              onBlur={() => { if (story.title.trim()) setEditing(false); }}
            />
            <TextField
              fullWidth
              label="Summary"
              value={story.summary}
              onChange={(e) => onChange("summary", e.target.value)}
              multiline
              rows={2}
              size="small"
              disabled={disabled}
            />
            {hasContent && (
              <Button size="small" onClick={() => setEditing(false)} sx={{ mt: 0.5, fontSize: "0.72rem" }}>
                Done editing
              </Button>
            )}
          </Box>
        </Collapse>
      </CardContent>
    </Card>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function AiNewsPage() {
  const navigate = useNavigate();
  const currentProject = useProjectStore((s) => s.currentProject);
  const { data: project, refetch } = useProject(currentProject?.id);

  const [stories, setStories] = useState<NewsStory[]>(Array.from({ length: 10 }, () => ({ title: "", summary: "" })));
  const [scrapeStatus, setScrapeStatus] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [scrapeSource, setScrapeSource] = useState<"gemini" | "rss" | "">("");
  const [scrapeError, setScrapeError] = useState("");
  const [genStatus, setGenStatus] = useState<"idle" | "running" | "done" | "error">("idle");
  const [progress, setProgress] = useState(0);
  const [progressMsg, setProgressMsg] = useState("");
  const [genError, setGenError] = useState("");

  const displayProject = project || currentProject;
  const inputFiles = (displayProject?.input_files_status as Record<string, { status: string }>) || {};
  const filesReady = FILE_ITEMS.filter((f) => inputFiles[f.key]?.status === "ready").length;

  // Auto-fetch stories on mount
  useEffect(() => {
    if (currentProject?.id && scrapeStatus === "idle") {
      fetchStories();
    }
  }, [currentProject?.id]);

  // Mark done if files already exist (e.g. revisiting after generation)
  useEffect(() => {
    if (filesReady === FILE_ITEMS.length && genStatus === "idle") {
      setGenStatus("done");
    }
  }, [filesReady]);

  const fetchStories = async () => {
    if (!currentProject?.id) return;
    setScrapeStatus("loading");
    setScrapeError("");
    try {
      const result = await aiNewsApi.scrape(currentProject.id);
      const fetched = result.stories.slice(0, 10);
      setStories(
        fetched.length >= 10
          ? fetched
          : [...fetched, ...Array.from({ length: 10 - fetched.length }, () => ({ title: "", summary: "" }))]
      );
      setScrapeSource(result.source);
      setScrapeStatus("done");
    } catch (err: any) {
      setScrapeStatus("error");
      setScrapeError(err?.response?.data?.detail || "Failed to fetch news stories");
    }
  };

  // WebSocket progress handler
  const handleWsMessage = useCallback(
    (event: string, data: Record<string, unknown>) => {
      if (data.job_type !== "ai_news_content") return;
      if (event === "job_progress") {
        setProgress(Number(data.progress ?? 0));
        setProgressMsg(String(data.message ?? ""));
      } else if (event === "job_completed") {
        setGenStatus("done");
        setProgress(100);
        setTimeout(() => refetch(), 1500);
      } else if (event === "job_failed") {
        setGenStatus("error");
        setGenError(String(data.error ?? "Content generation failed"));
      }
    },
    [refetch]
  );
  useWebSocket({ projectId: currentProject?.id, onMessage: handleWsMessage });

  const updateStory = (idx: number, field: keyof NewsStory, value: string) =>
    setStories((prev) => prev.map((s, i) => (i === idx ? { ...s, [field]: value } : s)));

  const handleGenerate = async () => {
    if (!currentProject?.id) return;
    setGenStatus("running");
    setProgress(0);
    setProgressMsg("Initializing…");
    setGenError("");
    try {
      await aiNewsApi.generate(currentProject.id, stories);
    } catch (err: any) {
      setGenStatus("error");
      setGenError(err?.response?.data?.detail || err?.message || "Failed to start generation");
    }
  };

  const handleFetchAndGenerate = async () => {
    if (!currentProject?.id) return;
    // Step 1: fetch stories
    setScrapeStatus("loading");
    setScrapeError("");
    let fetched: NewsStory[] = [];
    try {
      const result = await aiNewsApi.scrape(currentProject.id);
      fetched = result.stories.slice(0, 10);
      setStories(
        fetched.length >= 10
          ? fetched
          : [...fetched, ...Array.from({ length: 10 - fetched.length }, () => ({ title: "", summary: "" }))]
      );
      setScrapeSource(result.source);
      setScrapeStatus("done");
    } catch {
      setScrapeStatus("error");
      return;
    }
    // Step 2: immediately generate content
    setGenStatus("running");
    setProgress(0);
    setProgressMsg("Initializing…");
    setGenError("");
    try {
      await aiNewsApi.generate(currentProject.id, fetched);
    } catch (err: any) {
      setGenStatus("error");
      setGenError(err?.response?.data?.detail || "Failed to start generation");
    }
  };

  const filledCount = stories.filter((s) => s.title.trim()).length;
  const isWorking = scrapeStatus === "loading" || genStatus === "running";

  if (!currentProject) {
    return (
      <Box sx={{ textAlign: "center", py: 8 }}>
        <Typography variant="h5" color="text.secondary" gutterBottom>No Project Selected</Typography>
        <Button variant="contained" onClick={() => navigate("/")}>Go to Dashboard</Button>
      </Box>
    );
  }

  return (
    <Box>
      {/* ── Header ── */}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 0.5 }}>
        <Typography variant="h4" fontWeight={800}>AI News Content</Typography>
        <Chip label="AI NEWS" color="warning" size="small" variant="outlined" sx={{ fontSize: "0.65rem" }} />
        {scrapeSource && (
          <Chip
            icon={scrapeSource === "gemini" ? <GeminiIcon sx={{ fontSize: 14 }} /> : <RssIcon sx={{ fontSize: 14 }} />}
            label={scrapeSource === "gemini" ? "via Gemini Search" : "via RSS"}
            size="small"
            variant="outlined"
            color={scrapeSource === "gemini" ? "primary" : "default"}
            sx={{ fontSize: "0.65rem" }}
          />
        )}
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2.5 }}>
        AI headlines are fetched automatically. Review and click Generate to produce all video files.
      </Typography>

      {/* ── File status ── */}
      <Box sx={{ display: "flex", gap: 1, mb: 2.5, flexWrap: "wrap" }}>
        {FILE_ITEMS.map(({ key, label, icon }) => {
          const ready = inputFiles[key]?.status === "ready";
          return (
            <Chip
              key={key}
              label={label}
              icon={ready ? <CheckIcon /> : icon}
              size="small"
              color={ready ? "success" : "default"}
              variant={ready ? "filled" : "outlined"}
              sx={{ fontSize: "0.7rem" }}
            />
          );
        })}
      </Box>

      {/* ── Scrape status / error ── */}
      {scrapeStatus === "loading" && (
        <Alert
          severity="info"
          icon={<CircularProgress size={16} />}
          sx={{ mb: 2, bgcolor: "rgba(30,100,200,0.08)" }}
        >
          Fetching today's top AI headlines via {scrapeSource === "rss" ? "RSS feeds" : "Gemini Search"}…
        </Alert>
      )}
      {scrapeStatus === "error" && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setScrapeStatus("idle")}>
          {scrapeError}
        </Alert>
      )}

      {/* ── Generation progress ── */}
      {genStatus === "running" && (
        <Box sx={{ mb: 2.5 }}>
          <Box sx={{ display: "flex", justifyContent: "space-between", mb: 0.5 }}>
            <Typography variant="caption" color="text.secondary">{progressMsg}</Typography>
            <Typography variant="caption" fontWeight={700} color="warning.main">{progress}%</Typography>
          </Box>
          <LinearProgress variant="determinate" value={progress} color="warning" sx={{ borderRadius: 1, height: 6 }} />
        </Box>
      )}
      {genStatus === "error" && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => { setGenStatus("idle"); setGenError(""); }}>
          {genError}
        </Alert>
      )}
      {genStatus === "done" && (
        <Alert
          severity="success"
          sx={{ mb: 2 }}
          action={
            <Button size="small" onClick={() => navigate("/images")}>
              Go to Images →
            </Button>
          }
        >
          All 5 content files generated successfully.
        </Alert>
      )}

      {/* ── Action buttons ── */}
      <Box sx={{ display: "flex", gap: 1.5, mb: 3, flexWrap: "wrap", alignItems: "center" }}>
        {/* One-click automation */}
        <Button
          variant="contained"
          color="warning"
          size="large"
          onClick={handleFetchAndGenerate}
          disabled={isWorking}
          startIcon={isWorking ? <CircularProgress size={18} color="inherit" /> : <AutoAwesomeIcon />}
          sx={{ px: 3 }}
        >
          {genStatus === "running"
            ? `Generating… ${progress}%`
            : scrapeStatus === "loading"
            ? "Fetching headlines…"
            : "Fetch & Generate"}
        </Button>

        <Divider orientation="vertical" flexItem sx={{ mx: 0.5 }} />

        {/* Manual controls */}
        <Button
          variant="outlined"
          startIcon={scrapeStatus === "loading" ? <CircularProgress size={16} /> : <RefreshIcon />}
          onClick={fetchStories}
          disabled={isWorking}
          size="large"
        >
          {scrapeStatus === "loading" ? "Fetching…" : "Refresh Stories"}
        </Button>

        {filledCount > 0 && genStatus !== "running" && (
          <Button
            variant="outlined"
            color="warning"
            startIcon={<AutoAwesomeIcon />}
            onClick={handleGenerate}
            disabled={isWorking}
            size="large"
          >
            Generate from current stories
          </Button>
        )}

        <Typography variant="caption" color="text.secondary" sx={{ ml: "auto" }}>
          {filledCount}/10 stories ready
        </Typography>
      </Box>

      {/* ── Story cards ── */}
      <Typography variant="h6" fontWeight={700} sx={{ mb: 1.5 }}>
        Today's AI News Stories
        {scrapeStatus === "loading" && (
          <CircularProgress size={14} sx={{ ml: 1.5, verticalAlign: "middle" }} />
        )}
      </Typography>
      <Grid container spacing={1.5}>
        {stories.map((story, idx) => (
          <Grid item xs={12} md={6} key={idx}>
            <StoryCard
              index={idx}
              story={story}
              onChange={(field, value) => updateStory(idx, field, value)}
              disabled={isWorking}
            />
          </Grid>
        ))}
      </Grid>
    </Box>
  );
}
