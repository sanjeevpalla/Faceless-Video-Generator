import React, { useState, useEffect } from "react";
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
  Skeleton,
  CircularProgress,
  Tooltip,
  Divider,
  IconButton,
} from "@mui/material";
import {
  PhotoCamera as ThumbnailIcon,
  Refresh as RegenerateIcon,
  Download as DownloadIcon,
  AutoAwesome as AIIcon,
  ContentCopy as CopyIcon,
  CheckCircle as DoneIcon,
  DeleteForever as DeleteIcon,
} from "@mui/icons-material";
import { useProjectStore } from "../store";
import { useThumbnailStatus, useRegenerateThumbnail, THUMBNAIL_KEYS } from "../hooks/useThumbnail";
import { thumbnailApi } from "../api/thumbnail";
import { useQueryClient } from "@tanstack/react-query";
import ProgressCard from "../components/common/ProgressCard";
import StatusBadge from "../components/common/StatusBadge";
import DeleteConfirmDialog from "../components/common/DeleteConfirmDialog";
import ComfyUIControl from "../components/common/ComfyUIControl";
import { useComfyUIStatus } from "../hooks/useImages";

const PROMPT_TAGS = [
  "4K quality",
  "vibrant colors",
  "professional",
  "eye-catching",
  "dramatic lighting",
  "cinematic",
  "high contrast",
  "stunning",
  "epic",
  "minimalist",
];

export default function ThumbnailPage() {
  const currentProject = useProjectStore((s) => s.currentProject);
  const generationProgress = useProjectStore((s) => s.generationProgress);
  const regenerate = useRegenerateThumbnail();

  const queryClient = useQueryClient();
  const { data: thumbStatus, isLoading } = useThumbnailStatus(currentProject?.id);
  const { data: comfyStatus } = useComfyUIStatus();
  const [imgError, setImgError] = useState(false);
  const [imgLoaded, setImgLoaded] = useState(false);
  const [customPrompt, setCustomPrompt] = useState("");
  const [copied, setCopied] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const thumbProgress = generationProgress.thumbnail;
  const isRunning = thumbProgress.status === "running" || regenerate.isPending;
  const isReady = thumbStatus?.status === "ready" && !imgError;
  const comfyOnline = comfyStatus?.online ?? false;

  // Load existing prompt into the editor
  useEffect(() => {
    if (thumbStatus?.prompt && !customPrompt) {
      setCustomPrompt(thumbStatus.prompt);
    }
  }, [thumbStatus?.prompt]);

  const handleRegenerate = async () => {
    if (!currentProject) return;
    setImgError(false);
    setImgLoaded(false);
    try {
      await regenerate.mutateAsync(currentProject.id);
    } catch (err) {
      console.error("Thumbnail regeneration failed:", err);
    }
  };

  const handleDelete = async () => {
    if (!currentProject) return;
    setDeleting(true);
    try {
      await thumbnailApi.deleteOutputs(currentProject.id);
      queryClient.invalidateQueries({ queryKey: THUMBNAIL_KEYS.status(currentProject.id) });
      setImgError(false);
      setImgLoaded(false);
    } catch (err) {
      console.error("Failed to delete thumbnail:", err);
    } finally {
      setDeleting(false);
      setDeleteOpen(false);
    }
  };

  const handleDownload = () => {
    if (!currentProject || !isReady) return;
    const url = thumbnailApi.getThumbnailUrl(currentProject.id);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${currentProject.name}_thumbnail.png`;
    a.click();
  };

  const handleCopyPrompt = () => {
    if (!customPrompt) return;
    navigator.clipboard.writeText(customPrompt).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const appendTag = (tag: string) => {
    setCustomPrompt((prev) => (prev ? `${prev}, ${tag}` : tag));
  };

  if (!currentProject) {
    return (
      <Box sx={{ textAlign: "center", py: 8 }}>
        <Typography color="text.secondary">No project selected.</Typography>
      </Box>
    );
  }

  const thumbnailUrl = thumbnailApi.getThumbnailUrl(currentProject.id);

  return (
    <Box>
      {/* Header */}
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 3 }}>
        <Box>
          <Typography variant="h4" fontWeight={800} gutterBottom>
            Thumbnail Generation
          </Typography>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
            <Typography variant="body2" color="text.secondary">
              Generate a YouTube thumbnail using FLUX Dev via ComfyUI
            </Typography>
            <ComfyUIControl />
          </Box>
        </Box>
        <Box sx={{ display: "flex", gap: 1.5 }}>
          {isReady && (
            <Button variant="outlined" startIcon={<DownloadIcon />} onClick={handleDownload}>
              Download PNG
            </Button>
          )}
          {isReady && (
            <Button
              variant="outlined"
              color="error"
              startIcon={<DeleteIcon />}
              onClick={() => setDeleteOpen(true)}
              disabled={isRunning}
            >
              Delete
            </Button>
          )}
          <Tooltip title={!comfyOnline ? "Start ComfyUI first" : ""}>
            <span>
              <Button
                variant="contained"
                startIcon={isRunning ? <CircularProgress size={16} color="inherit" /> : isReady ? <RegenerateIcon /> : <ThumbnailIcon />}
                onClick={handleRegenerate}
                disabled={isRunning || !comfyOnline}
                size="large"
              >
                {isRunning ? "Generating…" : isReady ? "Regenerate" : "Generate Thumbnail"}
              </Button>
            </span>
          </Tooltip>
        </Box>
      </Box>

      <DeleteConfirmDialog
        open={deleteOpen}
        title="Delete Thumbnail"
        description="Delete the generated thumbnail image? You will need to regenerate it from scratch."
        loading={deleting}
        onConfirm={handleDelete}
        onCancel={() => setDeleteOpen(false)}
      />

      {/* Running progress */}
      {isRunning && (
        <Box sx={{ mb: 3 }}>
          <Box sx={{ display: "flex", justifyContent: "space-between", mb: 0.5 }}>
            <Typography variant="caption" color="text.secondary">
              {thumbProgress.progress < 30 ? "Submitting to ComfyUI…" : thumbProgress.progress < 80 ? "Rendering thumbnail…" : "Downloading…"}
            </Typography>
            <Typography variant="caption" fontWeight={700} color="primary.light">
              {thumbProgress.progress.toFixed(0)}%
            </Typography>
          </Box>
          <Box sx={{ mb: 3, height: 8, borderRadius: 2, bgcolor: "rgba(255,255,255,0.06)", overflow: "hidden" }}>
            <Box
              sx={{
                height: "100%",
                width: `${thumbProgress.progress}%`,
                bgcolor: "primary.main",
                borderRadius: 2,
                transition: "width 0.3s ease",
              }}
            />
          </Box>
        </Box>
      )}

      <Grid container spacing={3}>
        {/* Left: thumbnail preview */}
        <Grid item xs={12} md={7}>
          <Card>
            <CardContent sx={{ p: 2 }}>
              <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 2 }}>
                <Typography variant="subtitle1" fontWeight={700}>
                  Thumbnail Preview
                  <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 1 }}>
                    1280 × 720 · 16:9
                  </Typography>
                </Typography>
                <StatusBadge status={isReady ? "ready" : thumbProgress.status === "running" ? "processing" : "missing"} />
              </Box>

              {/* Image container */}
              <Box
                sx={{
                  width: "100%",
                  aspectRatio: "16/9",
                  borderRadius: 2,
                  overflow: "hidden",
                  bgcolor: "#050508",
                  border: `2px solid ${isReady ? "rgba(0,230,118,0.2)" : "rgba(255,255,255,0.06)"}`,
                  position: "relative",
                }}
              >
                {isLoading || isRunning ? (
                  <Box sx={{ display: "flex", height: "100%", alignItems: "center", justifyContent: "center" }}>
                    {isRunning ? (
                      <Box sx={{ textAlign: "center" }}>
                        <CircularProgress size={40} sx={{ mb: 1 }} />
                        <Typography variant="caption" color="text.secondary" display="block">
                          Generating with FLUX Dev…
                        </Typography>
                      </Box>
                    ) : (
                      <Skeleton variant="rectangular" sx={{ position: "absolute", inset: 0, transform: "none" }} />
                    )}
                  </Box>
                ) : isReady && !imgError ? (
                  <>
                    {!imgLoaded && (
                      <Skeleton variant="rectangular" sx={{ position: "absolute", inset: 0, transform: "none" }} />
                    )}
                    <img
                      src={`${thumbnailUrl}?t=${Date.now()}`}
                      alt="Thumbnail"
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
                ) : (
                  <Box
                    sx={{
                      height: "100%",
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "center",
                      justifyContent: "center",
                      gap: 1.5,
                      background: "linear-gradient(135deg, rgba(108,99,255,0.08), rgba(0,188,212,0.05))",
                    }}
                  >
                    <AIIcon sx={{ fontSize: 48, color: "text.disabled" }} />
                    <Typography variant="body2" color="text.disabled">
                      {imgError ? "Could not load thumbnail" : "Thumbnail not generated yet"}
                    </Typography>
                    <Typography variant="caption" color="text.disabled">
                      Click "Generate Thumbnail" to create one with FLUX Dev
                    </Typography>
                  </Box>
                )}

                {/* Ready badge overlay */}
                {isReady && imgLoaded && (
                  <Box
                    sx={{
                      position: "absolute",
                      top: 8,
                      right: 8,
                      bgcolor: "rgba(0,0,0,0.7)",
                      borderRadius: 1,
                      px: 1,
                      py: 0.25,
                      display: "flex",
                      alignItems: "center",
                      gap: 0.5,
                    }}
                  >
                    <DoneIcon sx={{ fontSize: 12, color: "success.main" }} />
                    <Typography variant="caption" color="success.main" fontWeight={700}>
                      Ready
                    </Typography>
                  </Box>
                )}
              </Box>

              {isReady && (
                <Box sx={{ mt: 1.5, display: "flex", gap: 1 }}>
                  <Button fullWidth variant="outlined" size="small" startIcon={<DownloadIcon />} onClick={handleDownload}>
                    Download PNG
                  </Button>
                  <Button fullWidth variant="outlined" size="small" startIcon={<RegenerateIcon />} onClick={handleRegenerate} disabled={isRunning}>
                    Regenerate
                  </Button>
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Right: prompt editor + progress */}
        <Grid item xs={12} md={5}>
          {/* Prompt editor */}
          <Card sx={{ mb: 2 }}>
            <CardContent sx={{ p: 2.5 }}>
              <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1.5 }}>
                <Typography variant="subtitle2" fontWeight={700}>
                  FLUX Prompt
                </Typography>
                <Tooltip title={copied ? "Copied!" : "Copy prompt"}>
                  <IconButton size="small" onClick={handleCopyPrompt} sx={{ color: copied ? "success.main" : "text.secondary" }}>
                    {copied ? <DoneIcon fontSize="small" /> : <CopyIcon fontSize="small" />}
                  </IconButton>
                </Tooltip>
              </Box>

              <TextField
                fullWidth
                multiline
                rows={5}
                value={customPrompt}
                onChange={(e) => setCustomPrompt(e.target.value)}
                placeholder="e.g. Professional YouTube thumbnail showing futuristic AI robot, vibrant neon colors, dramatic lighting, 4K, ultra-detailed"
                helperText={`${customPrompt.length} chars · Edit prompt and regenerate to try variations`}
                size="small"
              />

              <Box sx={{ mt: 1.5 }}>
                <Typography variant="caption" color="text.disabled" display="block" sx={{ mb: 0.75 }}>
                  Quick tags — click to append:
                </Typography>
                <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.6 }}>
                  {PROMPT_TAGS.map((tag) => (
                    <Chip
                      key={tag}
                      label={tag}
                      size="small"
                      onClick={() => appendTag(tag)}
                      sx={{
                        height: 22,
                        fontSize: "0.68rem",
                        cursor: "pointer",
                        bgcolor: "rgba(108,99,255,0.08)",
                        color: "primary.light",
                        border: "1px solid rgba(108,99,255,0.2)",
                        "&:hover": { bgcolor: "rgba(108,99,255,0.18)" },
                      }}
                    />
                  ))}
                </Box>
              </Box>

              <Alert severity="info" sx={{ mt: 1.5, borderRadius: 1.5, py: 0.5 }}>
                <Typography variant="caption">
                  The prompt from <strong>thumbnail_prompt.txt</strong> is used by default. Edit here and regenerate to try variations.
                </Typography>
              </Alert>
            </CardContent>
          </Card>

          {/* Progress card */}
          <ProgressCard
            title="Thumbnail Generation"
            status={isReady ? "completed" : thumbProgress.status}
            progress={isReady ? 100 : thumbProgress.progress}
          />

          {/* File info */}
          {isReady && thumbStatus && (
            <Card sx={{ mt: 2 }}>
              <CardContent sx={{ p: 2 }}>
                <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1 }}>
                  Output Info
                </Typography>
                <Box sx={{ display: "flex", flexDirection: "column", gap: 0.5 }}>
                  {[
                    { label: "Format", value: "PNG" },
                    { label: "Resolution", value: "1280 × 720" },
                    { label: "Size", value: `${(thumbStatus.size / 1024).toFixed(0)} KB` },
                    { label: "Ratio", value: "16:9 (YouTube standard)" },
                  ].map((row) => (
                    <Box key={row.label} sx={{ display: "flex", justifyContent: "space-between" }}>
                      <Typography variant="caption" color="text.disabled">{row.label}</Typography>
                      <Typography variant="caption" color="text.secondary" fontWeight={600}>{row.value}</Typography>
                    </Box>
                  ))}
                </Box>
              </CardContent>
            </Card>
          )}
        </Grid>
      </Grid>
    </Box>
  );
}
