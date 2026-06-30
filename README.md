# Faceless Video Generator

A production-grade desktop application for automated faceless YouTube-style video generation. Converts user-prepared content assets into professional documentary-style videos using 100% local AI — no paid APIs.

![Stack](https://img.shields.io/badge/Stack-React%20%2B%20FastAPI%20%2B%20Tauri-6C63FF)
![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![Tests](https://img.shields.io/badge/Tests-203%20passing-00E676)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## What It Does

| Step | Tool | Description |
|---|---|---|
| 1 | Gemini AI | Generate script, scenes.json, image prompts, SEO metadata |
| 2 | FLUX Dev (ComfyUI) | Generate scene images + thumbnail |
| 3 | Piper TTS | Generate narration audio per scene |
| 4 | Whisper | Transcribe audio → SRT / VTT subtitles |
| 5 | MoviePy + FFmpeg | Assemble final MP4 with Ken Burns, transitions, music |
| 6 | rembg | Background removal for narrator overlay clips |
| 7 | deep-translator | Free Google Translate (no API key) for multi-language support |
| 8 | App | Generate YouTube metadata from seo.json |

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│  Tauri Desktop Shell  (Rust 1.70+)              │
│  ┌───────────────────────────────────────────┐  │
│  │  React 18 + Material UI v5  (TypeScript)  │  │
│  │  Zustand · React Query · Vite             │  │
│  └──────────────────┬────────────────────────┘  │
│                     │ HTTP + WebSocket           │
│  ┌──────────────────▼────────────────────────┐  │
│  │  FastAPI  (Python 3.11+)                  │  │
│  │  SQLAlchemy Async · SQLite · aiosqlite    │  │
│  │  Async Job Queue · WebSocket broadcasts   │  │
│  └──────┬──────────────────────┬─────────────┘  │
│         │                      │                 │
│  ┌──────▼──────┐   ┌──────────▼────────────┐    │
│  │  ComfyUI    │   │  Local Models          │    │
│  │  FLUX Dev   │   │  Piper TTS  (.onnx)   │    │
│  │  port 8188  │   │  Whisper  (base/small) │    │
│  └─────────────┘   └───────────────────────┘    │
└─────────────────────────────────────────────────┘
```

---

## Prerequisites

### System dependencies (install before anything else)

| Dependency | Version | Download |
|---|---|---|
| Python | 3.11+ | https://python.org |
| Node.js | 18+ | https://nodejs.org |
| Rust | 1.70+ | https://rustup.rs |
| FFmpeg | 6.0+ | https://ffmpeg.org/download.html |
| ComfyUI | Latest | https://github.com/comfyanonymous/ComfyUI |
| Piper TTS | Latest | https://github.com/rhasspy/piper/releases |

### AI models (download separately)

| Model | Purpose | Notes |
|---|---|---|
| `flux1-dev.safetensors` | Image generation | Place in ComfyUI `models/checkpoints/` |
| `en_US-lessac-medium.onnx` | Narration voice | Place anywhere; set path in Settings |
| Whisper `base` | Subtitles | Auto-downloaded on first use |

---

## Quick Start

> For a complete step-by-step guide including binary installs and model downloads, see [`docs/local-setup.md`](docs/local-setup.md).

### 1. Clone / extract the project

```bash
cd "D:\Faceless Video Generator"
```

### 2. Install backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Install frontend

```powershell
cd frontend
npm install
```

### 4. Set Gemini API key

The content-generation pipeline (script, scenes, prompts, SEO) uses Google Gemini:

```powershell
$env:GEMINI_API_KEY = "your-key-here"
```

Get a free key at https://aistudio.google.com/app/apikey.

### 5. Start ComfyUI (for image generation)

```powershell
# In a separate terminal — must be running before generating images
cd C:\path\to\ComfyUI
python main.py --listen 127.0.0.1 --port 8188
```

### 6. Run the app

**One-click (recommended):**
```
start.bat
```
Opens backend (port 8000) and frontend (port 1420) in separate terminal windows.

**Or manually — Terminal 1 (Backend):**
```powershell
cd backend && .venv\Scripts\activate && python run.py
```

**Terminal 2 (Frontend):**
```powershell
cd frontend && npm run dev
```

Open `http://localhost:1420`, or run the Tauri desktop shell:

```powershell
cd frontend && npm run tauri dev
```

### 7. Configure settings

Open **Settings** in the app:
- **Piper executable path** — e.g. `C:\piper\piper.exe`
- **Piper model path** — e.g. `models\piper\en_US-lessac-medium.onnx`
- **ComfyUI URL** — default `http://127.0.0.1:8188`
- **Whisper model** — `base` (fast) or `small` / `medium` (more accurate)

---

## Workflow

### Prepare your input files (using Gemini or manually)

| File | Description |
|---|---|
| `script.md` | Full video script |
| `scenes.json` | Scene breakdown with narration per scene |
| `image_prompts.txt` | One FLUX prompt per line (one per scene) |
| `thumbnail_prompt.txt` | Single FLUX prompt for the thumbnail |
| `seo.json` | Title, description, tags, chapters |
| `bg_music.mp3` | Background music track |

### scenes.json format

```json
{
  "video_title": "The Rise of Artificial Intelligence",
  "total_duration": 600,
  "scenes": [
    {
      "scene_id": 1,
      "title": "Opening Hook",
      "image_file": "scene_001.png",
      "duration": 12,
      "narration": "In the next decade, artificial intelligence will reshape every industry...",
      "visual_description": "Cinematic shot of a futuristic city at dawn"
    }
  ]
}
```

### seo.json format

```json
{
  "title": "The Rise of AI — Complete Documentary 2025",
  "description": "A comprehensive look at how artificial intelligence is changing the world...",
  "tags": ["artificial intelligence", "AI documentary", "machine learning"],
  "hashtags": ["#AI", "#Technology"],
  "chapters": [
    {"timestamp": "0:00", "title": "Introduction"},
    {"timestamp": "2:30", "title": "Machine Learning Basics"}
  ]
}
```

### Generation steps

1. **Dashboard** → New Project → enter name
2. **Project** tab → upload all 6 files → Validate Files
3. **Images** → Generate All (requires ComfyUI running)
4. **Voice** → Generate Voice (requires Piper configured)
5. **Subtitles** → Generate Subtitles (Whisper auto-downloads model)
6. **Thumbnail** → Generate Thumbnail
7. **Video** → select template → Render Video
8. **Video → Metadata tab** → Generate metadata → Copy All → paste into YouTube Studio

---

## Project Structure

```
Faceless Video Generator/
├── backend/                 # FastAPI Python backend
│   ├── app/
│   │   ├── api/             # REST endpoints + WebSocket
│   │   ├── core/            # Logging, events, exceptions, progress
│   │   ├── models/          # SQLAlchemy ORM models
│   │   ├── repositories/    # Async DB access layer
│   │   ├── schemas/         # Pydantic v2 schemas
│   │   ├── services/        # Generation services (image/voice/video...)
│   │   └── workers/         # Async job queue manager
│   ├── tests/               # 203 pytest tests
│   └── requirements.txt
├── frontend/                # React + TypeScript + MUI
│   └── src/
│       ├── api/             # Axios API clients per domain
│       ├── components/      # Reusable UI components
│       ├── hooks/           # React Query + custom hooks
│       ├── pages/           # 8 application pages
│       └── store/           # Zustand global state
├── src-tauri/               # Tauri Rust shell
├── projects/                # Per-project data (created at runtime)
├── config/
│   └── default.json         # Default backend configuration
├── models/
│   └── piper/               # Place .onnx voice model here
├── output/                  # Final rendered videos
└── docs/                    # local-setup.md, developer_guide.md, troubleshooting.md
```

---

## API Reference

The FastAPI backend exposes full Swagger docs at `http://localhost:8000/docs`.

Key endpoint groups:

| Prefix | Purpose |
|---|---|
| `/api/v1/projects` | Project CRUD + file uploads + validate |
| `/api/v1/images` | Scene image status, serving, regeneration |
| `/api/v1/voice` | Audio files, merged narration, Piper status |
| `/api/v1/subtitles` | SRT/VTT download, Whisper status |
| `/api/v1/video` | Render status, MP4 serving, FFmpeg check |
| `/api/v1/thumbnail` | Thumbnail status, serving, regeneration |
| `/api/v1/metadata` | SEO data, YouTube metadata, copy text |
| `/api/v1/queue` | Job queue status, pause/resume/cancel |
| `/api/v1/settings` | App settings CRUD |
| `/ws/{project_id}` | WebSocket progress stream |

---

## Running Tests

```bash
cd backend
python -m pytest tests/ -v
# 203 tests, ~5 seconds
```

Tests use in-memory SQLite and mock services — no GPU, Piper, Whisper, FFmpeg, or ComfyUI required.

---

## Building for Production

### Package as Tauri desktop app

```bash
cd frontend
npm run tauri build
```

Output: `src-tauri/target/release/bundle/`
- Windows: `.msi` installer + `.exe`
- macOS: `.dmg`
- Linux: `.deb` / `.AppImage`

### Backend as standalone executable (optional)

```bash
cd backend
pip install pyinstaller
pyinstaller --onefile run.py --name faceless-backend
```

---

## Video Style Templates

| Template | Transition | Zoom | Subtitle | Music |
|---|---|---|---|---|
| Documentary | Crossfade | Alternating | Bottom white | 12% |
| News | Cut | None | Lower third | 8% |
| Technology | Fade | Zoom out | Bottom white | 15% |
| Finance | Fade | Zoom in | Bottom white | 10% |
| Educational | Crossfade | Zoom in | Bottom yellow | 10% |
| History | Fade | Slow zoom | Bottom white | 14% |

---

## Performance (RTX 5060 Ti 16GB)

| Task | Target |
|---|---|
| 50 scene images (FLUX Dev, 20 steps) | < 20 min |
| Voice generation (50 scenes) | < 2 min |
| Subtitle transcription (10 min audio) | < 3 min |
| 10-minute documentary render | < 15 min |

---

## Troubleshooting

See [`docs/troubleshooting.md`](docs/troubleshooting.md) for common issues and [`docs/local-setup.md`](docs/local-setup.md) for full install instructions.

Quick checks:
- **ComfyUI offline chip** → ensure ComfyUI is running on port 8188
- **Piper Not Found** → set executable path in Settings → Piper TTS
- **FFmpeg not found** → install FFmpeg and add to system PATH
- **Whisper slow** → change model to `tiny` or `base` in Settings

---

## License

MIT — free to use, modify, and distribute.
