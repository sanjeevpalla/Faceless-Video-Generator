"""
Service control — start and stop ComfyUI and Wan2GP from the UI.

POST /services/comfyui/start
POST /services/comfyui/stop
POST /services/wan2gp/start
POST /services/wan2gp/stop
"""
import asyncio
import subprocess
import sys
from pathlib import Path
from typing import Optional

import httpx

from fastapi import APIRouter, Depends

from app.core.dependencies import get_settings_repo
from app.repositories.settings_repo import SettingsRepository

router = APIRouter()

_COMFYUI_DEFAULT = Path(r"C:\Program Files\Comfy Desktop")
_WAN2GP_DEFAULT = Path(r"D:\LLMs\Wan2GP")


def _pid_on_port(port: int) -> Optional[int]:
    try:
        out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=5).stdout
        for line in out.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                if parts:
                    return int(parts[-1])
    except Exception:
        pass
    return None


def _kill_port(port: int) -> bool:
    pid = _pid_on_port(port)
    if pid:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
        return True
    return False


# ---------------------------------------------------------------------------
# ComfyUI
# ---------------------------------------------------------------------------

@router.post("/comfyui/start")
async def start_comfyui(repo: SettingsRepository = Depends(get_settings_repo)):
    raw = await repo.get_by_key("services.comfyui_path")
    path = Path(str(raw)) if raw else _COMFYUI_DEFAULT

    def _launch():
        exe = path / "Comfy Desktop.exe"
        main_py = path / "main.py"
        if exe.exists():
            subprocess.Popen(
                [str(exe)],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                close_fds=True,
            )
            return {"started": True, "mode": "desktop", "path": str(exe)}
        if main_py.exists():
            subprocess.Popen(
                [sys.executable, str(main_py), "--listen", "127.0.0.1", "--port", "8188", "--gpu-only"],
                cwd=str(path),
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
            return {"started": True, "mode": "python", "path": str(main_py)}
        return {"started": False, "error": f"ComfyUI not found at {path}"}

    return await asyncio.to_thread(_launch)


@router.post("/comfyui/stop")
async def stop_comfyui():
    def _stop():
        return {"stopped": _kill_port(8188)}
    return await asyncio.to_thread(_stop)


@router.post("/comfyui/clear-queue")
async def clear_comfyui_queue():
    """Interrupt the currently running ComfyUI job and clear all pending queue items."""
    comfyui_url = "http://127.0.0.1:8188"
    interrupted, cleared = False, False
    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            await client.post(f"{comfyui_url}/interrupt")
            interrupted = True
        except Exception:
            pass
        try:
            await client.post(f"{comfyui_url}/queue", json={"clear": True})
            cleared = True
        except Exception:
            pass
    return {"interrupted": interrupted, "cleared": cleared}


# ---------------------------------------------------------------------------
# Wan2GP
# ---------------------------------------------------------------------------

@router.post("/wan2gp/start")
async def start_wan2gp(repo: SettingsRepository = Depends(get_settings_repo)):
    raw = await repo.get_by_key("services.wan2gp_path")
    path = Path(str(raw)) if raw else _WAN2GP_DEFAULT

    def _launch():
        wgp = path / "wgp.py"
        if not wgp.exists():
            return {"started": False, "error": f"wgp.py not found at {path}"}
        venv_py = path / "venv" / "Scripts" / "python.exe"
        python = str(venv_py) if venv_py.exists() else sys.executable
        subprocess.Popen(
            [
                python, "wgp.py",
                "--mcp", "--mcp-transport", "streamable-http",
                "--mcp-host", "0.0.0.0", "--mcp-port", "8889",
            ],
            cwd=str(path),
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        return {"started": True, "path": str(wgp)}

    return await asyncio.to_thread(_launch)


@router.post("/wan2gp/stop")
async def stop_wan2gp():
    def _stop():
        return {"stopped": _kill_port(8889)}
    return await asyncio.to_thread(_stop)
