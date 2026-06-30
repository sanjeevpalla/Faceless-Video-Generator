# Faceless Video Generator — Claude Code Context

## Project summary
Full-stack desktop application for automated faceless YouTube video generation.
- Frontend: React 18 + TypeScript + Material UI v5 + Zustand + React Query
- Backend: Python 3.11 + FastAPI + SQLAlchemy async + SQLite
- Desktop: Tauri 1.x (Rust)
- Image gen: FLUX Dev via ComfyUI API at localhost:8188
- Voice: Piper TTS (subprocess, .onnx model)
- Subtitles: openai-whisper (local)
- Video: MoviePy + FFmpeg

## Key constraints
- NO paid APIs — everything runs locally
- FLUX is called via ComfyUI REST API; never loaded inside FastAPI
- User hardware: RTX 5060 Ti 16GB, Windows 11, AMD Ryzen 7

## Input files per project
script.md, scenes.json, image_prompts.txt, thumbnail_prompt.txt, seo.json, bg_music.mp3

## Running the project
```
# Terminal 1 — backend
cd backend && python run.py

# Terminal 2 — frontend
cd frontend && npm run dev

# Or just double-click start.bat
```

## Running tests
```
cd backend
python -m pytest tests/ -v
# 203 tests, ~5 seconds, no hardware needed
```

## API docs
http://localhost:8000/docs (Swagger UI, live when backend is running)

## Key files
- backend/app/api/router.py — all router registrations
- backend/app/services/base.py — BaseService with retry_async(), check_cancelled()
- backend/app/workers/queue_manager.py — async priority job queue
- backend/app/core/progress.py — WebSocket event emitter functions
- frontend/src/hooks/useWebSocket.ts — routes all WS events to stores + React Query
- frontend/src/store/projectStore.ts — generationProgress per step

## Pydantic v2 conventions
- Use ConfigDict instead of class Config
- Use model_dump() instead of .dict()
- Use model_validate(obj, from_attributes=True) instead of from_orm()

## Phase completion status
All 12 phases complete:
1. Architecture + scaffold
2. Backend deep implementation
3. Frontend foundation
4. Project management module
5. FLUX image generation
6. Piper voice generation
7. Whisper subtitles
8. MoviePy video rendering
9. WebSocket progress tracking
10. YouTube metadata + thumbnail
11. Testing (203 tests) + error recovery
12. Documentation + packaging
