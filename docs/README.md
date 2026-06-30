# Faceless Video Generator

A desktop application for generating AI-powered faceless YouTube videos using FLUX Dev image generation, Piper TTS narration, Whisper subtitles, and MoviePy video assembly.

## Features

- **AI Image Generation** — Generate scene images using FLUX Dev via ComfyUI
- **Text-to-Speech** — High-quality narration with Piper TTS
- **Auto Subtitles** — Transcribe audio with OpenAI Whisper
- **Video Assembly** — Ken Burns effects, transitions, subtitle burning with MoviePy
- **Thumbnail Generation** — AI-generated YouTube thumbnails via FLUX Dev
- **SEO Metadata** — Auto-generate YouTube metadata from SEO JSON
- **Real-time Progress** — WebSocket-based live progress streaming
- **Project Management** — Full CRUD with resume/checkpoint support
- **Dark UI** — Material UI v5 dark theme desktop app via Tauri

## Architecture

```
┌─────────────────────────────────────────────┐
│  Tauri Desktop Shell (Rust)                 │
│  ┌─────────────────────────────────────┐    │
│  │  React + MUI v5 Frontend            │    │
│  │  Zustand + React Query              │    │
│  └───────────────┬─────────────────────┘    │
│                  │ HTTP + WebSocket          │
│  ┌───────────────▼─────────────────────┐    │
│  │  FastAPI Backend (Python)           │    │
│  │  SQLAlchemy + SQLite                │    │
│  │  Async Job Queue                    │    │
│  └──┬────────┬──────────┬─────────┬───┘    │
│     │        │          │         │         │
│  ComfyUI  Piper TTS  Whisper  MoviePy       │
│  (FLUX)   (Voice)    (STT)   (Video)        │
└─────────────────────────────────────────────┘
```

## Prerequisites

Before installing, ensure the following are available:

| Dependency | Version | Notes |
|-----------|---------|-------|
| Python | 3.11+ | Backend runtime |
| Node.js | 18+ | Frontend build |
| Rust | 1.70+ | Tauri compilation |
| FFmpeg | 6.0+ | Video/audio processing |
| ComfyUI | Latest | FLUX image generation |
| Piper TTS | Latest | Voice synthesis |

### Installing ComfyUI

```bash
git clone https://github.com/comfyanonymous/ComfyUI.git
cd ComfyUI
pip install -r requirements.txt
# Download FLUX Dev model to models/checkpoints/flux1-dev.safetensors
python main.py --listen 127.0.0.1 --port 8188
```

### Installing Piper TTS

```bash
pip install piper-tts
# Or download binary from https://github.com/rhasspy/piper/releases
# Download voice model: en_US-lessac-medium.onnx
```

### Installing FFmpeg

- **Windows**: Download from https://ffmpeg.org/download.html, add to PATH
- **macOS**: `brew install ffmpeg`
- **Linux**: `sudo apt install ffmpeg`

## Installation

### 1. Clone / Download

```bash
cd "D:\Faceless Video Generator"
```

### 2. Backend Setup

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Frontend Setup

```bash
cd frontend
npm install
```

### 4. Configuration

Edit `config/default.json` to set your paths:

```json
{
  "COMFYUI_URL": "http://127.0.0.1:8188",
  "PIPER_MODEL_PATH": "C:/path/to/en_US-lessac-medium.onnx",
  "PIPER_EXECUTABLE": "piper",
  "WHISPER_MODEL": "base"
}
```

## Running the Application

### Development Mode

**Terminal 1 — Backend:**
```bash
cd backend
venv\Scripts\activate   # Windows
python run.py
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm run dev
```

The app runs at http://localhost:1420

### Tauri Desktop Build

```bash
cd frontend
npm run tauri build
```

## Usage Guide

### 1. Create a Project

- Open the Dashboard
- Click **New Project**
- Enter a project name and description

### 2. Upload Input Files

Navigate to **Project** and upload all 6 required files:

| File | Format | Description |
|------|--------|-------------|
| `script.txt` | .txt, .md | Full video script |
| `scenes.json` | .json, .txt | Scene breakdown |
| `narration.txt` | .txt, .json | Per-scene narration text |
| `music.mp3` | .mp3, .wav | Background music |
| `seo.json` | .json | Title, description, tags |
| `prompts.json` | .json | FLUX image prompts per scene |

#### prompts.json Format

```json
{
  "scenes": [
    {
      "id": 1,
      "prompt": "Futuristic cityscape at sunset, cinematic lighting, 4K",
      "negative_prompt": "blurry, watermark, text"
    }
  ],
  "thumbnail_prompt": "Eye-catching YouTube thumbnail, dramatic AI robot"
}
```

#### seo.json Format

```json
{
  "title": "The Future of AI in 2025",
  "description": "Explore how artificial intelligence is transforming...",
  "tags": ["AI", "technology", "future", "2025"],
  "category_id": "28",
  "thumbnail_prompt": "Futuristic AI thumbnail with neural network visualization"
}
```

### 3. Generate Content

Work through each generation step in order:

1. **Images** — Generate scene images (requires ComfyUI + FLUX)
2. **Voice** — Generate narration audio (requires Piper TTS)
3. **Subtitles** — Transcribe audio (requires Whisper)
4. **Thumbnail** — Generate YouTube thumbnail
5. **Video** — Assemble final video
6. **Metadata** — Generate YouTube metadata

### 4. Export

- Download the final MP4 from the **Video** page
- Find `youtube_metadata.json` and `description.txt` in the project output folder

## Project Structure

```
project_id/
├── input/          # Uploaded input files
│   ├── script.txt
│   ├── scenes.json
│   ├── narration.txt
│   ├── music.mp3
│   ├── seo.json
│   └── prompts.json
├── images/         # Generated scene images
├── audio/          # Generated voice files
├── subtitles/      # SRT and VTT files
├── thumbnail/      # Thumbnail image
├── output/         # Final video + metadata
└── cache/          # Cached generation results
```

## API Reference

The backend exposes a REST API at `http://localhost:8000/api/v1`:

- `GET /api/v1/projects` — List projects
- `POST /api/v1/projects` — Create project
- `GET /api/v1/projects/{id}` — Get project
- `POST /api/v1/projects/{id}/files/{type}` — Upload file
- `POST /api/v1/jobs/trigger/{project_id}/{job_type}` — Trigger generation
- `GET /api/v1/settings` — Get settings
- `PUT /api/v1/settings` — Update settings

WebSocket endpoint: `ws://localhost:8000/ws/{project_id}`

Full API docs: http://localhost:8000/docs

## Settings Reference

| Setting | Default | Description |
|---------|---------|-------------|
| `flux.steps` | 20 | FLUX diffusion steps (higher = better quality, slower) |
| `flux.cfg` | 7.0 | Guidance scale (how closely to follow the prompt) |
| `flux.sampler` | euler | Sampling algorithm |
| `video.fps` | 30 | Output video framerate |
| `video.template` | documentary | Visual style template |
| `video.zoom_amount` | 0.05 | Ken Burns zoom intensity |
| `piper.speed` | 1.0 | Speech rate multiplier |
| `whisper.model` | base | Whisper model size (tiny/base/small/medium/large) |

## Troubleshooting

**ComfyUI not connecting:**
- Ensure ComfyUI is running: `python main.py --listen 127.0.0.1 --port 8188`
- Check the URL in Settings matches exactly

**Piper not found:**
- Set the full path to the piper executable in Settings
- Ensure the ONNX model path is correct

**FFmpeg not found:**
- Add FFmpeg to your system PATH
- Verify with: `ffmpeg -version`

**Slow image generation:**
- Reduce FLUX steps (try 15-20)
- Enable GPU if available in ComfyUI

**Out of memory:**
- Use a smaller Whisper model (tiny or base)
- Reduce FLUX resolution

## License

MIT License — See LICENSE file for details.
