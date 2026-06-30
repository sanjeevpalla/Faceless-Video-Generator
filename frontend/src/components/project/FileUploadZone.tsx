import React, { useCallback, useState } from "react";
import { Box, Typography, LinearProgress, CircularProgress } from "@mui/material";
import { CloudUpload as UploadIcon } from "@mui/icons-material";

interface FileUploadZoneProps {
  fileType: string;
  acceptedExtensions: string[];
  onFileSelected: (file: File) => Promise<void>;
  disabled?: boolean;
  label?: string;
  description?: string;
}

export default function FileUploadZone({
  fileType,
  acceptedExtensions,
  onFileSelected,
  disabled = false,
  label,
  description,
}: FileUploadZoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const inputRef = React.useRef<HTMLInputElement>(null);

  const acceptStr = acceptedExtensions.map((e) => (e.startsWith(".") ? e : `.${e}`)).join(",");

  const handleFile = useCallback(
    async (file: File) => {
      const ext = `.${file.name.split(".").pop()?.toLowerCase()}`;
      if (acceptedExtensions.length > 0 && !acceptedExtensions.includes(ext)) {
        setError(`Invalid file type. Expected: ${acceptedExtensions.join(", ")}`);
        return;
      }
      setError(null);
      setIsUploading(true);
      setUploadProgress(0);
      try {
        await onFileSelected(file);
        setUploadProgress(100);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : "Upload failed");
      } finally {
        setIsUploading(false);
      }
    },
    [acceptedExtensions, onFileSelected]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      if (disabled || isUploading) return;
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [disabled, isUploading, handleFile]
  );

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    if (!disabled && !isUploading) setIsDragging(true);
  };

  const handleDragLeave = () => setIsDragging(false);

  const handleClick = () => {
    if (!disabled && !isUploading) inputRef.current?.click();
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <Box
      onClick={handleClick}
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      sx={{
        border: `2px dashed ${
          isDragging
            ? "rgba(108,99,255,0.8)"
            : error
            ? "rgba(255,82,82,0.4)"
            : "rgba(255,255,255,0.12)"
        }`,
        borderRadius: 2,
        p: 2.5,
        textAlign: "center",
        cursor: disabled || isUploading ? "not-allowed" : "pointer",
        bgcolor: isDragging
          ? "rgba(108,99,255,0.06)"
          : "rgba(255,255,255,0.02)",
        transition: "all 0.2s ease",
        opacity: disabled ? 0.5 : 1,
        "&:hover": {
          borderColor: disabled ? undefined : "rgba(108,99,255,0.5)",
          bgcolor: disabled ? undefined : "rgba(108,99,255,0.04)",
        },
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept={acceptStr}
        hidden
        onChange={handleInputChange}
        disabled={disabled || isUploading}
      />

      {isUploading ? (
        <Box>
          <CircularProgress size={24} sx={{ mb: 1 }} />
          <Typography variant="caption" display="block" color="text.secondary">
            Uploading...
          </Typography>
          <LinearProgress
            variant="determinate"
            value={uploadProgress}
            sx={{ mt: 1, height: 4 }}
          />
        </Box>
      ) : (
        <Box>
          <UploadIcon sx={{ color: isDragging ? "primary.main" : "text.disabled", mb: 0.5, fontSize: 28 }} />
          <Typography variant="body2" fontWeight={600}>
            {label || `Upload ${fileType}`}
          </Typography>
          {description && (
            <Typography variant="caption" color="text.secondary" display="block">
              {description}
            </Typography>
          )}
          <Typography variant="caption" color="text.disabled" display="block" sx={{ mt: 0.5 }}>
            {acceptedExtensions.join(", ")}
          </Typography>
        </Box>
      )}

      {error && (
        <Typography variant="caption" color="error.main" sx={{ display: "block", mt: 0.5 }}>
          {error}
        </Typography>
      )}
    </Box>
  );
}
