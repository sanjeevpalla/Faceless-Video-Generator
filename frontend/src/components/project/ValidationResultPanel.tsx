import React from "react";
import {
  Box,
  Typography,
  Chip,
  Collapse,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Alert,
} from "@mui/material";
import {
  CheckCircle as OkIcon,
  Error as ErrorIcon,
  Warning as WarnIcon,
  Info as InfoIcon,
} from "@mui/icons-material";

export interface FileValidationResult {
  file_type: string;
  valid: boolean;
  errors: string[];
  warnings: string[];
  info: Record<string, string | number | boolean>;
}

export interface ValidationResults {
  all_valid: boolean;
  results: Record<string, FileValidationResult>;
}

const FILE_LABELS: Record<string, string> = {
  script: "Script (script.md)",
  scenes: "Scenes JSON (scenes.json)",
  image_prompts: "Image Prompts (image_prompts.txt)",
  thumbnail_prompt: "Thumbnail Prompt (thumbnail_prompt.txt)",
  seo: "SEO Data (seo.json)",
  music: "Background Music",
};

function InfoRow({ label, value }: { label: string; value: string | number | boolean }) {
  return (
    <Box sx={{ display: "flex", gap: 1, alignItems: "baseline" }}>
      <Typography variant="caption" color="text.disabled" sx={{ minWidth: 100 }}>
        {label}
      </Typography>
      <Typography variant="caption" color="text.secondary" fontWeight={600}>
        {String(value)}
      </Typography>
    </Box>
  );
}

function FileResultRow({ result }: { result: FileValidationResult }) {
  const hasIssues = result.errors.length > 0 || result.warnings.length > 0;
  const hasInfo = Object.keys(result.info).length > 0;

  return (
    <Box
      sx={{
        p: 1.5,
        borderRadius: 2,
        border: `1px solid ${
          !result.valid
            ? "rgba(255,82,82,0.25)"
            : result.warnings.length > 0
            ? "rgba(255,179,0,0.2)"
            : "rgba(0,230,118,0.15)"
        }`,
        bgcolor: !result.valid
          ? "rgba(255,82,82,0.05)"
          : result.warnings.length > 0
          ? "rgba(255,179,0,0.04)"
          : "rgba(0,230,118,0.04)",
        mb: 1,
      }}
    >
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: hasIssues || hasInfo ? 1 : 0 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          {!result.valid ? (
            <ErrorIcon sx={{ fontSize: 16, color: "error.main" }} />
          ) : result.warnings.length > 0 ? (
            <WarnIcon sx={{ fontSize: 16, color: "warning.main" }} />
          ) : (
            <OkIcon sx={{ fontSize: 16, color: "success.main" }} />
          )}
          <Typography variant="body2" fontWeight={600}>
            {FILE_LABELS[result.file_type] || result.file_type}
          </Typography>
        </Box>
        <Chip
          label={!result.valid ? "Invalid" : result.warnings.length > 0 ? "Warnings" : "Valid"}
          size="small"
          sx={{
            height: 18,
            fontSize: "0.65rem",
            bgcolor: !result.valid
              ? "rgba(255,82,82,0.15)"
              : result.warnings.length > 0
              ? "rgba(255,179,0,0.15)"
              : "rgba(0,230,118,0.12)",
            color: !result.valid ? "error.main" : result.warnings.length > 0 ? "warning.main" : "success.main",
          }}
        />
      </Box>

      {result.errors.map((err, i) => (
        <Box key={i} sx={{ display: "flex", alignItems: "flex-start", gap: 0.75, mb: 0.25 }}>
          <ErrorIcon sx={{ fontSize: 12, color: "error.main", mt: 0.3, flexShrink: 0 }} />
          <Typography variant="caption" color="error.light">
            {err}
          </Typography>
        </Box>
      ))}

      {result.warnings.map((warn, i) => (
        <Box key={i} sx={{ display: "flex", alignItems: "flex-start", gap: 0.75, mb: 0.25 }}>
          <WarnIcon sx={{ fontSize: 12, color: "warning.main", mt: 0.3, flexShrink: 0 }} />
          <Typography variant="caption" color="warning.light">
            {warn}
          </Typography>
        </Box>
      ))}

      {hasInfo && (
        <Box sx={{ mt: 0.5, pl: 1, borderLeft: "2px solid rgba(255,255,255,0.06)" }}>
          {Object.entries(result.info).map(([k, v]) => (
            <InfoRow key={k} label={k.replace(/_/g, " ")} value={v} />
          ))}
        </Box>
      )}
    </Box>
  );
}

interface ValidationResultPanelProps {
  results: ValidationResults | null;
}

export default function ValidationResultPanel({ results }: ValidationResultPanelProps) {
  if (!results) return null;

  return (
    <Box sx={{ mt: 2 }}>
      <Alert
        severity={results.all_valid ? "success" : "error"}
        sx={{ mb: 2, borderRadius: 2 }}
        icon={results.all_valid ? <OkIcon /> : <ErrorIcon />}
      >
        {results.all_valid
          ? "All files validated — project is ready to generate"
          : "Validation failed — fix the issues below before generating"}
      </Alert>

      {Object.values(results.results).map((result) => (
        <FileResultRow key={result.file_type} result={result} />
      ))}
    </Box>
  );
}
