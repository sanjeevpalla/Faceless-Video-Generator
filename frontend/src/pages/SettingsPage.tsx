import React, { useState, useEffect } from "react";
import {
  Box,
  Typography,
  Button,
  Grid,
  TextField,
  Slider,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Divider,
  CircularProgress,
  Alert,
  Switch,
  FormControlLabel,
  Chip,
  LinearProgress,
  IconButton,
  ToggleButton,
  ToggleButtonGroup,
} from "@mui/material";
import {
  ExpandMore as ExpandIcon,
  Save as SaveIcon,
  RestartAlt as ResetIcon,
  AutoAwesome as FluxIcon,
  RecordVoiceOver as PiperIcon,
  VideoLibrary as VideoIcon,
  FolderOpen as OutputIcon,
  PictureInPictureAlt as NarratorIcon,
  AutoFixHigh as RemoveBgIcon,
  CheckCircle as CheckIcon,
  BrandingWatermark as LogoIcon,
  AutoAwesomeMotion as GeminiIcon,
  Visibility as ShowIcon,
  VisibilityOff as HideIcon,
  ImageSearch as ImageBackendIcon,
  Cloud as CloudIcon,
} from "@mui/icons-material";
import { useQuery, useMutation } from "@tanstack/react-query";
import { narratorApi } from "../api/narrator";
import { settingsApi, AppSettings, GoogleTTSSettings, SettingsUpdate, GeminiImageModel } from "../api/settings";

const SAMPLERS = ["euler", "euler_ancestral", "heun", "dpm_2", "dpm_2_ancestral", "lms", "dpm_fast", "dpm_adaptive"];
const GOOGLE_TTS_VOICES = [
  { value: "", label: "Auto (use project language default)" },
  { value: "en-US-Neural2-C", label: "en-US-Neural2-C (English US, Female)" },
  { value: "en-US-Neural2-A", label: "en-US-Neural2-A (English US, Male)" },
  { value: "te-IN-Standard-A", label: "te-IN-Standard-A (Telugu Standard, Female)" },
  { value: "te-IN-Standard-B", label: "te-IN-Standard-B (Telugu Standard, Male)" },
  { value: "hi-IN-Wavenet-A", label: "hi-IN-Wavenet-A (Hindi, Female)" },
  { value: "hi-IN-Wavenet-B", label: "hi-IN-Wavenet-B (Hindi, Male)" },
  { value: "ml-IN-Wavenet-A", label: "ml-IN-Wavenet-A (Malayalam, Female)" },
  { value: "ta-IN-Wavenet-A", label: "ta-IN-Wavenet-A (Tamil, Female)" },
  { value: "kn-IN-Wavenet-A", label: "kn-IN-Wavenet-A (Kannada, Female)" },
];
const SCHEDULERS = ["normal", "karras", "exponential", "sgm_uniform", "simple"];
const WHISPER_MODELS = ["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"];
const RESOLUTIONS = ["1920x1080", "1280x720", "3840x2160", "1080x1920"];
const VIDEO_TEMPLATES = ["documentary", "news", "technology", "finance", "educational", "history"];

export default function SettingsPage() {
  const { data: settings, isLoading, refetch } = useQuery({
    queryKey: ["settings"],
    queryFn: settingsApi.get,
  });

  const updateMutation = useMutation({
    mutationFn: settingsApi.update,
    onSuccess: () => {
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
      refetch();
    },
  });

  const resetMutation = useMutation({
    mutationFn: settingsApi.reset,
    onSuccess: () => refetch(),
  });

  const [localSettings, setLocalSettings] = useState<AppSettings | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [bgError, setBgError] = useState<string | null>(null);
  const [browseError, setBrowseError] = useState<string | null>(null);
  const [logoError, setLogoError] = useState<string | null>(null);
  const [showApiKey, setShowApiKey] = useState(false);
  const [showGoogleApiKey, setShowGoogleApiKey] = useState(false);
  const [imageModels, setImageModels] = useState<GeminiImageModel[]>([]);
  const [imageModelsError, setImageModelsError] = useState<string | null>(null);

  const fetchImageModelsMutation = useMutation({
    mutationFn: settingsApi.listGeminiImageModels,
    onSuccess: (data) => {
      setImageModels(data.models);
      setImageModelsError(null);
    },
    onError: (e: Error) => setImageModelsError(e.message),
  });

  const narratorClipsDir = localSettings?.video?.narrator_clips_dir ?? "";

  const { data: bgStatus, refetch: refetchBgStatus } = useQuery({
    queryKey: ["narrator-bg-status", narratorClipsDir],
    queryFn: () => narratorApi.bgStatus(narratorClipsDir || undefined),
    enabled: !!(localSettings?.video?.narrator_enabled && narratorClipsDir),
    refetchOnWindowFocus: false,
  });

  const removeBgMutation = useMutation({
    mutationFn: () => narratorApi.removeBackground(narratorClipsDir || undefined),
    onSuccess: () => { setBgError(null); refetchBgStatus(); },
    onError: (e: Error) => setBgError(e.message),
  });

  const { data: defaultDirData } = useQuery({
    queryKey: ["narrator-default-dir"],
    queryFn: async () => {
      const r = await import("../api/client").then(m => m.default.get("/settings/narrator-default-dir"));
      return r.data as { path: string };
    },
    staleTime: Infinity,
  });

  const browseMutation = useMutation({
    mutationFn: async () => {
      const r = await import("../api/client").then(m => m.default.post("/settings/browse-folder"));
      return r.data as { path: string };
    },
    onSuccess: (data) => {
      if (data.path) {
        updateVideo("narrator_clips_dir", data.path);
        setBrowseError(null);
      }
    },
    onError: (e: Error) => setBrowseError(e.message),
  });

  const browseLogoMutation = useMutation({
    mutationFn: async () => {
      const r = await import("../api/client").then(m => m.default.post("/settings/browse-logo"));
      return r.data as { path: string };
    },
    onSuccess: (data) => {
      if (data.path) {
        updateVideo("logo_path", data.path);
        setLogoError(null);
      }
    },
    onError: (e: Error) => setLogoError(e.message),
  });

  useEffect(() => {
    if (settings && !localSettings) {
      setLocalSettings(settings);
    }
  }, [settings]);

  const updateFlux = (key: string, value: unknown) => {
    if (!localSettings) return;
    setLocalSettings({ ...localSettings, flux: { ...localSettings.flux, [key]: value } });
  };

  const updatePiper = (key: string, value: unknown) => {
    if (!localSettings) return;
    setLocalSettings({ ...localSettings, piper: { ...localSettings.piper, [key]: value } });
  };

  const updateGoogleTTS = (key: keyof GoogleTTSSettings, value: unknown) => {
    if (!localSettings) return;
    setLocalSettings({ ...localSettings, google_tts: { ...localSettings.google_tts, [key]: value } });
  };

  const updateVideo = (key: string, value: unknown) => {
    if (!localSettings) return;
    setLocalSettings({ ...localSettings, video: { ...localSettings.video, [key]: value } });
  };

  const updateOutput = (key: string, value: unknown) => {
    if (!localSettings) return;
    setLocalSettings({ ...localSettings, output: { ...localSettings.output, [key]: value } });
  };

  const updateGemini = (key: string, value: unknown) => {
    if (!localSettings) return;
    setLocalSettings({ ...localSettings, gemini: { ...localSettings.gemini, [key]: value } });
  };

  const handleSave = () => {
    if (!localSettings) return;
    const update: SettingsUpdate = {
      flux: localSettings.flux,
      piper: localSettings.piper,
      google_tts: localSettings.google_tts,
      tts_engine: localSettings.tts_engine,
      video: localSettings.video,
      output: localSettings.output,
      gemini: localSettings.gemini,
      whisper_model: localSettings.whisper_model,
      whisper_language: localSettings.whisper_language,
      whisper_device: localSettings.whisper_device,
    };
    updateMutation.mutate(update);
  };

  if (isLoading || !localSettings) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 3 }}>
        <Box>
          <Typography variant="h4" fontWeight={800} gutterBottom>
            Settings
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Configure generation parameters
          </Typography>
        </Box>
        <Box sx={{ display: "flex", gap: 2 }}>
          <Button
            variant="outlined"
            startIcon={<ResetIcon />}
            onClick={() => resetMutation.mutate()}
            disabled={resetMutation.isPending}
            color="warning"
          >
            Reset Defaults
          </Button>
          <Button
            variant="contained"
            startIcon={updateMutation.isPending ? <CircularProgress size={16} /> : <SaveIcon />}
            onClick={handleSave}
            disabled={updateMutation.isPending}
          >
            Save Settings
          </Button>
        </Box>
      </Box>

      {saveSuccess && (
        <Alert severity="success" sx={{ mb: 2, borderRadius: 2 }}>
          Settings saved successfully!
        </Alert>
      )}

      {/* FLUX Settings */}
      <Accordion defaultExpanded>
        <AccordionSummary expandIcon={<ExpandIcon />}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
            <FluxIcon sx={{ color: "primary.main" }} />
            <Typography fontWeight={700}>FLUX Image Generation</Typography>
          </Box>
        </AccordionSummary>
        <AccordionDetails>
          <Grid container spacing={2.5}>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="ComfyUI URL"
                value={localSettings.flux.comfyui_url}
                onChange={(e) => updateFlux("comfyui_url", e.target.value)}
              />
            </Grid>
            <Grid item xs={12} sm={3}>
              <TextField
                fullWidth
                label="Width"
                type="number"
                value={localSettings.flux.width}
                onChange={(e) => updateFlux("width", parseInt(e.target.value))}
              />
            </Grid>
            <Grid item xs={12} sm={3}>
              <TextField
                fullWidth
                label="Height"
                type="number"
                value={localSettings.flux.height}
                onChange={(e) => updateFlux("height", parseInt(e.target.value))}
              />
            </Grid>
            <Grid item xs={12} sm={4}>
              <Box>
                <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                  <Typography variant="body2" fontWeight={600}>Steps</Typography>
                  <Typography variant="body2" color="primary.light" fontWeight={700}>{localSettings.flux.steps}</Typography>
                </Box>
                <Slider
                  value={localSettings.flux.steps}
                  onChange={(_, v) => updateFlux("steps", v)}
                  min={1} max={100} step={1}
                  marks={[{ value: 20, label: "20" }, { value: 50, label: "50" }]}
                />
              </Box>
            </Grid>
            <Grid item xs={12} sm={4}>
              <Box>
                <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                  <Typography variant="body2" fontWeight={600}>CFG Scale</Typography>
                  <Typography variant="body2" color="primary.light" fontWeight={700}>{localSettings.flux.cfg.toFixed(1)}</Typography>
                </Box>
                <Slider
                  value={localSettings.flux.cfg}
                  onChange={(_, v) => updateFlux("cfg", v)}
                  min={1} max={20} step={0.5}
                  marks={[{ value: 7, label: "7" }]}
                />
              </Box>
            </Grid>
            <Grid item xs={12} sm={2}>
              <FormControl fullWidth>
                <InputLabel>Sampler</InputLabel>
                <Select
                  value={localSettings.flux.sampler}
                  onChange={(e) => updateFlux("sampler", e.target.value)}
                  label="Sampler"
                >
                  {SAMPLERS.map((s) => <MenuItem key={s} value={s}>{s}</MenuItem>)}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={2}>
              <FormControl fullWidth>
                <InputLabel>Scheduler</InputLabel>
                <Select
                  value={localSettings.flux.scheduler}
                  onChange={(e) => updateFlux("scheduler", e.target.value)}
                  label="Scheduler"
                >
                  {SCHEDULERS.map((s) => <MenuItem key={s} value={s}>{s}</MenuItem>)}
                </Select>
              </FormControl>
            </Grid>
          </Grid>
        </AccordionDetails>
      </Accordion>

      {/* TTS Engine Selector */}
      <Box sx={{ px: 2, py: 1.5, mb: 0, border: "1px solid", borderColor: "divider", borderRadius: 2, display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap" }}>
        <Typography variant="body2" fontWeight={700} sx={{ minWidth: 100 }}>TTS Engine</Typography>
        <ToggleButtonGroup
          value={localSettings.tts_engine}
          exclusive
          onChange={(_, val) => val && setLocalSettings({ ...localSettings, tts_engine: val })}
          size="small"
        >
          <ToggleButton value="piper">
            <PiperIcon fontSize="small" sx={{ mr: 0.5 }} />
            Piper (Local)
          </ToggleButton>
          <ToggleButton value="google">
            <CloudIcon fontSize="small" sx={{ mr: 0.5 }} />
            Google Cloud TTS
          </ToggleButton>
        </ToggleButtonGroup>
        <Typography variant="caption" color="text.secondary">
          {localSettings.tts_engine === "google"
            ? "Uses Google Cloud TTS API — configure key below"
            : "Uses local Piper binary — no internet required"}
        </Typography>
      </Box>

      {/* Piper Settings */}
      <Accordion>
        <AccordionSummary expandIcon={<ExpandIcon />}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
            <PiperIcon sx={{ color: "secondary.main" }} />
            <Typography fontWeight={700}>Piper TTS Voice</Typography>
            {localSettings.tts_engine === "piper" && (
              <Chip label="Active" size="small" color="secondary" sx={{ ml: 1 }} />
            )}
          </Box>
        </AccordionSummary>
        <AccordionDetails>
          <Grid container spacing={2.5}>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Piper Executable Path"
                value={localSettings.piper.executable}
                onChange={(e) => updatePiper("executable", e.target.value)}
                placeholder="piper"
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Voice Model Path (.onnx)"
                value={localSettings.piper.model_path}
                onChange={(e) => updatePiper("model_path", e.target.value)}
                placeholder="/path/to/en_US-lessac-medium.onnx"
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Voice Name"
                value={localSettings.piper.voice}
                onChange={(e) => updatePiper("voice", e.target.value)}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <Box>
                <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                  <Typography variant="body2" fontWeight={600}>Speech Speed</Typography>
                  <Typography variant="body2" color="primary.light" fontWeight={700}>{localSettings.piper.speed.toFixed(1)}x</Typography>
                </Box>
                <Slider
                  value={localSettings.piper.speed}
                  onChange={(_, v) => updatePiper("speed", v)}
                  min={0.5} max={2.0} step={0.1}
                  marks={[{ value: 0.5, label: "0.5x" }, { value: 1.0, label: "1x" }, { value: 2.0, label: "2x" }]}
                />
              </Box>
            </Grid>
          </Grid>
        </AccordionDetails>
      </Accordion>

      {/* Google Cloud TTS Settings */}
      <Accordion>
        <AccordionSummary expandIcon={<ExpandIcon />}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
            <CloudIcon sx={{ color: "info.main" }} />
            <Typography fontWeight={700}>Google Cloud TTS</Typography>
            {localSettings.tts_engine === "google" && (
              <Chip label="Active" size="small" color="info" sx={{ ml: 1 }} />
            )}
          </Box>
        </AccordionSummary>
        <AccordionDetails>
          <Grid container spacing={2.5}>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="API Key"
                type={showGoogleApiKey ? "text" : "password"}
                value={localSettings.google_tts.api_key}
                onChange={(e) => updateGoogleTTS("api_key", e.target.value)}
                placeholder="AIza..."
                InputProps={{
                  endAdornment: (
                    <IconButton onClick={() => setShowGoogleApiKey((v) => !v)} edge="end" size="small">
                      {showGoogleApiKey ? <HideIcon /> : <ShowIcon />}
                    </IconButton>
                  ),
                }}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth>
                <InputLabel>Voice Name</InputLabel>
                <Select
                  value={localSettings.google_tts.voice_name || ""}
                  onChange={(e) => updateGoogleTTS("voice_name", e.target.value)}
                  label="Voice Name"
                >
                  {GOOGLE_TTS_VOICES.map((v) => (
                    <MenuItem key={v.value} value={v.value}>{v.label}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Language Code Override"
                value={localSettings.google_tts.language_code}
                onChange={(e) => updateGoogleTTS("language_code", e.target.value)}
                placeholder="e.g. te-IN (leave blank to use project language)"
                helperText="Overrides automatic language detection when set"
              />
            </Grid>
            <Grid item xs={12}>
              <Box>
                <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                  <Typography variant="body2" fontWeight={600}>Speaking Rate</Typography>
                  <Typography variant="body2" color="primary.light" fontWeight={700}>
                    {localSettings.google_tts.speaking_rate.toFixed(2)}x
                  </Typography>
                </Box>
                <Slider
                  value={localSettings.google_tts.speaking_rate}
                  onChange={(_, v) => updateGoogleTTS("speaking_rate", v as number)}
                  min={0.25} max={4.0} step={0.05}
                  marks={[{ value: 0.75, label: "0.75x" }, { value: 1.0, label: "1x" }, { value: 1.5, label: "1.5x" }]}
                />
              </Box>
            </Grid>
          </Grid>
          <Alert severity="info" sx={{ mt: 2 }}>
            Free tier: 1M chars/month (WaveNet/Neural2) or 4M chars/month (Standard voices).
            Get your API key from Google Cloud Console → Text-to-Speech API.
          </Alert>
        </AccordionDetails>
      </Accordion>

      {/* Video Settings */}
      <Accordion>
        <AccordionSummary expandIcon={<ExpandIcon />}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
            <VideoIcon sx={{ color: "warning.main" }} />
            <Typography fontWeight={700}>Video & Subtitles</Typography>
          </Box>
        </AccordionSummary>
        <AccordionDetails>
          <Grid container spacing={2.5}>
            <Grid item xs={6} sm={3}>
              <TextField
                fullWidth
                label="FPS"
                type="number"
                value={localSettings.video.fps}
                onChange={(e) => updateVideo("fps", parseInt(e.target.value))}
              />
            </Grid>
            <Grid item xs={6} sm={3}>
              <FormControl fullWidth>
                <InputLabel>Resolution</InputLabel>
                <Select
                  value={localSettings.video.resolution}
                  onChange={(e) => updateVideo("resolution", e.target.value)}
                  label="Resolution"
                >
                  {RESOLUTIONS.map((r) => <MenuItem key={r} value={r}>{r}</MenuItem>)}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={6} sm={3}>
              <FormControl fullWidth>
                <InputLabel>Template</InputLabel>
                <Select
                  value={localSettings.video.template}
                  onChange={(e) => updateVideo("template", e.target.value)}
                  label="Template"
                >
                  {VIDEO_TEMPLATES.map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={6} sm={3}>
              <FormControl fullWidth>
                <InputLabel>Whisper Model</InputLabel>
                <Select
                  value={localSettings.whisper_model}
                  onChange={(e) => setLocalSettings({ ...localSettings, whisper_model: e.target.value })}
                  label="Whisper Model"
                >
                  {WHISPER_MODELS.map((m) => <MenuItem key={m} value={m}>{m}</MenuItem>)}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6}>
              <Box>
                <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                  <Typography variant="body2" fontWeight={600}>Ken Burns Zoom Amount</Typography>
                  <Typography variant="body2" color="primary.light" fontWeight={700}>{(localSettings.video.zoom_amount * 100).toFixed(0)}%</Typography>
                </Box>
                <Slider
                  value={localSettings.video.zoom_amount}
                  onChange={(_, v) => updateVideo("zoom_amount", v)}
                  min={0} max={0.3} step={0.01}
                />
              </Box>
            </Grid>
            <Grid item xs={12} sm={6}>
              <Box>
                <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                  <Typography variant="body2" fontWeight={600}>Transition Duration</Typography>
                  <Typography variant="body2" color="primary.light" fontWeight={700}>{localSettings.video.transition_duration.toFixed(1)}s</Typography>
                </Box>
                <Slider
                  value={localSettings.video.transition_duration}
                  onChange={(_, v) => updateVideo("transition_duration", v)}
                  min={0} max={3} step={0.1}
                />
              </Box>
            </Grid>

            <Grid item xs={12} sm={4}>
              <FormControlLabel
                control={
                  <Switch
                    checked={localSettings.video.burn_subtitles ?? true}
                    onChange={(e) => updateVideo("burn_subtitles", e.target.checked)}
                    color="primary"
                  />
                }
                label={
                  <Typography variant="body2">
                    Burn subtitles into video
                  </Typography>
                }
              />
            </Grid>

            {/* Narrator overlay sub-section */}
            <Grid item xs={12}>
              <Divider sx={{ my: 1, borderColor: "rgba(255,255,255,0.07)" }} />
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2 }}>
                <NarratorIcon sx={{ fontSize: 18, color: "info.main" }} />
                <Typography variant="body2" fontWeight={700} color="info.main">
                  Narrator Overlay (PiP)
                </Typography>
              </Box>
            </Grid>

            <Grid item xs={12} sm={4}>
              <FormControlLabel
                control={
                  <Switch
                    checked={localSettings.video.narrator_enabled ?? false}
                    onChange={(e) => updateVideo("narrator_enabled", e.target.checked)}
                    color="info"
                  />
                }
                label={
                  <Typography variant="body2">
                    Enable narrator overlay
                  </Typography>
                }
              />
              <Typography variant="caption" color="text.disabled" display="block" sx={{ mt: 0.5 }}>
                Drop clips in project's narrator/ folder to auto-enable
              </Typography>
            </Grid>

            <Grid item xs={12} sm={8}>
              <TextField
                fullWidth
                label="Narrator Clips Folder"
                value={localSettings.video.narrator_clips_dir ?? ""}
                onChange={(e) => updateVideo("narrator_clips_dir", e.target.value)}
                placeholder={defaultDirData?.path ?? "D:\\narrator"}
                helperText="Path to folder with .mp4 clips — cycled and looped throughout the video"
                disabled={!(localSettings.video.narrator_enabled ?? false)}
                InputProps={{
                  endAdornment: (
                    <Box sx={{ display: "flex", gap: 0.5, ml: 1, flexShrink: 0 }}>
                      <Button
                        size="small"
                        variant="outlined"
                        color="info"
                        onClick={() => browseMutation.mutate()}
                        disabled={!(localSettings.video.narrator_enabled ?? false) || browseMutation.isPending}
                        sx={{ whiteSpace: "nowrap", minWidth: 0, px: 1 }}
                      >
                        {browseMutation.isPending ? <CircularProgress size={14} /> : "Browse…"}
                      </Button>
                      {defaultDirData?.path && (
                        <Button
                          size="small"
                          variant="text"
                          color="info"
                          onClick={() => updateVideo("narrator_clips_dir", defaultDirData.path)}
                          disabled={!(localSettings.video.narrator_enabled ?? false)}
                          sx={{ whiteSpace: "nowrap", minWidth: 0, px: 1 }}
                        >
                          Default
                        </Button>
                      )}
                    </Box>
                  ),
                }}
              />
              {browseError && (
                <Typography variant="caption" color="error">{browseError}</Typography>
              )}
            </Grid>

            <Grid item xs={12} sm={2}>
              <FormControl fullWidth disabled={!(localSettings.video.narrator_enabled ?? false)}>
                <InputLabel>Shape</InputLabel>
                <Select
                  value={localSettings.video.narrator_shape ?? "circle"}
                  onChange={(e) => updateVideo("narrator_shape", e.target.value)}
                  label="Shape"
                >
                  <MenuItem value="circle">Circle</MenuItem>
                  <MenuItem value="rectangle">Rectangle</MenuItem>
                </Select>
              </FormControl>
            </Grid>

            <Grid item xs={12} sm={2}>
              <FormControl fullWidth disabled={!(localSettings.video.narrator_enabled ?? false)}>
                <InputLabel>Position</InputLabel>
                <Select
                  value={localSettings.video.narrator_position ?? "bottom_right"}
                  onChange={(e) => updateVideo("narrator_position", e.target.value)}
                  label="Position"
                >
                  <MenuItem value="bottom_right">Bottom Right</MenuItem>
                  <MenuItem value="bottom_left">Bottom Left</MenuItem>
                  <MenuItem value="top_right">Top Right</MenuItem>
                  <MenuItem value="top_left">Top Left</MenuItem>
                </Select>
              </FormControl>
            </Grid>

            <Grid item xs={12} sm={3}>
              <Box sx={{ opacity: (localSettings.video.narrator_enabled ?? false) ? 1 : 0.4 }}>
                <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                  <Typography variant="body2" fontWeight={600}>Width (px)</Typography>
                  <Typography variant="body2" color="info.light" fontWeight={700}>{localSettings.video.narrator_width ?? 320}px</Typography>
                </Box>
                <Slider
                  value={localSettings.video.narrator_width ?? 320}
                  onChange={(_, v) => updateVideo("narrator_width", v)}
                  min={100} max={800} step={20}
                  marks={[{ value: 240, label: "240" }, { value: 320, label: "320" }, { value: 480, label: "480" }]}
                  disabled={!(localSettings.video.narrator_enabled ?? false)}
                />
              </Box>
            </Grid>

            <Grid item xs={12} sm={3}>
              <Box sx={{ opacity: (localSettings.video.narrator_enabled ?? false) ? 1 : 0.4 }}>
                <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                  <Typography variant="body2" fontWeight={600}>Side Margin</Typography>
                  <Typography variant="body2" color="info.light" fontWeight={700}>{localSettings.video.narrator_margin ?? 20}px</Typography>
                </Box>
                <Slider
                  value={localSettings.video.narrator_margin ?? 20}
                  onChange={(_, v) => updateVideo("narrator_margin", v)}
                  min={0} max={100} step={5}
                  disabled={!(localSettings.video.narrator_enabled ?? false)}
                />
              </Box>
            </Grid>

            <Grid item xs={12} sm={3}>
              <Box sx={{ opacity: (localSettings.video.narrator_enabled ?? false) ? 1 : 0.4 }}>
                <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                  <Typography variant="body2" fontWeight={600}>Bottom Margin</Typography>
                  <Typography variant="body2" color="info.light" fontWeight={700}>{localSettings.video.narrator_bottom_margin ?? 120}px</Typography>
                </Box>
                <Slider
                  value={localSettings.video.narrator_bottom_margin ?? 120}
                  onChange={(_, v) => updateVideo("narrator_bottom_margin", v)}
                  min={0} max={300} step={10}
                  marks={[{ value: 80, label: "above subs" }, { value: 120, label: "120" }]}
                  disabled={!(localSettings.video.narrator_enabled ?? false)}
                />
              </Box>
            </Grid>

            {/* Background removal */}
            {(localSettings.video.narrator_enabled ?? false) && narratorClipsDir && (
              <Grid item xs={12}>
                <Divider sx={{ my: 1, borderColor: "rgba(255,255,255,0.07)" }} />
                <Box sx={{ display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap" }}>
                  <Button
                    variant="outlined"
                    color="info"
                    size="small"
                    startIcon={removeBgMutation.isPending ? <CircularProgress size={14} color="inherit" /> : <RemoveBgIcon />}
                    onClick={() => removeBgMutation.mutate()}
                    disabled={removeBgMutation.isPending}
                  >
                    {removeBgMutation.isPending ? "Removing background…" : "Remove Background (AI)"}
                  </Button>

                  {bgStatus && (
                    <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                      <Chip
                        size="small"
                        icon={bgStatus.processed === bgStatus.total ? <CheckIcon /> : undefined}
                        label={`${bgStatus.processed} / ${bgStatus.total} clips processed`}
                        color={bgStatus.processed === bgStatus.total ? "success" : "default"}
                        variant="outlined"
                      />
                    </Box>
                  )}

                  <Typography variant="caption" color="text.disabled">
                    Runs rembg AI on each clip (~2 min). Saves *_nobg.webm next to originals.
                  </Typography>
                </Box>

                {removeBgMutation.isPending && (
                  <LinearProgress color="info" sx={{ mt: 1.5, borderRadius: 1 }} />
                )}

                {removeBgMutation.isSuccess && removeBgMutation.data && (
                  <Alert
                    severity={removeBgMutation.data.errors > 0 ? "warning" : "success"}
                    sx={{ mt: 1.5 }}
                    onClose={() => removeBgMutation.reset()}
                  >
                    {removeBgMutation.data.processed} clip(s) processed
                    {removeBgMutation.data.skipped > 0 && `, ${removeBgMutation.data.skipped} already done`}
                    {removeBgMutation.data.errors > 0 && `, ${removeBgMutation.data.errors} error(s)`}
                    {removeBgMutation.data.message && ` — ${removeBgMutation.data.message}`}
                  </Alert>
                )}

                {bgError && (
                  <Alert severity="error" sx={{ mt: 1.5 }} onClose={() => setBgError(null)}>
                    {bgError}
                  </Alert>
                )}
              </Grid>
            )}

            {/* Logo overlay sub-section */}
            <Grid item xs={12}>
              <Divider sx={{ my: 1, borderColor: "rgba(255,255,255,0.07)" }} />
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2 }}>
                <LogoIcon sx={{ fontSize: 18, color: "secondary.main" }} />
                <Typography variant="body2" fontWeight={700} color="secondary.main">
                  Logo Overlay (Top Right)
                </Typography>
              </Box>
            </Grid>

            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Logo Image Path"
                value={localSettings.video.logo_path ?? ""}
                onChange={(e) => updateVideo("logo_path", e.target.value)}
                placeholder="C:\path\to\logo.png"
                helperText="PNG with transparency recommended. Leave empty to disable."
                InputProps={{
                  endAdornment: (
                    <Button
                      size="small"
                      variant="outlined"
                      color="secondary"
                      onClick={() => browseLogoMutation.mutate()}
                      disabled={browseLogoMutation.isPending}
                      sx={{ whiteSpace: "nowrap", minWidth: 0, px: 1, ml: 1, flexShrink: 0 }}
                    >
                      {browseLogoMutation.isPending ? <CircularProgress size={14} /> : "Browse…"}
                    </Button>
                  ),
                }}
              />
              {logoError && (
                <Typography variant="caption" color="error">{logoError}</Typography>
              )}
            </Grid>

            <Grid item xs={12} sm={4}>
              <Box sx={{ opacity: (localSettings.video.logo_path ?? "") ? 1 : 0.4 }}>
                <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                  <Typography variant="body2" fontWeight={600}>Logo Size</Typography>
                  <Typography variant="body2" color="secondary.light" fontWeight={700}>
                    {((localSettings.video.logo_scale ?? 0.10) * 100).toFixed(0)}% of width
                  </Typography>
                </Box>
                <Slider
                  value={localSettings.video.logo_scale ?? 0.10}
                  onChange={(_, v) => updateVideo("logo_scale", v)}
                  min={0.02} max={0.5} step={0.01}
                  marks={[{ value: 0.10, label: "10%" }, { value: 0.20, label: "20%" }]}
                  color="secondary"
                  disabled={!(localSettings.video.logo_path ?? "")}
                />
              </Box>
            </Grid>

            <Grid item xs={12} sm={4}>
              <Box sx={{ opacity: (localSettings.video.logo_path ?? "") ? 1 : 0.4 }}>
                <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                  <Typography variant="body2" fontWeight={600}>Opacity</Typography>
                  <Typography variant="body2" color="secondary.light" fontWeight={700}>
                    {Math.round((localSettings.video.logo_opacity ?? 1.0) * 100)}%
                  </Typography>
                </Box>
                <Slider
                  value={localSettings.video.logo_opacity ?? 1.0}
                  onChange={(_, v) => updateVideo("logo_opacity", v)}
                  min={0} max={1} step={0.05}
                  marks={[{ value: 0.5, label: "50%" }, { value: 1, label: "100%" }]}
                  color="secondary"
                  disabled={!(localSettings.video.logo_path ?? "")}
                />
              </Box>
            </Grid>

            <Grid item xs={12} sm={4}>
              <Box sx={{ opacity: (localSettings.video.logo_path ?? "") ? 1 : 0.4 }}>
                <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                  <Typography variant="body2" fontWeight={600}>Corner Margin</Typography>
                  <Typography variant="body2" color="secondary.light" fontWeight={700}>
                    {localSettings.video.logo_margin ?? 20}px
                  </Typography>
                </Box>
                <Slider
                  value={localSettings.video.logo_margin ?? 20}
                  onChange={(_, v) => updateVideo("logo_margin", v)}
                  min={0} max={100} step={5}
                  color="secondary"
                  disabled={!(localSettings.video.logo_path ?? "")}
                />
              </Box>
            </Grid>
          </Grid>
        </AccordionDetails>
      </Accordion>

      {/* Gemini AI Settings */}
      <Accordion>
        <AccordionSummary expandIcon={<ExpandIcon />}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
            <GeminiIcon sx={{ color: "info.main" }} />
            <Typography fontWeight={700}>Gemini AI (Content + Image Generation)</Typography>
          </Box>
        </AccordionSummary>
        <AccordionDetails>
          <Grid container spacing={2.5}>
            <Grid item xs={12}>
              <Alert severity="info" sx={{ mb: 1 }}>
                Free tier via <strong>aistudio.google.com</strong>. Steps 1–2 use search grounding
                (1,500 RPD), Step 3 uses Script Model for reasoning, Step 4 (Scenes) + Step 7 (SEO) use Search Model, Steps 5–6 use Fast Model.
              </Alert>
            </Grid>

            {/* API Key */}
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Gemini API Key"
                type={showApiKey ? "text" : "password"}
                value={localSettings.gemini?.api_key ?? ""}
                onChange={(e) => updateGemini("api_key", e.target.value)}
                placeholder="AIza..."
                InputProps={{
                  endAdornment: (
                    <IconButton size="small" onClick={() => setShowApiKey(!showApiKey)}>
                      {showApiKey ? <HideIcon fontSize="small" /> : <ShowIcon fontSize="small" />}
                    </IconButton>
                  ),
                }}
              />
            </Grid>

            {/* Model fields */}
            <Grid item xs={12} sm={4}>
              <TextField
                fullWidth
                label="Search Model (Steps 1–2)"
                value={localSettings.gemini?.pro_model ?? "gemini-3-flash"}
                onChange={(e) => updateGemini("pro_model", e.target.value)}
                helperText="Trend discovery + research — needs Google Search grounding (1,500 RPD)"
              />
            </Grid>
            <Grid item xs={12} sm={4}>
              <TextField
                fullWidth
                label="Script Model (Step 3)"
                value={localSettings.gemini?.script_model ?? "gemma-4-31b-it"}
                onChange={(e) => updateGemini("script_model", e.target.value)}
                helperText="Documentary script generation — heavy reasoning (free via AI Studio)"
              />
            </Grid>
            <Grid item xs={12} sm={4}>
              <TextField
                fullWidth
                label="Fast Model (Steps 5–6)"
                value={localSettings.gemini?.flash_model ?? "gemini-3.1-flash-lite"}
                onChange={(e) => updateGemini("flash_model", e.target.value)}
                helperText="Image prompts + thumbnail — 1M context, ultra fast"
              />
            </Grid>

            {/* Search grounding toggle */}
            <Grid item xs={12} sm={6}>
              <FormControlLabel
                control={
                  <Switch
                    checked={localSettings.gemini?.search_grounding ?? true}
                    onChange={(e) => updateGemini("search_grounding", e.target.checked)}
                    color="info"
                  />
                }
                label={<Typography variant="body2">Google Search Grounding (Steps 1–2)</Typography>}
              />
              <Typography variant="caption" color="text.disabled" display="block">
                Enables live web search for trend discovery and research
              </Typography>
            </Grid>

            {/* Image backend divider */}
            <Grid item xs={12}>
              <Divider sx={{ my: 0.5, borderColor: "rgba(255,255,255,0.07)" }} />
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 1, mb: 0.5 }}>
                <ImageBackendIcon sx={{ fontSize: 18, color: "warning.main" }} />
                <Typography variant="body2" fontWeight={700} color="warning.main">
                  Image Generation Backend
                </Typography>
              </Box>
            </Grid>

            <Grid item xs={12} sm={6}>
              <Typography variant="body2" fontWeight={600} sx={{ mb: 1 }}>
                Choose backend for scene images &amp; thumbnails
              </Typography>
              <ToggleButtonGroup
                value={localSettings.gemini?.image_backend ?? "flux"}
                exclusive
                onChange={(_, v) => v && updateGemini("image_backend", v)}
                size="small"
                color="warning"
              >
                <ToggleButton value="flux">
                  <FluxIcon sx={{ mr: 0.75, fontSize: 16 }} />
                  FLUX (Local — ComfyUI)
                </ToggleButton>
                <ToggleButton value="gemini">
                  <GeminiIcon sx={{ mr: 0.75, fontSize: 16 }} />
                  Gemini (Cloud — Free tier)
                </ToggleButton>
              </ToggleButtonGroup>
              <Typography variant="caption" color="text.disabled" display="block" sx={{ mt: 0.75 }}>
                FLUX runs locally on your RTX 5060 Ti. Gemini uses the API (15 RPM / 1,500 RPD free).
              </Typography>
            </Grid>

            <Grid item xs={12} sm={6}>
              <Box sx={{ display: "flex", gap: 1, alignItems: "flex-start" }}>
                {imageModels.length > 0 ? (
                  <FormControl fullWidth disabled={(localSettings.gemini?.image_backend ?? "flux") === "flux"}>
                    <InputLabel>Gemini Image Model</InputLabel>
                    <Select
                      label="Gemini Image Model"
                      value={localSettings.gemini?.image_model ?? ""}
                      onChange={(e) => updateGemini("image_model", e.target.value)}
                    >
                      {imageModels.map((m) => (
                        <MenuItem key={m.name} value={m.name}>
                          <Box>
                            <Typography variant="body2">{m.name}</Typography>
                            {m.methods.includes("generateImages") && (
                              <Typography variant="caption" color="success.main">Imagen (native image gen)</Typography>
                            )}
                          </Box>
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                ) : (
                  <TextField
                    fullWidth
                    label="Gemini Image Model"
                    value={localSettings.gemini?.image_model ?? "gemini-2.5-flash-preview-image-generation"}
                    onChange={(e) => updateGemini("image_model", e.target.value)}
                    disabled={(localSettings.gemini?.image_backend ?? "flux") === "flux"}
                    helperText={imageModelsError
                      ? `Error: ${imageModelsError}`
                      : 'Click "Fetch" to discover available models'}
                    error={!!imageModelsError}
                  />
                )}
                <Button
                  variant="outlined"
                  size="small"
                  onClick={() => fetchImageModelsMutation.mutate()}
                  disabled={
                    fetchImageModelsMutation.isPending ||
                    (localSettings.gemini?.image_backend ?? "flux") === "flux" ||
                    !localSettings.gemini?.api_key
                  }
                  sx={{ mt: 1, flexShrink: 0, minWidth: 64, height: 40 }}
                >
                  {fetchImageModelsMutation.isPending
                    ? <CircularProgress size={14} />
                    : imageModels.length > 0 ? "Refetch" : "Fetch"}
                </Button>
              </Box>
            </Grid>
          </Grid>
        </AccordionDetails>
      </Accordion>

      {/* Output Settings */}
      <Accordion>
        <AccordionSummary expandIcon={<ExpandIcon />}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
            <OutputIcon sx={{ color: "success.main" }} />
            <Typography fontWeight={700}>Output Settings</Typography>
          </Box>
        </AccordionSummary>
        <AccordionDetails>
          <Grid container spacing={2.5}>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Export Folder"
                value={localSettings.output.export_folder}
                onChange={(e) => updateOutput("export_folder", e.target.value)}
                placeholder="Leave empty for default output folder"
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Naming Convention"
                value={localSettings.output.naming_convention}
                onChange={(e) => updateOutput("naming_convention", e.target.value)}
                placeholder="{project_name}_{timestamp}"
                helperText="Available: {project_name}, {timestamp}, {date}"
              />
            </Grid>
          </Grid>
        </AccordionDetails>
      </Accordion>
    </Box>
  );
}
