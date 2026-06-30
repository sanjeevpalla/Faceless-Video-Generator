/**
 * MetadataPanel — displays SEO source data and the generated YouTube metadata
 * side-by-side. Allows inline editing of the generated output and provides
 * copy-to-clipboard for the full formatted block.
 */
import React, { useState, useEffect } from "react";
import {
  Box,
  Typography,
  Card,
  CardContent,
  Button,
  TextField,
  Chip,
  Alert,
  CircularProgress,
  Skeleton,
  Divider,
  IconButton,
  Tooltip,
  LinearProgress,
} from "@mui/material";
import {
  ContentCopy as CopyIcon,
  CheckCircle as DoneIcon,
  Edit as EditIcon,
  Save as SaveIcon,
  AutoAwesome as GenerateIcon,
  Tag as TagIcon,
} from "@mui/icons-material";
import {
  useMetadataStatus,
  useSeoData,
  useYouTubeMetadata,
  useUpdateYouTubeMetadata,
  useGenerateMetadata,
} from "../../hooks/useMetadata";
import { metadataApi } from "../../api/metadata";

// ---------------------------------------------------------------------------
// Character limit bar
// ---------------------------------------------------------------------------
function LimitBar({ value, max, label }: { value: number; max: number; label: string }) {
  const pct = Math.min(100, (value / max) * 100);
  const color = pct > 90 ? "error" : pct > 75 ? "warning" : "primary";
  return (
    <Box sx={{ mb: 0.5 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", mb: 0.25 }}>
        <Typography variant="caption" color="text.disabled">{label}</Typography>
        <Typography variant="caption" color={pct > 90 ? "error.main" : "text.secondary"}>
          {value}/{max}
        </Typography>
      </Box>
      <LinearProgress variant="determinate" value={pct} color={color} sx={{ height: 3, borderRadius: 1 }} />
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Copy button
// ---------------------------------------------------------------------------
function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };
  return (
    <Tooltip title={copied ? "Copied!" : `Copy ${label}`}>
      <IconButton size="small" onClick={handleCopy} sx={{ color: copied ? "success.main" : "text.secondary" }}>
        {copied ? <DoneIcon sx={{ fontSize: 15 }} /> : <CopyIcon sx={{ fontSize: 15 }} />}
      </IconButton>
    </Tooltip>
  );
}

// ---------------------------------------------------------------------------
// Main panel
// ---------------------------------------------------------------------------
interface MetadataPanelProps {
  projectId: string;
}

export default function MetadataPanel({ projectId }: MetadataPanelProps) {
  const { data: status } = useMetadataStatus(projectId);
  const { data: seo, isLoading: seoLoading } = useSeoData(projectId);
  const { data: yt, isLoading: ytLoading, refetch: refetchYt } = useYouTubeMetadata(projectId);
  const updateMeta = useUpdateYouTubeMetadata();
  const generateMeta = useGenerateMetadata();

  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editDesc, setEditDesc] = useState("");
  const [editTags, setEditTags] = useState("");
  const [copyAllDone, setCopyAllDone] = useState(false);

  useEffect(() => {
    if (yt && editing) {
      setEditTitle(yt.title);
      setEditDesc(yt.description);
      setEditTags(yt.tags.join(", "));
    }
  }, [yt, editing]);

  const startEdit = () => {
    if (yt) {
      setEditTitle(yt.title);
      setEditDesc(yt.description);
      setEditTags(yt.tags.join(", "));
    }
    setEditing(true);
  };

  const saveEdit = async () => {
    await updateMeta.mutateAsync({
      projectId,
      payload: {
        title: editTitle,
        description: editDesc,
        tags: editTags.split(",").map((t) => t.trim()).filter(Boolean),
      },
    });
    setEditing(false);
    refetchYt();
  };

  const handleGenerate = async () => {
    await generateMeta.mutateAsync(projectId);
  };

  const handleCopyAll = async () => {
    try {
      const { text } = await metadataApi.getCopyText(projectId);
      await navigator.clipboard.writeText(text);
      setCopyAllDone(true);
      setTimeout(() => setCopyAllDone(false), 3000);
    } catch {
      // ignore
    }
  };

  const hasYt = !!yt;

  return (
    <Box>
      {/* Header actions */}
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 2 }}>
        <Typography variant="h6" fontWeight={700}>
          YouTube Metadata
        </Typography>
        <Box sx={{ display: "flex", gap: 1 }}>
          {hasYt && (
            <>
              <Button
                size="small"
                variant="outlined"
                startIcon={copyAllDone ? <DoneIcon /> : <CopyIcon />}
                onClick={handleCopyAll}
                color={copyAllDone ? "success" : "primary"}
              >
                {copyAllDone ? "Copied!" : "Copy All"}
              </Button>
              {!editing ? (
                <Button size="small" variant="outlined" startIcon={<EditIcon />} onClick={startEdit}>
                  Edit
                </Button>
              ) : (
                <Button
                  size="small"
                  variant="contained"
                  startIcon={updateMeta.isPending ? <CircularProgress size={14} color="inherit" /> : <SaveIcon />}
                  onClick={saveEdit}
                  disabled={updateMeta.isPending}
                >
                  Save
                </Button>
              )}
            </>
          )}
          <Button
            size="small"
            variant="contained"
            startIcon={generateMeta.isPending ? <CircularProgress size={14} color="inherit" /> : <GenerateIcon />}
            onClick={handleGenerate}
            disabled={generateMeta.isPending || !status?.seo_available}
          >
            {hasYt ? "Re-generate" : "Generate"}
          </Button>
        </Box>
      </Box>

      {!status?.seo_available && (
        <Alert severity="warning" sx={{ mb: 2, borderRadius: 2 }}>
          Upload seo.json on the Project page before generating metadata.
        </Alert>
      )}

      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" }, gap: 3 }}>
        {/* SEO source */}
        <Card>
          <CardContent sx={{ p: 2 }}>
            <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1.5 }}>
              SEO Source (seo.json)
            </Typography>
            {seoLoading ? (
              <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
                {[1, 2, 3].map((i) => <Skeleton key={i} height={40} />)}
              </Box>
            ) : seo ? (
              <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
                <Box>
                  <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <Typography variant="caption" color="text.disabled" fontWeight={600}>TITLE</Typography>
                    <CopyButton text={seo.title} label="title" />
                  </Box>
                  <Typography variant="body2" fontWeight={600}>{seo.title}</Typography>
                  <LimitBar value={seo.title.length} max={100} label="" />
                </Box>

                <Divider sx={{ borderColor: "rgba(255,255,255,0.05)" }} />

                <Box>
                  <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <Typography variant="caption" color="text.disabled" fontWeight={600}>DESCRIPTION</Typography>
                    <CopyButton text={seo.description} label="description" />
                  </Box>
                  <Typography variant="body2" color="text.secondary" sx={{ maxHeight: 100, overflow: "auto", lineHeight: 1.5 }}>
                    {seo.description}
                  </Typography>
                  <LimitBar value={seo.description.length} max={5000} label="" />
                </Box>

                <Divider sx={{ borderColor: "rgba(255,255,255,0.05)" }} />

                <Box>
                  <Typography variant="caption" color="text.disabled" fontWeight={600} display="block" sx={{ mb: 0.5 }}>
                    TAGS ({seo.tags.length})
                  </Typography>
                  <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, maxHeight: 80, overflow: "auto" }}>
                    {seo.tags.map((tag, i) => (
                      <Chip key={i} label={tag} size="small" sx={{ height: 18, fontSize: "0.62rem", bgcolor: "rgba(255,255,255,0.06)" }} />
                    ))}
                  </Box>
                </Box>

                {seo.chapters && seo.chapters.length > 0 && (
                  <>
                    <Divider sx={{ borderColor: "rgba(255,255,255,0.05)" }} />
                    <Box>
                      <Typography variant="caption" color="text.disabled" fontWeight={600} display="block" sx={{ mb: 0.5 }}>
                        CHAPTERS ({seo.chapters.length})
                      </Typography>
                      {seo.chapters.map((ch, i) => (
                        <Typography key={i} variant="caption" color="text.secondary" display="block">
                          {ch.timestamp} — {ch.title}
                        </Typography>
                      ))}
                    </Box>
                  </>
                )}
              </Box>
            ) : (
              <Typography variant="caption" color="text.disabled">
                seo.json not uploaded yet.
              </Typography>
            )}
          </CardContent>
        </Card>

        {/* Generated YouTube metadata */}
        <Card>
          <CardContent sx={{ p: 2 }}>
            <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1.5 }}>
              Generated Output (youtube_metadata.json)
            </Typography>

            {ytLoading ? (
              <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
                {[1, 2, 3].map((i) => <Skeleton key={i} height={40} />)}
              </Box>
            ) : yt ? (
              <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
                {/* Title */}
                <Box>
                  <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <Typography variant="caption" color="text.disabled" fontWeight={600}>TITLE</Typography>
                    {!editing && <CopyButton text={yt.title} label="title" />}
                  </Box>
                  {editing ? (
                    <TextField
                      fullWidth
                      size="small"
                      value={editTitle}
                      onChange={(e) => setEditTitle(e.target.value)}
                      inputProps={{ maxLength: 100 }}
                    />
                  ) : (
                    <Typography variant="body2" fontWeight={600}>{yt.title}</Typography>
                  )}
                  <LimitBar value={(editing ? editTitle : yt.title).length} max={100} label="" />
                </Box>

                <Divider sx={{ borderColor: "rgba(255,255,255,0.05)" }} />

                {/* Description */}
                <Box>
                  <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <Typography variant="caption" color="text.disabled" fontWeight={600}>DESCRIPTION</Typography>
                    {!editing && <CopyButton text={yt.description} label="description" />}
                  </Box>
                  {editing ? (
                    <TextField
                      fullWidth
                      multiline
                      rows={4}
                      size="small"
                      value={editDesc}
                      onChange={(e) => setEditDesc(e.target.value)}
                      inputProps={{ maxLength: 5000 }}
                    />
                  ) : (
                    <Typography variant="body2" color="text.secondary" sx={{ maxHeight: 100, overflow: "auto", lineHeight: 1.5 }}>
                      {yt.description}
                    </Typography>
                  )}
                  <LimitBar value={(editing ? editDesc : yt.description).length} max={5000} label="" />
                </Box>

                <Divider sx={{ borderColor: "rgba(255,255,255,0.05)" }} />

                {/* Tags */}
                <Box>
                  <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <Typography variant="caption" color="text.disabled" fontWeight={600}>TAGS ({yt.tags.length})</Typography>
                    {!editing && <CopyButton text={yt.tags.join(", ")} label="tags" />}
                  </Box>
                  {editing ? (
                    <TextField
                      fullWidth
                      size="small"
                      value={editTags}
                      onChange={(e) => setEditTags(e.target.value)}
                      helperText="Comma-separated"
                    />
                  ) : (
                    <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, maxHeight: 80, overflow: "auto" }}>
                      {yt.tags.map((tag, i) => (
                        <Chip key={i} label={tag} size="small"
                          sx={{ height: 18, fontSize: "0.62rem", bgcolor: "rgba(108,99,255,0.1)", color: "primary.light" }}
                        />
                      ))}
                    </Box>
                  )}
                </Box>

                {/* Meta chips */}
                <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap" }}>
                  <Chip label={`Privacy: ${yt.privacy_status}`} size="small" sx={{ height: 20, fontSize: "0.62rem" }} />
                  <Chip label={`Category: ${yt.category_id}`} size="small" sx={{ height: 20, fontSize: "0.62rem" }} />
                  <Chip label={`Lang: ${yt.language}`} size="small" sx={{ height: 20, fontSize: "0.62rem" }} />
                </Box>
              </Box>
            ) : (
              <Box sx={{ py: 4, textAlign: "center", color: "text.disabled" }}>
                <GenerateIcon sx={{ fontSize: 40, mb: 1 }} />
                <Typography variant="body2">Click "Generate" to create YouTube metadata from seo.json</Typography>
              </Box>
            )}
          </CardContent>
        </Card>
      </Box>
    </Box>
  );
}
