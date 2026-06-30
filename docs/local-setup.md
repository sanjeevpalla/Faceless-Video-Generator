# Local Setup Guide — Faceless Video Generator

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.11+ | Must be on PATH |
| Node.js | 18+ | npm included |
| FFmpeg | Any recent | Must be on PATH |
| Rust + Cargo | stable | Required for Tauri build only |
| Git | Any | Optional |

### Hardware (recommended)
- GPU: NVIDIA RTX with 8 GB+ VRAM (RTX 5060 Ti 16 GB tested)
- RAM: 16 GB+
- OS: Windows 11

---

## 1. Clone / Download

```powershell
# If using git
git clone <repo-url> "D:\Faceless Video Generator"
cd "D:\Faceless Video Generator"
```

Or unzip the archive into `D:\Faceless Video Generator\`.

---

## 2. Python Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

> **Note:** `moviepy`, `openai-whisper`, and `rembg` pull in large transitive deps (PyTorch for Whisper). Expect ~5–10 minutes and ~4 GB on first install.

### Verify
```powershell
python -c "import fastapi, moviepy, whisper; print('OK')"
```

---

## 3. Node Frontend

```powershell
cd frontend
npm install
```

---

## 4. External Binaries

### FFmpeg
1. Download from https://ffmpeg.org/download.html (Windows build, e.g. gyan.dev full build)
2. Extract and add the `bin\` folder to your system `PATH`
3. Verify: `ffmpeg -version`

### Piper TTS
1. Download the latest Windows release from https://github.com/rhasspy/piper/releases
2. Extract `piper.exe` and add its folder to `PATH`
3. Download a voice model (`.onnx` + `.onnx.json`), e.g. `en_US-lessac-medium`
4. Place both files in `models\piper\` (create folder if needed)
5. Verify: `piper --help`

### ComfyUI + FLUX (for image generation)
1. Clone ComfyUI: `git clone https://github.com/comfyanonymous/ComfyUI`
2. Install its requirements inside its own venv
3. Download `flux1-dev.safetensors` and place in `ComfyUI\models\checkpoints\`
4. Start ComfyUI: `python main.py --listen 127.0.0.1 --port 8188`

> ComfyUI runs independently — it is never imported by the backend. The app talks to it via REST at `http://127.0.0.1:8188`.

---

## 5. Configuration

Copy or edit `config\default.json` to set your local paths:

```json
{
  "PIPER_MODEL_PATH": "D:\\Faceless Video Generator\\models\\piper\\en_US-lessac-medium.onnx",
  "PIPER_EXECUTABLE": "piper",
  "COMFYUI_URL": "http://127.0.0.1:8188",
  "WHISPER_MODEL": "base",
  "WHISPER_DEVICE": "cpu"
}
```

For GPU-accelerated Whisper set `"WHISPER_DEVICE": "cuda"`.

---

## 6. Google Gemini API Key (content generation)

The pipeline uses the free `google-genai` SDK. Set your key as an environment variable before starting the backend:

```powershell
$env:GEMINI_API_KEY = "your-key-here"
```

Or add it permanently via **System Properties → Environment Variables**.

---

## 7. Database

The SQLite database is created automatically on first run at `database\faceless.db`. No migration step is needed.

---

## 8. Running the App

### Option A — one double-click
```
start.bat
```
Opens two terminal windows: backend on port 8000, frontend on port 1420.

### Option B — manual (two terminals)

**Terminal 1 — Backend**
```powershell
cd backend
.venv\Scripts\activate
python run.py
```

**Terminal 2 — Frontend**
```powershell
cd frontend
npm run dev
```

### URLs
| Service | URL |
|---------|-----|
| Frontend UI | http://localhost:1420 |
| Backend API | http://localhost:8000 |
| Swagger docs | http://localhost:8000/docs |
| ComfyUI (optional) | http://localhost:8188 |

---

## 9. Running Tests

```powershell
cd backend
.venv\Scripts\activate
python -m pytest tests/ -v
```

203 tests, ~5 seconds, no GPU or external services required.

---

## 10. Tauri Desktop Build (optional)

Only needed if you want a native `.exe` instead of the Vite dev server.

```powershell
# Install Rust if not present
winget install Rustlang.Rustup

cd frontend
npm run tauri build
# Output: src-tauri\target\release\bundle\
```

---

## Directory Overview

```
D:\Faceless Video Generator\
├── backend\          Python / FastAPI source
│   ├── app\          Application code
│   ├── tests\        Pytest suite (203 tests)
│   └── run.py        Entrypoint
├── frontend\         React / Vite source
├── src-tauri\        Tauri / Rust wrapper
├── config\           default.json — runtime config
├── database\         SQLite DB (auto-created)
├── projects\         Per-project files (script, scenes, audio…)
├── models\
│   └── piper\        .onnx voice model goes here
├── output\           Final rendered videos
├── logs\             Rotating log files
├── docs\             This file + other guides
└── start.bat         One-click launcher
```

---

## Common Issues

| Symptom | Fix |
|---------|-----|
| `ModuleNotFoundError: fastapi` | Activate venv and re-run `pip install -r requirements.txt` |
| Port 8000 already in use | Run `start.bat` (kills old processes) or `taskkill /F /IM python.exe` |
| "ComfyUI Offline" chip red | Start ComfyUI with `--listen 127.0.0.1 --port 8188`, or check firewall |
| Black images from FLUX | Confirm `flux1-dev.safetensors` is in `ComfyUI\models\checkpoints\` |
| Piper not found | Ensure `piper.exe` is on PATH; check Settings → Voice in the UI |
| Whisper slow | Set `WHISPER_DEVICE: "cuda"` in `config\default.json` |
| `rembg` errors on first run | It auto-downloads the `u2netp` model (~170 MB) on first use — wait for it |

See [`docs\troubleshooting.md`](troubleshooting.md) for more detailed diagnostics.
