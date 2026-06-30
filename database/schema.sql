-- Faceless Video Generator - SQLite Schema
-- Version: 1.0.0

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA synchronous = NORMAL;

-- =============================================================================
-- Projects Table
-- =============================================================================
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'created'
        CHECK(status IN ('created', 'processing', 'completed', 'failed', 'archived')),
    description TEXT,
    created_at DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at DATETIME NOT NULL DEFAULT (datetime('now')),
    project_dir TEXT,
    input_files_status TEXT NOT NULL DEFAULT '{}',  -- JSON
    progress_state TEXT NOT NULL DEFAULT '{}',       -- JSON
    resume_state TEXT NOT NULL DEFAULT '{}'          -- JSON
);

CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);
CREATE INDEX IF NOT EXISTS idx_projects_created_at ON projects(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_projects_updated_at ON projects(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_projects_name ON projects(name);

-- Trigger to auto-update updated_at
CREATE TRIGGER IF NOT EXISTS projects_updated_at
AFTER UPDATE ON projects
FOR EACH ROW
BEGIN
    UPDATE projects SET updated_at = datetime('now') WHERE id = OLD.id;
END;

-- =============================================================================
-- Settings Table
-- =============================================================================
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY NOT NULL,
    value TEXT,                             -- JSON value
    updated_at DATETIME NOT NULL DEFAULT (datetime('now')),
    description TEXT,
    category TEXT
);

CREATE INDEX IF NOT EXISTS idx_settings_category ON settings(category);

-- =============================================================================
-- Jobs Table
-- =============================================================================
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY NOT NULL,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    job_type TEXT NOT NULL
        CHECK(job_type IN ('image', 'voice', 'subtitle', 'video', 'thumbnail', 'metadata')),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending', 'running', 'paused', 'completed', 'failed', 'cancelled')),
    created_at DATETIME NOT NULL DEFAULT (datetime('now')),
    started_at DATETIME,
    completed_at DATETIME,
    progress REAL NOT NULL DEFAULT 0.0,
    error_message TEXT,
    metadata TEXT NOT NULL DEFAULT '{}',    -- JSON
    priority REAL NOT NULL DEFAULT 0.0,
    retry_count REAL NOT NULL DEFAULT 0.0,
    max_retries REAL NOT NULL DEFAULT 3.0
);

CREATE INDEX IF NOT EXISTS idx_jobs_project_id ON jobs(project_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_job_type ON jobs(job_type);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_project_type ON jobs(project_id, job_type);

-- =============================================================================
-- Logs Table
-- =============================================================================
CREATE TABLE IF NOT EXISTS logs (
    id TEXT PRIMARY KEY NOT NULL,
    project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    level TEXT NOT NULL DEFAULT 'INFO'
        CHECK(level IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')),
    message TEXT NOT NULL,
    timestamp DATETIME NOT NULL DEFAULT (datetime('now')),
    context TEXT NOT NULL DEFAULT '{}',     -- JSON
    source TEXT,
    job_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_logs_project_id ON logs(project_id);
CREATE INDEX IF NOT EXISTS idx_logs_level ON logs(level);
CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_logs_job_id ON logs(job_id);

-- =============================================================================
-- Default Settings Seed Data
-- =============================================================================
INSERT OR IGNORE INTO settings (key, value, category, description) VALUES
    ('flux.steps', '20', 'flux', 'Number of diffusion steps'),
    ('flux.cfg', '7.0', 'flux', 'Classifier-free guidance scale'),
    ('flux.sampler', '"euler"', 'flux', 'Sampling algorithm'),
    ('flux.scheduler', '"normal"', 'flux', 'Noise scheduler'),
    ('flux.width', '1920', 'flux', 'Output image width'),
    ('flux.height', '1080', 'flux', 'Output image height'),
    ('flux.comfyui_url', '"http://127.0.0.1:8188"', 'flux', 'ComfyUI API base URL'),
    ('piper.model_path', '""', 'piper', 'Path to Piper ONNX model file'),
    ('piper.voice', '"en_US-lessac-medium"', 'piper', 'Voice identifier'),
    ('piper.speed', '1.0', 'piper', 'Speech speed multiplier'),
    ('piper.executable', '"piper"', 'piper', 'Piper executable name or path'),
    ('video.fps', '30', 'video', 'Output video frames per second'),
    ('video.resolution', '"1920x1080"', 'video', 'Output video resolution'),
    ('video.codec', '"libx264"', 'video', 'Video codec'),
    ('video.audio_codec', '"aac"', 'video', 'Audio codec'),
    ('video.bitrate', '"8000k"', 'video', 'Video bitrate'),
    ('video.audio_bitrate', '"192k"', 'video', 'Audio bitrate'),
    ('video.zoom_amount', '0.05', 'video', 'Ken Burns zoom amount (0-0.3)'),
    ('video.transition_duration', '0.5', 'video', 'Transition duration in seconds'),
    ('video.template', '"documentary"', 'video', 'Video style template'),
    ('output.export_folder', '""', 'output', 'Export output directory'),
    ('output.naming_convention', '"{project_name}_{timestamp}"', 'output', 'File naming pattern'),
    ('output.export_format', '"mp4"', 'output', 'Output file format'),
    ('whisper.model', '"base"', 'whisper', 'Whisper model size'),
    ('whisper.language', '"en"', 'whisper', 'Transcription language'),
    ('whisper.device', '"cpu"', 'whisper', 'Compute device (cpu/cuda)');
