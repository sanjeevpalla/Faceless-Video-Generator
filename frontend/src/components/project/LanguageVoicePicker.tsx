import React from "react";
import { FormControl, InputLabel, Select, MenuItem, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { settingsApi } from "../../api/settings";

interface LanguageVoicePickerProps {
  language: string;
  languageLabel: string;
  engine: "piper" | "google";
  value: string; // "" = auto (default)
  onChange: (voiceId: string) => void;
  disabled?: boolean;
  /** Overrides the "no voice available" message — use this to explain a
   * setup step (e.g. missing API key) instead of implying no voices exist. */
  emptyReason?: string;
}

export default function LanguageVoicePicker({
  language,
  languageLabel,
  engine,
  value,
  onChange,
  disabled,
  emptyReason,
}: LanguageVoicePickerProps) {
  const { data: voices, isLoading } = useQuery({
    queryKey: ["voice-catalog", engine, language],
    queryFn: async (): Promise<{ id: string; label: string }[]> =>
      engine === "google"
        ? await settingsApi.getGoogleVoices(language)
        : await settingsApi.getPiperVoices(language),
    staleTime: 5 * 60_000,
  });

  const options = voices || [];

  if (!isLoading && options.length === 0) {
    return (
      <Typography variant="caption" color="text.disabled" sx={{ display: "block", py: 1 }}>
        {languageLabel}: {emptyReason ||
          `no ${engine === "google" ? "Google TTS" : "Piper"} voice available — will use the default.`}
      </Typography>
    );
  }

  return (
    <FormControl fullWidth size="small" sx={{ mb: 1 }} disabled={disabled || isLoading}>
      <InputLabel>{languageLabel} voice</InputLabel>
      <Select value={value || ""} label={`${languageLabel} voice`} onChange={(e) => onChange(e.target.value)}>
        <MenuItem value="">Auto (default)</MenuItem>
        {options.map((v) => (
          <MenuItem key={v.id} value={v.id}>
            {v.label}
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );
}
