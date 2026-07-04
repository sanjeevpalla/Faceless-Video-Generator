import React, { useEffect, useState } from "react";
import {
  Box,
  Typography,
  Card,
  CardContent,
  Button,
  Grid,
  TextField,
  Chip,
  Alert,
  CircularProgress,
  Tooltip,
  Tabs,
  Tab,
  IconButton,
} from "@mui/material";
import {
  AutoStories as BlogIcon,
  Refresh as RegenerateIcon,
  ContentCopy as CopyIcon,
  CheckCircle as DoneIcon,
  Save as SaveIcon,
} from "@mui/icons-material";
import { useProjectStore } from "../store";
import { useBlogStatus, useBlogContent, useBlogCopyText, useUpdateBlog, useGenerateBlog } from "../hooks/useBlog";
import { BlogPlatform } from "../api/blog";
import ProgressCard from "../components/common/ProgressCard";
import StatusBadge from "../components/common/StatusBadge";

const PLATFORMS: { key: BlogPlatform; label: string }[] = [
  { key: "medium", label: "Medium" },
  { key: "linkedin", label: "LinkedIn" },
  { key: "generic", label: "Generic" },
];

export default function BlogPage() {
  const currentProject = useProjectStore((s) => s.currentProject);
  const generationProgress = useProjectStore((s) => s.generationProgress);
  const generate = useGenerateBlog();
  const updateBlog = useUpdateBlog();

  const { data: status, isLoading: statusLoading } = useBlogStatus(currentProject?.id);
  const { data: content } = useBlogContent(currentProject?.id);

  const [platform, setPlatform] = useState<BlogPlatform>("medium");
  const { data: copyData } = useBlogCopyText(currentProject?.id, platform, !!status?.available);

  const [title, setTitle] = useState("");
  const [subtitle, setSubtitle] = useState("");
  const [body, setBody] = useState("");
  const [copied, setCopied] = useState(false);
  const [dirty, setDirty] = useState(false);

  const blogProgress = generationProgress.blog;
  const isRunning = blogProgress?.status === "running" || generate.isPending;
  const isReady = !!status?.available;

  useEffect(() => {
    if (content && !dirty) {
      setTitle(content.title);
      setSubtitle(content.subtitle);
      setBody(content.body);
    }
  }, [content, dirty]);

  const handleGenerate = async () => {
    if (!currentProject) return;
    setDirty(false);
    try {
      await generate.mutateAsync(currentProject.id);
    } catch (err) {
      console.error("Blog generation failed:", err);
    }
  };

  const handleSave = async () => {
    if (!currentProject) return;
    try {
      await updateBlog.mutateAsync({
        projectId: currentProject.id,
        payload: { title, subtitle, body },
      });
      setDirty(false);
    } catch (err) {
      console.error("Failed to save blog post:", err);
    }
  };

  const handleCopy = () => {
    if (!copyData?.text) return;
    navigator.clipboard.writeText(copyData.text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

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
            Blog Post
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Generate a long-form article from your script — ready for Medium, LinkedIn, and tech blogs
          </Typography>
        </Box>
        <Tooltip title={!status?.script_available ? "Generate script.md first (Content step)" : ""}>
          <span>
            <Button
              variant="contained"
              startIcon={isRunning ? <CircularProgress size={16} color="inherit" /> : <BlogIcon />}
              onClick={handleGenerate}
              disabled={isRunning || !status?.script_available}
              size="large"
            >
              {isRunning ? "Generating…" : isReady ? "Regenerate" : "Generate Blog Post"}
            </Button>
          </span>
        </Tooltip>
      </Box>

      {/* Running progress */}
      {isRunning && (
        <Box sx={{ mb: 3 }}>
          <Box sx={{ display: "flex", justifyContent: "space-between", mb: 0.5 }}>
            <Typography variant="caption" color="text.secondary">
              {(blogProgress?.progress ?? 0) < 20 ? "Reading script…" : "Writing article…"}
            </Typography>
            <Typography variant="caption" fontWeight={700} color="primary.light">
              {(blogProgress?.progress ?? 0).toFixed(0)}%
            </Typography>
          </Box>
          <Box sx={{ height: 8, borderRadius: 2, bgcolor: "rgba(255,255,255,0.06)", overflow: "hidden" }}>
            <Box
              sx={{
                height: "100%",
                width: `${blogProgress?.progress ?? 0}%`,
                bgcolor: "primary.main",
                borderRadius: 2,
                transition: "width 0.3s ease",
              }}
            />
          </Box>
        </Box>
      )}

      {!statusLoading && !status?.script_available && (
        <Alert severity="info" sx={{ mb: 3, borderRadius: 1.5 }}>
          Generate script.md first from the Content step before creating a blog post.
        </Alert>
      )}

      <Grid container spacing={3}>
        {/* Left: editable article */}
        <Grid item xs={12} md={7}>
          <Card>
            <CardContent sx={{ p: 2.5 }}>
              <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 2 }}>
                <Typography variant="subtitle1" fontWeight={700}>
                  Article
                </Typography>
                <StatusBadge status={isReady ? "ready" : isRunning ? "processing" : "missing"} />
              </Box>

              {isReady || dirty ? (
                <>
                  <TextField
                    fullWidth
                    label="Title"
                    value={title}
                    onChange={(e) => {
                      setTitle(e.target.value);
                      setDirty(true);
                    }}
                    size="small"
                    sx={{ mb: 1.5 }}
                  />
                  <TextField
                    fullWidth
                    label="Subtitle"
                    value={subtitle}
                    onChange={(e) => {
                      setSubtitle(e.target.value);
                      setDirty(true);
                    }}
                    size="small"
                    sx={{ mb: 1.5 }}
                  />
                  <TextField
                    fullWidth
                    multiline
                    minRows={14}
                    maxRows={28}
                    label="Body (Markdown)"
                    value={body}
                    onChange={(e) => {
                      setBody(e.target.value);
                      setDirty(true);
                    }}
                    size="small"
                    helperText={`${body.trim() ? body.trim().split(/\s+/).length : 0} words`}
                  />
                  <Button
                    sx={{ mt: 1.5 }}
                    variant="outlined"
                    startIcon={<SaveIcon />}
                    onClick={handleSave}
                    disabled={!dirty || updateBlog.isPending}
                  >
                    {updateBlog.isPending ? "Saving…" : "Save Changes"}
                  </Button>
                </>
              ) : (
                <Box
                  sx={{
                    py: 6,
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    gap: 1.5,
                    background: "linear-gradient(135deg, rgba(108,99,255,0.08), rgba(0,188,212,0.05))",
                    borderRadius: 2,
                  }}
                >
                  <BlogIcon sx={{ fontSize: 48, color: "text.disabled" }} />
                  <Typography variant="body2" color="text.disabled">
                    No blog post generated yet
                  </Typography>
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Right: platform copy + progress */}
        <Grid item xs={12} md={5}>
          <Card sx={{ mb: 2 }}>
            <CardContent sx={{ p: 2.5 }}>
              <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1 }}>
                <Typography variant="subtitle2" fontWeight={700}>
                  Copy for Platform
                </Typography>
                <Tooltip title={copied ? "Copied!" : "Copy text"}>
                  <span>
                    <IconButton
                      size="small"
                      onClick={handleCopy}
                      disabled={!copyData?.text}
                      sx={{ color: copied ? "success.main" : "text.secondary" }}
                    >
                      {copied ? <DoneIcon fontSize="small" /> : <CopyIcon fontSize="small" />}
                    </IconButton>
                  </span>
                </Tooltip>
              </Box>

              <Tabs
                value={platform}
                onChange={(_e, v) => setPlatform(v)}
                variant="fullWidth"
                sx={{ mb: 1.5, minHeight: 32 }}
              >
                {PLATFORMS.map((p) => (
                  <Tab key={p.key} value={p.key} label={p.label} sx={{ minHeight: 32, py: 0.5 }} />
                ))}
              </Tabs>

              <TextField
                fullWidth
                multiline
                minRows={10}
                maxRows={16}
                value={copyData?.text ?? ""}
                InputProps={{ readOnly: true }}
                placeholder="Generate a blog post to see platform-formatted copy text here."
                size="small"
                helperText={copyData ? `${copyData.char_count} characters` : ""}
              />
            </CardContent>
          </Card>

          <ProgressCard
            title="Blog Post Generation"
            status={isReady ? "completed" : blogProgress?.status ?? "pending"}
            progress={isReady ? 100 : blogProgress?.progress ?? 0}
          />

          {isReady && status && (
            <Card sx={{ mt: 2 }}>
              <CardContent sx={{ p: 2 }}>
                <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1 }}>
                  Article Info
                </Typography>
                <Box sx={{ display: "flex", flexDirection: "column", gap: 0.5 }}>
                  {[
                    { label: "Word count", value: `${status.word_count}` },
                    { label: "Tags", value: `${status.tag_count}` },
                  ].map((row) => (
                    <Box key={row.label} sx={{ display: "flex", justifyContent: "space-between" }}>
                      <Typography variant="caption" color="text.disabled">{row.label}</Typography>
                      <Typography variant="caption" color="text.secondary" fontWeight={600}>{row.value}</Typography>
                    </Box>
                  ))}
                </Box>
                {content?.tags && content.tags.length > 0 && (
                  <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.6, mt: 1.5 }}>
                    {content.tags.map((tag) => (
                      <Chip key={tag} label={tag} size="small" sx={{ height: 20, fontSize: "0.68rem" }} />
                    ))}
                  </Box>
                )}
              </CardContent>
            </Card>
          )}
        </Grid>
      </Grid>
    </Box>
  );
}
