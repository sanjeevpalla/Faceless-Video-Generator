# Troubleshooting Guide

## Backend won't start

**Symptom:** `python run.py` exits immediately with an import error.

```
ModuleNotFoundError: No module named 'fastapi'
```

**Fix:** Install dependencies.
```bash
cd backend
pip install -r requirements.txt
```

---

**Symptom:** Port 8000 already in use.

```
[Errno 10048] error while attempting to bind on address ('127.0.0.1', 8000)
```

**Fix:** Kill the existing process or change the port in `config/default.json`:
```json
{ "PORT": 8001 }
```
Then update `frontend/src/api/client.ts` `BASE_URL` to match.

---

## ComfyUI / Image Generation

**Symptom:** "ComfyUI Offline" chip is red.

**Checks:**
1. Is ComfyUI running? `python main.py --listen 127.0.0.1 --port 8188`
2. Is the port correct? Check Settings → FLUX → ComfyUI URL.
3. Firewall blocking? Try `curl http://127.0.0.1:8188/system_stats`

---

**Symptom:** Image generation starts but produces black images.

**Fix:** Ensure `flux1-dev.safetensors` is placed in ComfyUI's `models/checkpoints/` folder and the model name in the workflow template matches exactly.

---

**Symptom:** ComfyUI returns "prompt_id not found" after submission.

**Fix:** The FLUX workflow references `"4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "flux1-dev.safetensors"}}`. If your model file has a different name, update `FLUX_WORKFLOW_TEMPLATE` in `backend/app/services/image_service.py`.

---

## Voice Generation (Piper)

**Symptom:** "Piper Not Found" chip is red.

**Fix:**
1. Download Piper from https://github.com/rhasspy/piper/releases
2. Extract to e.g. `C:\piper\`
3. In Settings → Piper TTS, set **Executable** to `C:\piper\piper.exe`
4. Download a voice model `.onnx` from https://huggingface.co/rhasspy/piper-voices
5. Set **Model Path** to the `.onnx` file

---

**Symptom:** Piper found but audio is empty (0 bytes).

**Fix:** Ensure the `.onnx` model file and its companion `.json` config file are in the same directory. Piper requires both files.

---

**Symptom:** Voice generation hangs indefinitely.

**Fix:** Piper has a 120-second timeout per scene. Very long narration texts (>2000 chars) may time out. Split into shorter scenes in `scenes.json`.

---

## Subtitles (Whisper)

**Symptom:** Whisper model download fails behind a proxy.

**Fix:**
```bash
# Pre-download the model manually
python -c "import whisper; whisper.load_model('base')"
```

---

**Symptom:** Subtitle generation is very slow.

**Fix:** Change Whisper model to `tiny` in Settings → Video & Subtitles → Whisper Model. Accuracy decreases but speed increases 4×.

---

**Symptom:** Subtitles have wrong language.

**Fix:** Set **Whisper Language** in Settings to the correct ISO 639-1 code (e.g. `en`, `es`, `fr`, `de`).

---

## Video Rendering (MoviePy / FFmpeg)

**Symptom:** "FFmpeg Not Found" chip is red.

**Fix:**
1. Download FFmpeg from https://ffmpeg.org/download.html
2. Extract and add the `bin/` folder to your system `PATH`
3. Verify: `ffmpeg -version` in a new terminal

---

**Symptom:** Video renders but has no audio.

**Checks:**
- Is `narration_merged.wav` present in `projects/{id}/audio/`?
- Check the Voice generation page — did it complete successfully?
- Check the Asset Readiness panel on the Video page.

---

**Symptom:** Subtitle burning fails; video is produced without subtitles.

**Cause:** FFmpeg's `subtitles` filter requires the SRT file path to be escaped correctly on Windows.

**Fix:** The service escapes backslashes automatically. If it still fails, check the error log. The app falls back to the raw video without subtitles rather than failing completely.

---

**Symptom:** `moviepy` import error: `ImageMagick not found`.

**Fix:** MoviePy's `TextClip` requires ImageMagick, but the app deliberately avoids `TextClip` (uses FFmpeg for subtitle burning instead). If you see this error, it means a code path you shouldn't be hitting is executing — check the logs.

---

## Frontend / UI

**Symptom:** "Backend disconnected" chip stays red.

**Fix:** Ensure `python run.py` is running in the backend directory. The frontend WebSocket connects to `ws://localhost:8000/ws`.

---

**Symptom:** Images don't load in the gallery.

**Cause:** Images are served at `/api/v1/images/project/{id}/scene/{n}/file` by the backend. If the backend is down, images won't load.

**Fix:** Ensure the backend is running. Check browser console for 404s.

---

**Symptom:** Project validation shows all files as missing even after upload.

**Fix:** After uploading, click **Validate Files** — the button calls the backend to re-check. If it still shows missing, the file may have been saved to the wrong path. Check `projects/{id}/input/` in the file system.

---

## Database

**Symptom:** `sqlite3.OperationalError: database is locked`.

**Fix:** Only one backend process should be running. Kill all `python run.py` processes and restart once.

---

**Symptom:** Projects disappeared after restart.

**Fix:** The SQLite DB is at `database/faceless.db`. If this file was deleted, all project metadata is lost (generated files in `projects/` are still intact). You would need to re-import projects manually.

---

## Performance

**Symptom:** Image generation is slow (more than 2 min/image).

**Fix:**
- Ensure ComfyUI is using the GPU: add `--gpu-only` to its startup command
- Lower FLUX Steps from 20 to 12-15 (acceptable quality tradeoff)
- Check GPU VRAM in the ComfyUI status chip — if < 4GB free, reduce step count

---

**Symptom:** Video render takes very long.

**Fix:**
- Use a lower resolution (1280×720) during testing — change in Settings → Video
- Ken Burns effect is CPU-intensive; set Zoom Amount to 0 to disable it
- Reduce FPS from 30 to 24 for testing

---

## Getting Help

1. Check the live logs in **Project → Logs** tab
2. Check `logs/app.log` and `logs/error.log` in the project root
3. Open the API docs at `http://localhost:8000/docs` and test endpoints directly
