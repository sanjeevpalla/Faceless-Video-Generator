@echo off
setlocal

echo [FVG] Starting Faceless Video Generator...
echo.

:: --- Kill any previously launched FVG windows by title ---
echo [FVG] Stopping any existing services...
taskkill /FI "WINDOWTITLE eq FVG Backend" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq FVG Frontend" /F >nul 2>&1

:: --- Kill by port (backup: handles restarts from outside this bat) ---
netstat -aon 2>nul | findstr ":8000 " | findstr "LISTENING" > "%TEMP%\fvg_kill.txt"
if exist "%TEMP%\fvg_kill.txt" (
    for /f "usebackq tokens=5" %%p in ("%TEMP%\fvg_kill.txt") do (
        echo [FVG] Killing PID %%p on port 8000...
        taskkill /PID %%p /F >nul 2>&1
    )
    del "%TEMP%\fvg_kill.txt" >nul 2>&1
)

netstat -aon 2>nul | findstr ":1420 " | findstr "LISTENING" > "%TEMP%\fvg_kill.txt"
if exist "%TEMP%\fvg_kill.txt" (
    for /f "usebackq tokens=5" %%p in ("%TEMP%\fvg_kill.txt") do (
        echo [FVG] Killing PID %%p on port 1420...
        taskkill /PID %%p /F >nul 2>&1
    )
    del "%TEMP%\fvg_kill.txt" >nul 2>&1
)

echo [FVG] Waiting for ports to release...
timeout /t 2 /nobreak >nul

:: --- Start backend ---
echo [FVG] Starting FastAPI backend (port 8000)...
start "FVG Backend" cmd /k "cd /d "%~dp0backend" && python run.py"

timeout /t 3 /nobreak >nul

:: --- Start frontend ---
echo [FVG] Starting Vite frontend (port 1420)...
start "FVG Frontend" cmd /k "cd /d "%~dp0frontend" && npm run dev"

echo.
echo [FVG] Backend:  http://localhost:8000
echo [FVG] Frontend: http://localhost:1420
echo [FVG] API Docs: http://localhost:8000/docs
echo [FVG] Use the Images page to start ComfyUI, Clips page to start Wan2GP.
echo.
pause
