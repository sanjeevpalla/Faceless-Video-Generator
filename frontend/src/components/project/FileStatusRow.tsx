import React, { useState } from "react";
import {
  Box,
  Typography,
  IconButton,
  Tooltip,
  LinearProgress,
  Collapse,
} from "@mui/material";
import {
  CloudUpload as UploadIcon,
  Delete as DeleteIcon,
  CheckCircle as CheckIcon,
  Error as ErrorIcon,
  InsertDriveFile as FileIcon,
} from "@mui/icons-material";
import StatusBadge from "../common/StatusBadge";
import { FileStatusDetail } from "../../store/projectStore";

interface FileStatusRowProps {
  fileType: string;
  label: string;
  expectedTypes: string[];
  statusDetail: FileStatusDetail;
  onUpload: (file: File) => Promise<void>;
  onDelete: () => void;
  disabled?: boolean;
}

export default function FileStatusRow({
  fileType,
  label,
  expectedTypes,
  statusDetail,
  onUpload,
  onDelete,
  disabled = false,
}: FileStatusRowProps) {
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [dragOver, setDragOver] = useState(false);

  const inputRef = React.useRef<HTMLInputElement>(null);
  const acceptStr = expectedTypes.map((e) => (e.startsWith(".") ? e : `.${e}`)).join(",");

  const handleFile = async (file: File) => {
    setIsUploading(true);
    setUploadProgress(0);
    try {
      await onUpload(file);
    } finally {
      setIsUploading(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (disabled || isUploading) return;
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  const formatBytes = (bytes: number | null) => {
    if (!bytes) return "";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const isReady = statusDetail.status === "ready";

  return (
    <Box
      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      sx={{
        display: "flex",
        alignItems: "center",
        gap: 1.5,
        py: 1.25,
        px: 1.5,
        borderRadius: 2,
        border: `1px solid ${dragOver ? "rgba(108,99,255,0.5)" : "rgba(255,255,255,0.06)"}`,
        bgcolor: dragOver ? "rgba(108,99,255,0.06)" : "transparent",
        transition: "all 0.15s ease",
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept={acceptStr}
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleFile(file);
          if (inputRef.current) inputRef.current.value = "";
        }}
      />

      {/* Status Icon */}
      <Box sx={{ flexShrink: 0 }}>
        {isReady ? (
          <CheckIcon sx={{ color: "success.main", fontSize: 20 }} />
        ) : statusDetail.status === "failed" ? (
          <ErrorIcon sx={{ color: "error.main", fontSize: 20 }} />
        ) : (
          <FileIcon sx={{ color: "text.disabled", fontSize: 20 }} />
        )}
      </Box>

      {/* File Info */}
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography variant="body2" fontWeight={600}>
          {label}
        </Typography>
        {isReady && statusDetail.filename ? (
          <Typography variant="caption" color="text.secondary" noWrap display="block">
            {statusDetail.filename}
            {statusDetail.size && ` · ${formatBytes(statusDetail.size)}`}
          </Typography>
        ) : (
          <Typography variant="caption" color="text.disabled" display="block">
            {expectedTypes.join(", ")} · Drag & drop or click upload
          </Typography>
        )}
        <Collapse in={isUploading}>
          <LinearProgress sx={{ mt: 0.5, height: 2 }} />
        </Collapse>
      </Box>

      {/* Status Badge */}
      <StatusBadge status={statusDetail.status} size="small" />

      {/* Actions */}
      <Box sx={{ flexShrink: 0, display: "flex", gap: 0.25 }}>
        <Tooltip title={isReady ? "Replace file" : "Upload file"}>
          <IconButton
            size="small"
            onClick={() => inputRef.current?.click()}
            disabled={disabled || isUploading}
            color={isReady ? "default" : "primary"}
            sx={{ color: isReady ? "text.secondary" : undefined }}
          >
            <UploadIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        {isReady && (
          <Tooltip title="Remove file">
            <IconButton
              size="small"
              onClick={onDelete}
              disabled={disabled}
              color="error"
            >
              <DeleteIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        )}
      </Box>
    </Box>
  );
}
