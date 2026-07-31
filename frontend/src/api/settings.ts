import apiClient from "./client";

export interface GeminiSettings {
  api_key: string;
  pro_model: string;       // Steps 1-2: search grounding (gemini-3-flash)
  script_model: string;    // Step 3: heavy reasoning (gemma-4-31b-it)
  flash_model: string;     // Steps 4-7: fast bulk text (gemini-3.1-flash-lite)
  image_model: string;     // Image generation via Gemini (gemini-3.1-flash-image)
  image_backend: string;   // "flux" | "gemini"
  search_grounding: boolean;
}

export interface FluxSettings {
  steps: number;
  cfg: number;
  sampler: string;
  scheduler: string;
  width: number;
  height: number;
  comfyui_url: string;
}

export interface PiperSettings {
  model_path: string;
  voice: string;
  speed: number;
  executable: string;
}

export interface GoogleTTSSettings {
  api_key: string;
  language_api_keys: Record<string, string>; // {lang_code: api_key} — dedicated key per language, for parallel voice synthesis
  voice_name: string;
  language_code: string;
  speaking_rate: number;
}

export interface SubtitleStyleSettings {
  font: string;
  font_size: number;
  color: string;
  stroke_color: string;
  stroke_width: number;
  position: string;
  background: boolean;
  background_color: string;
}

export interface VideoSettings {
  fps: number;
  resolution: string;
  codec: string;
  audio_codec: string;
  bitrate: string;
  audio_bitrate: string;
  zoom_amount: number;
  transition_duration: number;
  subtitle_style: SubtitleStyleSettings;
  template: string;
  burn_subtitles: boolean;
  narrator_enabled: boolean;
  narrator_clips_dir: string;
  narrator_position: string;
  narrator_width: number;
  narrator_margin: number;
  narrator_bottom_margin: number;
  narrator_shape: string;
  logo_path: string;
  logo_opacity: number;
  logo_scale: number;
  logo_margin: number;
}

export interface OutputSettings {
  export_folder: string;
  naming_convention: string;
  export_format: string;
}

export interface WhatsAppSettings {
  phone_number_id: string;
  access_token: string;
  webhook_verify_token: string;
  app_secret: string;
  recipient_number: string;
  enabled: boolean;
}

export interface YouTubeSettings {
  client_id: string;
  client_secret: string;
  refresh_token: string;
  channel_id: string;
  default_privacy_status: string; // "public" | "unlisted" | "private"
}

export interface AutomationSettings {
  deep_dive_enabled: boolean;
  deep_dive_cron: string;
  ai_news_enabled: boolean;
  ai_news_cron: string;
  default_language: string;
  languages: string[];
}

export interface AppSettings {
  flux: FluxSettings;
  piper: PiperSettings;
  google_tts: GoogleTTSSettings;
  tts_engine: string;
  default_voices: Record<string, string>;
  video: VideoSettings;
  output: OutputSettings;
  gemini: GeminiSettings;
  whisper_model: string;
  whisper_language: string;
  whisper_device: string;
  whatsapp: WhatsAppSettings;
  youtube: YouTubeSettings;
  automation: AutomationSettings;
}

export interface SettingsUpdate {
  flux?: Partial<FluxSettings>;
  piper?: Partial<PiperSettings>;
  google_tts?: Partial<GoogleTTSSettings>;
  tts_engine?: string;
  default_voices?: Record<string, string>;
  video?: Partial<VideoSettings>;
  output?: Partial<OutputSettings>;
  gemini?: Partial<GeminiSettings>;
  whisper_model?: string;
  whisper_language?: string;
  whisper_device?: string;
  whatsapp?: Partial<WhatsAppSettings>;
  youtube?: Partial<YouTubeSettings>;
  automation?: Partial<AutomationSettings>;
}

export interface GeminiImageModel {
  name: string;
  display_name: string;
  methods: string[];
  image_capable: boolean;
}

export interface PiperVoiceOption {
  id: string;
  label: string;
  quality: string;
  region: string;
}

export interface GoogleVoiceOption {
  id: string;
  label: string;
  gender: string;
  language_code: string;
}

export const settingsApi = {
  get: async (): Promise<AppSettings> => {
    const response = await apiClient.get("/settings");
    return response.data;
  },

  update: async (data: SettingsUpdate): Promise<AppSettings> => {
    const response = await apiClient.put("/settings", data);
    return response.data;
  },

  reset: async (): Promise<AppSettings> => {
    const response = await apiClient.post("/settings/reset");
    return response.data;
  },

  listGeminiImageModels: async (): Promise<{ models: GeminiImageModel[]; all_count: number }> => {
    const response = await apiClient.get("/settings/gemini/image-models");
    return response.data;
  },

  getPiperVoices: async (language: string): Promise<PiperVoiceOption[]> => {
    const response = await apiClient.get("/settings/voices/piper", { params: { language } });
    return response.data.voices;
  },

  getGoogleVoices: async (language: string): Promise<GoogleVoiceOption[]> => {
    const response = await apiClient.get("/settings/voices/google", { params: { language } });
    return response.data.voices;
  },
};

export const youtubeApi = {
  oauthStatus: async (): Promise<{ connected: boolean }> => {
    const response = await apiClient.get("/youtube/oauth/status");
    return response.data;
  },
};
