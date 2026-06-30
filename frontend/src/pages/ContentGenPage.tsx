import React, { useCallback, useEffect, useState } from "react";
import { open as tauriOpen } from "@tauri-apps/api/shell";

const openLink = async (href: string) => {
  try {
    await tauriOpen(href);
  } catch {
    window.open(href, "_blank", "noopener,noreferrer");
  }
};
import {
  Box, Typography, Button, TextField, CircularProgress,
  Alert, Chip, LinearProgress, IconButton, Tooltip, Divider,
} from "@mui/material";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  TrendingUp as TrendIcon,
  Search as ResearchIcon,
  Article as ScriptIcon,
  ViewDay as ScenesIcon,
  Image as ImageIcon,
  PhotoCamera as ThumbnailIcon,
  Tag as SeoIcon,
  PlayArrow as RunIcon,
  Refresh as RerunIcon,
  CheckCircle as DoneIcon,
  ErrorOutline as ErrorIcon,
  ContentCopy as CopyIcon,
  Visibility as VisualIcon,
  Mic as NarratorIcon,
} from "@mui/icons-material";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useProjectStore, ContentStepState } from "../store/projectStore";
import { contentApi } from "../api/content";
import { aiNewsApi } from "../api/aiNews";
import { useWebSocket } from "../hooks/useWebSocket";
import AiNewsSectionTabs from "../components/ai-news/AiNewsSectionTabs";

// ── Step config ────────────────────────────────────────────────────────────────

const STEPS = [
  { key: "trends",       label: "Trend Discovery",  action: "Discover Trends",    icon: <TrendIcon />,     desc: "Find today's top AI topics using Google Search" },
  { key: "research",     label: "Research",          action: "Research Topic",     icon: <ResearchIcon />,  desc: "Deep fact-check dossier with Google Search grounding" },
  { key: "script",       label: "Script",            action: "Write Script",       icon: <ScriptIcon />,    desc: "Full documentary script" },
  { key: "scenes",       label: "Scenes JSON",       action: "Build Scenes",       icon: <ScenesIcon />,    desc: "Scene breakdown with narration + visuals" },
  { key: "imagePrompts", label: "Image Prompts",     action: "Generate Prompts",   icon: <ImageIcon />,     desc: "FLUX Dev-optimized prompts, one per scene" },
  { key: "thumbnail",    label: "Thumbnail",         action: "Create Thumbnail",   icon: <ThumbnailIcon />, desc: "High-CTR thumbnail concept + FLUX prompt" },
  { key: "seo",          label: "SEO Metadata",      action: "Write SEO",          icon: <SeoIcon />,       desc: "Title, description, tags, chapters, keywords" },
] as const;

type StepKey = typeof STEPS[number]["key"];

// Label / description overrides applied when project_type === "ai_news"
const AI_NEWS_OVERRIDES: Partial<Record<StepKey, { label?: string; action?: string; desc?: string }>> = {
  trends: {
    label:  "AI News Topics",
    action: "Fetch AI News",
    desc:   "Automatically fetch today's top 10 AI news stories from the last 24 hours",
  },
  research: {
    desc: "Not required for AI News — the fetched topics are used directly for the script",
  },
  script: {
    desc: "Write a 10-11 minute news anchor script covering all 10 AI stories",
  },
};

// ── JSON pretty-printer ────────────────────────────────────────────────────────

const JSON_STEPS: StepKey[] = ["scenes", "seo"];

function tryPrettyJson(content: string): string | null {
  try {
    return JSON.stringify(JSON.parse(content), null, 2);
  } catch {
    return null;
  }
}

// ── Research parser + viewer ──────────────────────────────────────────────────

const RESEARCH_MD_SX = {
  fontSize: "0.85rem", lineHeight: 1.75, color: "text.secondary",
  "& p": { mt: 0, mb: 1 },
  "& ul,& ol": { pl: 2.5, mb: 1, mt: 0 },
  "& li": { mb: 0.4 },
  "& strong": { color: "text.primary", fontWeight: 600 },
  "& h1,& h2,& h3,& h4": { color: "text.primary", fontWeight: 700, mt: 2, mb: 0.75 },
  "& h1": { fontSize: "1rem" },
  "& h2": { fontSize: "0.93rem" },
  "& h3,& h4": { fontSize: "0.86rem" },
  "& a": { color: "#6C63FF" },
  "& hr": { border: "none", borderTop: "1px solid rgba(255,255,255,0.08)", my: 1.5 },
} as const;

function ResearchViewer({ content }: { content: string }) {
  return (
    <Box sx={{ flex: 1, overflow: "auto", p: 2, bgcolor: "rgba(0,0,0,0.25)",
      border: "1px solid rgba(255,255,255,0.06)", borderRadius: 2, ...RESEARCH_MD_SX }}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </Box>
  );
}

// ── Script parser + viewer ────────────────────────────────────────────────────

interface ScriptBlock { type: "visual" | "narrator"; text: string; }
interface ScriptSection { number: number; name: string; blocks: ScriptBlock[]; }
interface ParsedScript { title: string; sections: ScriptSection[]; wordCount: number; }

function parseScript(raw: string): ParsedScript | null {
  const lines = raw.split("\n");
  const sections: ScriptSection[] = [];
  let title = "";
  let titleDone = false;
  let currentSection: ScriptSection | null = null;
  let currentBlock: ScriptBlock | null = null;

  const flushBlock = () => {
    if (currentBlock && currentSection) {
      const t = currentBlock.text.trim();
      if (t) currentSection.blocks.push({ ...currentBlock, text: t });
    }
    currentBlock = null;
  };

  for (const line of lines) {
    const secMatch = line.match(/^SECTION\s+(\d+)[:\s]+(.+)/i);
    const isVisual   = /^\[VISUAL\]/i.test(line.trimStart());
    const isNarrator = /^\[NARRATOR\]/i.test(line.trimStart());

    if (secMatch) {
      flushBlock();
      if (currentSection) sections.push(currentSection);
      currentSection = { number: Number(secMatch[1]), name: secMatch[2].trim(), blocks: [] };
      titleDone = true;
    } else if (isVisual) {
      flushBlock();
      const rest = line.replace(/^\[VISUAL\]/i, "").trim();
      currentBlock = { type: "visual", text: rest ? rest + "\n" : "" };
    } else if (isNarrator) {
      flushBlock();
      const rest = line.replace(/^\[NARRATOR\]/i, "").trim();
      currentBlock = { type: "narrator", text: rest ? rest + "\n" : "" };
    } else {
      if (!titleDone && line.trim()) {
        title += (title ? " " : "") + line.trim();
      } else if (currentBlock) {
        currentBlock.text += line + "\n";
      }
    }
  }
  flushBlock();
  if (currentSection) sections.push(currentSection);

  if (!sections.length) return null;

  const wordCount = raw.split(/\s+/).filter(Boolean).length;
  return { title: title.trim(), sections, wordCount };
}

const SECTION_COLORS = [
  "#6C63FF", "#3B82F6", "#10B981", "#F59E0B",
  "#EF4444", "#8B5CF6", "#EC4899", "#14B8A6",
];

function ScriptViewer({ content }: { content: string }) {
  const parsed = parseScript(content);
  if (!parsed) return (
    <Box component="pre" sx={{ flex: 1, overflow: "auto", p: 2, fontSize: "0.82rem", lineHeight: 1.7, fontFamily: "monospace", bgcolor: "rgba(0,0,0,0.4)", borderRadius: 2, whiteSpace: "pre-wrap" }}>
      {content}
    </Box>
  );

  const estMinutes = Math.round(parsed.wordCount / 140);

  return (
    <Box sx={{ flex: 1, overflow: "auto", display: "flex", flexDirection: "column", gap: 0 }}>
      {/* Title card */}
      <Box sx={{ mb: 2, p: 2.5, bgcolor: "rgba(108,99,255,0.1)", border: "1px solid rgba(108,99,255,0.25)", borderRadius: 2 }}>
        <Typography sx={{ fontSize: "1.15rem", fontWeight: 800, lineHeight: 1.3, color: "text.primary", mb: 0.75 }}>
          {parsed.title || "Documentary Script"}
        </Typography>
        <Box sx={{ display: "flex", gap: 1.5 }}>
          <Chip label={`${parsed.wordCount.toLocaleString()} words`} size="small" variant="outlined" sx={{ height: 20, fontSize: "0.68rem" }} />
          <Chip label={`~${estMinutes} min`} size="small" variant="outlined" sx={{ height: 20, fontSize: "0.68rem" }} />
          <Chip label={`${parsed.sections.length} sections`} size="small" variant="outlined" sx={{ height: 20, fontSize: "0.68rem" }} />
        </Box>
      </Box>

      {/* Sections */}
      {parsed.sections.map((sec, si) => {
        const color = SECTION_COLORS[si % SECTION_COLORS.length];
        return (
          <Box key={si} sx={{ mb: 2 }}>
            {/* Section header */}
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
              <Box sx={{ width: 3, height: 20, bgcolor: color, borderRadius: 2, flexShrink: 0 }} />
              <Typography sx={{ fontSize: "0.7rem", fontWeight: 800, textTransform: "uppercase", letterSpacing: 1, color }}>
                Section {sec.number}
              </Typography>
              <Typography sx={{ fontSize: "0.78rem", fontWeight: 700, color: "text.secondary" }}>
                — {sec.name}
              </Typography>
            </Box>

            {/* Blocks */}
            <Box sx={{ display: "flex", flexDirection: "column", gap: 0.75, pl: 1.5 }}>
              {sec.blocks.map((block, bi) =>
                block.type === "visual" ? (
                  <Box key={bi} sx={{ display: "flex", gap: 1.25, p: 1.25, bgcolor: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 1.5 }}>
                    <VisualIcon sx={{ fontSize: 14, color: "text.disabled", mt: 0.3, flexShrink: 0 }} />
                    <Typography sx={{ fontSize: "0.75rem", color: "text.disabled", fontStyle: "italic", lineHeight: 1.55 }}>
                      {block.text}
                    </Typography>
                  </Box>
                ) : (
                  <Box key={bi} sx={{ display: "flex", gap: 1.25, p: 1.5, bgcolor: "rgba(0,0,0,0.25)", border: "1px solid rgba(255,255,255,0.05)", borderLeft: `2px solid ${color}`, borderRadius: 1.5 }}>
                    <NarratorIcon sx={{ fontSize: 14, color, mt: 0.3, flexShrink: 0 }} />
                    <Typography sx={{ fontSize: "0.85rem", lineHeight: 1.75, color: "text.primary" }}>
                      {block.text}
                    </Typography>
                  </Box>
                )
              )}
            </Box>
          </Box>
        );
      })}
    </Box>
  );
}

// ── Image Prompts parser + viewer ─────────────────────────────────────────────

interface ScenePrompt { id: string; file: string; prompt: string; }

function parseImagePrompts(raw: string): ScenePrompt[] {
  const results: ScenePrompt[] = [];
  const blocks = raw.split(/\n(?=SCENE_\d+)/);
  for (const block of blocks) {
    const lines = block.trim().split("\n");
    const id   = lines[0]?.trim() ?? "";
    const file = lines.find((l) => l.startsWith("IMAGE_FILE:"))?.replace("IMAGE_FILE:", "").trim() ?? "";
    const prompt = lines.find((l) => l.startsWith("PROMPT:"))?.replace("PROMPT:", "").trim() ?? "";
    if (id && prompt) results.push({ id, file, prompt });
  }
  return results;
}

function ImagePromptsViewer({ content }: { content: string }) {
  const scenes = parseImagePrompts(content);
  if (!scenes.length) return (
    <Box component="pre" sx={{ flex: 1, overflow: "auto", p: 2, fontSize: "0.8rem", fontFamily: "monospace", bgcolor: "rgba(0,0,0,0.4)", borderRadius: 2, whiteSpace: "pre-wrap" }}>
      {content}
    </Box>
  );
  return (
    <Box sx={{ flex: 1, overflow: "auto", display: "flex", flexDirection: "column", gap: 1 }}>
      {scenes.map((s, i) => (
        <Box
          key={i}
          sx={{
            display: "flex", gap: 1.5, p: 1.5,
            bgcolor: "rgba(0,0,0,0.35)",
            border: "1px solid rgba(255,255,255,0.06)",
            borderRadius: 1.5,
            "&:hover": { borderColor: "rgba(255,255,255,0.14)", bgcolor: "rgba(0,0,0,0.45)" },
          }}
        >
          {/* Scene number */}
          <Box sx={{
            flexShrink: 0, width: 52, height: 52,
            display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
            bgcolor: "rgba(108,99,255,0.15)", borderRadius: 1.5,
            border: "1px solid rgba(108,99,255,0.3)",
          }}>
            <Typography sx={{ fontSize: "0.6rem", color: "primary.main", fontWeight: 700, lineHeight: 1 }}>SCENE</Typography>
            <Typography sx={{ fontSize: "1rem", fontWeight: 800, color: "primary.main", lineHeight: 1 }}>
              {s.id.replace("SCENE_", "")}
            </Typography>
          </Box>

          {/* Prompt text */}
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography sx={{ fontSize: "0.75rem", color: "text.disabled", mb: 0.25, fontFamily: "monospace" }}>
              {s.file}
            </Typography>
            <Typography sx={{ fontSize: "0.82rem", lineHeight: 1.55, color: "text.primary" }}>
              {s.prompt}
            </Typography>
          </Box>

          {/* Copy button */}
          <Tooltip title="Copy prompt">
            <IconButton size="small" sx={{ flexShrink: 0, alignSelf: "flex-start" }}
              onClick={() => navigator.clipboard.writeText(s.prompt)}>
              <CopyIcon sx={{ fontSize: 14 }} />
            </IconButton>
          </Tooltip>
        </Box>
      ))}
    </Box>
  );
}

// ── Thumbnail parser + viewer ──────────────────────────────────────────────────

interface ThumbnailData {
  title: string; text: string; concept: string;
  prompt: string; color: string; focal: string; emotion: string;
}

function parseThumbnail(raw: string): ThumbnailData | null {
  const get = (key: string) =>
    raw.split("\n").find((l) => l.toUpperCase().startsWith(key.toUpperCase() + ":"))
      ?.replace(new RegExp(`^${key}:`, "i"), "").trim() ?? "";
  const prompt = get("THUMBNAIL_PROMPT");
  if (!prompt) return null;
  return {
    title:   get("THUMBNAIL_TITLE"),
    text:    get("THUMBNAIL_TEXT"),
    concept: get("THUMBNAIL_CONCEPT"),
    prompt,
    color:   get("COLOR_THEME"),
    focal:   get("FOCAL_ELEMENTS"),
    emotion: get("EMOTION"),
  };
}

function ThumbnailViewer({ content }: { content: string }) {
  const data = parseThumbnail(content);
  if (!data) return (
    <Box component="pre" sx={{ flex: 1, overflow: "auto", p: 2, fontSize: "0.8rem", fontFamily: "monospace", bgcolor: "rgba(0,0,0,0.4)", borderRadius: 2, whiteSpace: "pre-wrap" }}>
      {content}
    </Box>
  );

  const rows: { label: string; value: string; highlight?: boolean }[] = [
    { label: "Title",          value: data.title },
    { label: "Thumbnail Text", value: data.text,    highlight: true },
    { label: "Concept",        value: data.concept },
    { label: "Color Theme",    value: data.color },
    { label: "Focal Elements", value: data.focal },
    { label: "Emotion",        value: data.emotion },
  ];

  return (
    <Box sx={{ flex: 1, overflow: "auto", display: "flex", flexDirection: "column", gap: 1.5 }}>
      {/* Metadata rows */}
      <Box sx={{ bgcolor: "rgba(0,0,0,0.35)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 2, overflow: "hidden" }}>
        {rows.filter((r) => r.value).map((r, i) => (
          <Box key={i}>
            {i > 0 && <Divider sx={{ borderColor: "rgba(255,255,255,0.05)" }} />}
            <Box sx={{ display: "flex", gap: 2, px: 2, py: 1.25 }}>
              <Typography sx={{ width: 130, flexShrink: 0, fontSize: "0.72rem", fontWeight: 700, color: "text.disabled", textTransform: "uppercase", letterSpacing: 0.5, pt: 0.1 }}>
                {r.label}
              </Typography>
              <Typography sx={{ fontSize: "0.85rem", lineHeight: 1.55, color: r.highlight ? "warning.light" : "text.primary", fontWeight: r.highlight ? 700 : 400 }}>
                {r.value}
              </Typography>
            </Box>
          </Box>
        ))}
      </Box>

      {/* FLUX prompt — full-width highlight card */}
      <Box sx={{ bgcolor: "rgba(108,99,255,0.08)", border: "1px solid rgba(108,99,255,0.25)", borderRadius: 2, p: 2 }}>
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1 }}>
          <Typography sx={{ fontSize: "0.72rem", fontWeight: 700, color: "primary.main", textTransform: "uppercase", letterSpacing: 0.5 }}>
            FLUX Prompt
          </Typography>
          <Tooltip title="Copy FLUX prompt">
            <IconButton size="small" onClick={() => navigator.clipboard.writeText(data.prompt)}>
              <CopyIcon sx={{ fontSize: 14 }} />
            </IconButton>
          </Tooltip>
        </Box>
        <Typography sx={{ fontSize: "0.83rem", lineHeight: 1.65, color: "text.primary", fontFamily: "monospace" }}>
          {data.prompt}
        </Typography>
      </Box>
    </Box>
  );
}

// ── Status helpers ─────────────────────────────────────────────────────────────

function StatusChip({ status }: { status: ContentStepState["status"] }) {
  if (status === "idle")    return <Chip label="Not run" size="small" variant="outlined" />;
  if (status === "running") return <Chip label="Running…" size="small" color="primary" icon={<CircularProgress size={12} color="inherit" />} />;
  if (status === "done")    return <Chip label="Done" size="small" color="success" icon={<DoneIcon />} />;
  if (status === "error")   return <Chip label="Error" size="small" color="error" icon={<ErrorIcon />} />;
  return null;
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function ContentGenPage() {
  const navigate = useNavigate();
  const { step: stepParam } = useParams<{ step: string }>();
  const currentProject = useProjectStore((s) => s.currentProject);
  const cs = useProjectStore((s) => s.contentGenState);
  const update = useProjectStore((s) => s.updateContentState);

  const pid = currentProject?.id ?? "";
  const isAiNews = currentProject?.project_type === "ai_news";

  const [sectionLabel, setSectionLabel] = useState<string | null>(null);

  const sectionsContentQuery = useQuery({
    queryKey: ["ai-news-sections-content", pid],
    queryFn: () => aiNewsApi.getSectionsContent(pid),
    enabled: isAiNews && !!pid,
    staleTime: 30_000,
  });
  const sectionsContent = sectionsContentQuery.data ?? [];

  const stepIndex = STEPS.findIndex((s) => s.key === stepParam);
  const baseStep = STEPS[stepIndex >= 0 ? stepIndex : 0];
  const currentStep = isAiNews && AI_NEWS_OVERRIDES[baseStep.key]
    ? { ...baseStep, ...AI_NEWS_OVERRIDES[baseStep.key] }
    : baseStep;
  const stepState: ContentStepState = cs[baseStep.key];

  // Shorthand updater per step
  const setStep = (key: StepKey, patch: Partial<ContentStepState>) =>
    update({ [key]: { ...cs[key], ...patch } });

  // WebSocket listener for "run all" batch progress
  useWebSocket({
    projectId: currentProject?.id,
    onMessage: useCallback((event: string, data: Record<string, unknown>) => {
      if (data.job_type !== "content") return;
      const step = String(data.step ?? "");
      if (event === "job_progress") {
        if (step === "script")        setStep("script",       { status: "running" });
        if (step === "scenes")        setStep("scenes",       { status: "running" });
        if (step === "image_prompts") setStep("imagePrompts", { status: "running" });
        if (step === "thumbnail")     setStep("thumbnail",    { status: "running" });
        if (step === "seo")           setStep("seo",          { status: "running" });
      }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []),
  });

  // Restore previously generated content from disk when the project is opened/refreshed
  useEffect(() => {
    if (!pid) return;
    contentApi.getState(pid).then((saved) => {
      // Use getState() to read the store without adding it to deps (avoids re-running on every update)
      const cur = useProjectStore.getState().contentGenState;
      const patch: Record<string, ContentStepState> = {};
      const apply = (key: StepKey, text: string) => {
        if (text && cur[key].content === "") patch[key] = { status: "done", content: text };
      };
      apply("trends",       saved.trends);
      apply("research",     saved.research);
      apply("script",       saved.script);
      apply("scenes",       saved.scenes);
      apply("imagePrompts", saved.image_prompts);
      apply("thumbnail",    saved.thumbnail);
      apply("seo",          saved.seo);
      if (Object.keys(patch).length) update(patch as any);
    }).catch(() => { /* no saved files yet — silently ignore */ });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pid]);

  if (!currentProject) {
    return (
      <Box sx={{ textAlign: "center", py: 8 }}>
        <Typography variant="h5" color="text.secondary" gutterBottom>No Project Selected</Typography>
        <Button variant="contained" onClick={() => navigate("/")}>Go to Dashboard</Button>
      </Box>
    );
  }

  // ── Per-step run handlers ────────────────────────────────────────────────────

  const run = async (key: StepKey) => {
    setStep(key, { status: "running", content: "", error: undefined });
    try {
      let text = "";
      if (key === "trends") {
        const r = await contentApi.discoverTrends(pid);
        text = r.text;
      } else if (key === "research") {
        if (!cs.topic.trim()) { setStep(key, { status: "error", error: "Enter a topic first." }); return; }
        const r = await contentApi.researchTopic(pid, cs.topic.trim());
        text = r.text;
      } else if (key === "script") {
        if (isAiNews) {
          if (!cs.trends.content) { setStep(key, { status: "error", error: "Run 'Fetch AI News Topics' first." }); return; }
          const r = await contentApi.generateScript(pid, cs.trends.content);
          text = r.text;
        } else {
          if (!cs.research.content) { setStep(key, { status: "error", error: "Run Research first." }); return; }
          const r = await contentApi.generateScript(pid, cs.research.content);
          text = r.text;
        }
      } else if (key === "scenes") {
        if (!cs.script.content) { setStep(key, { status: "error", error: "Run Script first." }); return; }
        const r = await contentApi.generateScenes(pid, cs.script.content);
        text = r.text;
      } else if (key === "imagePrompts") {
        if (!cs.scenes.content) { setStep(key, { status: "error", error: "Run Scenes first." }); return; }
        const r = await contentApi.generateImagePrompts(pid, cs.scenes.content);
        text = r.text;
      } else if (key === "thumbnail") {
        if (!cs.script.content) { setStep(key, { status: "error", error: "Run Script first." }); return; }
        const r = await contentApi.generateThumbnail(pid, cs.script.content);
        text = r.text;
      } else if (key === "seo") {
        if (!cs.script.content) { setStep(key, { status: "error", error: "Run Script first." }); return; }
        const r = await contentApi.generateSeo(pid, cs.script.content);
        text = r.text;
      }
      setStep(key, { status: "done", content: text });
    } catch (e: any) {
      setStep(key, { status: "error", error: e?.message ?? "Unknown error" });
    }
  };

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "calc(100vh - 80px)" }}>

      {/* Step header */}
      <Box sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", mb: 2 }}>
        <Box>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 0.5 }}>
            <Typography variant="h5" fontWeight={800}>{currentStep.label}</Typography>
            {isAiNews && <Chip label="AI NEWS" color="warning" size="small" variant="outlined" sx={{ fontSize: "0.65rem" }} />}
            <StatusChip status={stepState.status} />
          </Box>
          <Typography variant="body2" color="text.secondary">{currentStep.desc}</Typography>
        </Box>

        {/* Hide action button for the Research step on AI News projects */}
        {!(isAiNews && currentStep.key === "research") && (
          <Button
            variant="contained"
            size="large"
            startIcon={stepState.status === "running"
              ? <CircularProgress size={16} color="inherit" />
              : stepState.status === "done"
              ? <RerunIcon />
              : <RunIcon />}
            onClick={() => run(baseStep.key)}
            disabled={stepState.status === "running"}
            sx={{ flexShrink: 0 }}
          >
            {stepState.status === "running" ? "Running…" : stepState.status === "done" ? "Re-run" : currentStep.action}
          </Button>
        )}
      </Box>

      {/* AI News: Research step bypass */}
      {isAiNews && currentStep.key === "research" && (
        <Alert
          severity="info"
          sx={{ mb: 2 }}
          action={
            <Button size="small" color="inherit" onClick={() => navigate("/content/script")}>
              Go to Script →
            </Button>
          }
        >
          Research is not needed for AI News. The 10 fetched topics are used directly to write the script.
        </Alert>
      )}

      {/* Topic input for Research step (Deep Dive only) */}
      {currentStep.key === "research" && !isAiNews && (
        <TextField
          fullWidth
          label="Video Topic"
          value={cs.topic}
          onChange={(e) => update({ topic: e.target.value })}
          placeholder="e.g. Noam Shazeer resignation from Google"
          helperText="Paste the best topic from Trend Discovery or type your own"
          sx={{ mb: 2 }}
        />
      )}

      {/* AI News: section tabs for scenes / imagePrompts */}
      {isAiNews && (currentStep.key === "scenes" || currentStep.key === "imagePrompts") && (
        <AiNewsSectionTabs
          sections={sectionsContent}
          selected={sectionLabel}
          onSelect={setSectionLabel}
        />
      )}

      {/* AI News section content viewer (replaces global content when a section is selected) */}
      {isAiNews && sectionLabel !== null && (currentStep.key === "scenes" || currentStep.key === "imagePrompts") && (() => {
        const sec = sectionsContent.find((s) => s.label === sectionLabel);
        const text = currentStep.key === "scenes" ? (sec?.scenes_json ?? null) : (sec?.image_prompts ?? null);
        const fallbackScript = sec?.script_text ?? null;
        return (
          <Box sx={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
            {sectionsContentQuery.isLoading ? (
              <Box sx={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "text.disabled" }}>
                <Typography variant="body2">Loading section content…</Typography>
              </Box>
            ) : text ? (
              <Box
                component="pre"
                sx={{
                  flex: 1, overflow: "auto", m: 0, p: 2,
                  fontSize: "0.8rem", lineHeight: 1.6,
                  fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                  bgcolor: "rgba(0,0,0,0.45)",
                  border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: 2,
                  whiteSpace: "pre",
                  wordBreak: "normal",
                  color: "text.primary",
                }}
              >
                {text}
              </Box>
            ) : fallbackScript ? (
              /* Per-section file missing — show raw script as fallback */
              <Box sx={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0, gap: 1 }}>
                <Alert severity="info" sx={{ fontSize: "0.78rem" }}>
                  No per-section{" "}
                  {currentStep.key === "scenes" ? "scenes.json" : "image_prompts.txt"} yet.
                  Run <strong>Generate Scenes + Prompts</strong> from the{" "}
                  <strong>Script → Scenes</strong> step to produce per-section files.
                  Showing section script below for reference.
                </Alert>
                <Box
                  component="pre"
                  sx={{
                    flex: 1, overflow: "auto", m: 0, p: 2,
                    fontSize: "0.78rem", lineHeight: 1.65,
                    fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                    bgcolor: "rgba(0,0,0,0.3)",
                    border: "1px solid rgba(255,255,255,0.06)",
                    borderRadius: 2,
                    whiteSpace: "pre-wrap",
                    color: "text.secondary",
                  }}
                >
                  {fallbackScript}
                </Box>
              </Box>
            ) : (
              <Box sx={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 1, color: "text.disabled" }}>
                <Typography variant="body2">
                  No {currentStep.key === "scenes" ? "scenes.json" : "image_prompts.txt"} for this section yet.
                </Typography>
                <Typography variant="caption">Generate section content from the AI News Clips page.</Typography>
              </Box>
            )}
          </Box>
        );
      })()}

      {/* Global content (shown when All tab selected or non-section steps) */}
      {!(isAiNews && sectionLabel !== null && (currentStep.key === "scenes" || currentStep.key === "imagePrompts")) && (
        <>

      {/* Running progress bar */}
      {stepState.status === "running" && (
        <LinearProgress sx={{ mb: 2, borderRadius: 1 }} />
      )}

      {/* Error */}
      {stepState.status === "error" && stepState.error && (
        <Alert severity="error" sx={{ mb: 2 }}>{stepState.error}</Alert>
      )}

      {/* Result */}
      {stepState.content && (() => {
        const isJsonStep = JSON_STEPS.includes(currentStep.key as StepKey);
        const prettyJson = isJsonStep ? tryPrettyJson(stepState.content) : null;
        const displayContent = prettyJson ?? stepState.content;

        // Badges
        let badge: { label: string; color: "primary" | "warning" } | null = null;
        if (currentStep.key === "script") {
          const wc = stepState.content.split(/\s+/).filter(Boolean).length;
          if (wc) badge = { label: `${wc.toLocaleString()} words`, color: "primary" };
        } else if (currentStep.key === "scenes" && prettyJson) {
          try { const a = JSON.parse(prettyJson); if (Array.isArray(a)) badge = { label: `${a.length} scenes`, color: "primary" }; } catch { /* ignore */ }
        } else if (currentStep.key === "imagePrompts") {
          const count = parseImagePrompts(stepState.content).length;
          if (count) badge = { label: `${count} prompts`, color: "primary" };
        } else if (isJsonStep && !prettyJson) {
          badge = { label: "Invalid JSON", color: "warning" };
        }

        return (
          <Box sx={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
            <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1 }}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                <Typography variant="caption" color="text.secondary">
                  {displayContent.split("\n").length} lines · {displayContent.length.toLocaleString()} chars
                </Typography>
                {badge && (
                  <Chip label={badge.label} size="small" color={badge.color} variant="outlined" sx={{ height: 18, fontSize: "0.7rem" }} />
                )}
              </Box>
              <Tooltip title="Copy to clipboard">
                <IconButton size="small" onClick={() => navigator.clipboard.writeText(displayContent)}>
                  <CopyIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            </Box>

            {/* Step-specific viewers */}
            {currentStep.key === "research" ? (
              <ResearchViewer content={stepState.content} />
            ) : currentStep.key === "script" ? (
              <ScriptViewer content={stepState.content} />
            ) : currentStep.key === "imagePrompts" ? (
              <ImagePromptsViewer content={stepState.content} />
            ) : currentStep.key === "thumbnail" ? (
              <ThumbnailViewer content={stepState.content} />
            ) : isJsonStep && prettyJson ? (
              <Box
                component="pre"
                sx={{
                  flex: 1, overflow: "auto", m: 0, p: 2,
                  fontSize: "0.8rem", lineHeight: 1.6,
                  fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                  bgcolor: "rgba(0,0,0,0.45)",
                  border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: 2,
                  whiteSpace: "pre",
                  wordBreak: "normal",
                  color: "text.primary",
                  "& .json-key":    { color: "#79b8ff" },
                  "& .json-str":    { color: "#9ecbff" },
                  "& .json-num":    { color: "#f8c555" },
                  "& .json-bool":   { color: "#56d364" },
                  "& .json-null":   { color: "#888" },
                }}
                dangerouslySetInnerHTML={{
                  __html: prettyJson
                    .replace(/&/g, "&amp;")
                    .replace(/</g, "&lt;")
                    .replace(/>/g, "&gt;")
                    .replace(
                      /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,
                      (match) => {
                        if (/^"/.test(match)) {
                          if (/:$/.test(match)) return `<span class="json-key">${match}</span>`;
                          return `<span class="json-str">${match}</span>`;
                        }
                        if (/true|false/.test(match)) return `<span class="json-bool">${match}</span>`;
                        if (/null/.test(match))       return `<span class="json-null">${match}</span>`;
                        return `<span class="json-num">${match}</span>`;
                      }
                    ),
                }}
              />
            ) : (
              /* Markdown viewer (all non-JSON steps) */
              <Box
                sx={{
                  flex: 1, overflow: "auto", m: 0, p: 2,
                  fontSize: "0.82rem", lineHeight: 1.75,
                  bgcolor: "rgba(0,0,0,0.35)",
                  border: "1px solid rgba(255,255,255,0.06)",
                  borderRadius: 2,
                  "& table": { borderCollapse: "collapse", width: "100%", mb: 2 },
                  "& th": {
                    border: "1px solid rgba(255,255,255,0.2)",
                    p: "6px 12px", textAlign: "left",
                    bgcolor: "rgba(255,255,255,0.06)", fontWeight: 700,
                  },
                  "& td": {
                    border: "1px solid rgba(255,255,255,0.1)",
                    p: "6px 12px", verticalAlign: "top",
                  },
                  "& tr:nth-of-type(even) td": { bgcolor: "rgba(255,255,255,0.02)" },
                  "& a": { color: "#6C63FF", textDecorationColor: "rgba(108,99,255,0.4)" },
                  "& h2": { mt: 3, mb: 1.5, fontSize: "1rem", fontWeight: 700 },
                  "& p": { mb: 1 },
                  "& ul, & ol": { pl: 3, mb: 1 },
                  "& li": { mb: 0.5 },
                  "& hr": { borderColor: "rgba(255,255,255,0.1)", my: 2 },
                  "& code": { bgcolor: "rgba(255,255,255,0.08)", px: 0.5, borderRadius: 0.5, fontFamily: "monospace" },
                }}
              >
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    a: ({ href, children }) => (
                      <a
                        href={href}
                        onClick={(e) => { e.preventDefault(); if (href) openLink(href); }}
                        style={{ cursor: "pointer", color: "#6C63FF" }}
                      >
                        {children}
                      </a>
                    ),
                  }}
                >
                  {stepState.content}
                </ReactMarkdown>
              </Box>
            )}
          </Box>
        );
      })()}

      {/* Empty state */}
      {!stepState.content && stepState.status !== "running" && (
        <Box
          sx={{
            flex: 1, display: "flex", flexDirection: "column",
            alignItems: "center", justifyContent: "center", gap: 2,
            color: "text.disabled",
          }}
        >
          {React.cloneElement(currentStep.icon as React.ReactElement, { sx: { fontSize: 48, opacity: 0.3 } })}
          <Typography variant="body2">
            {stepState.status === "error"
              ? "Step failed — click Re-run to try again."
              : stepState.status === "done"
              ? "Step completed but no content was returned — click Re-run to try again."
              : "Click Run to generate this step."}
          </Typography>
        </Box>
      )}
        </>
      )}
    </Box>
  );
}
