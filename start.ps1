# Faceless Video Generator — Development startup script (PowerShell)
# Starts both backend and frontend in separate windows

param(
    [switch]$BackendOnly,
    [switch]$FrontendOnly
)

$ProjectRoot = $PSScriptRoot

function Start-Backend {
    Write-Host "[FVG] Starting FastAPI backend..." -ForegroundColor Cyan
    Start-Process powershell -ArgumentList "-NoExit", "-Command",
        "cd '$ProjectRoot\backend'; python run.py" `
        -WindowStyle Normal
}

function Start-Frontend {
    Write-Host "[FVG] Starting Vite frontend..." -ForegroundColor Cyan
    Start-Process powershell -ArgumentList "-NoExit", "-Command",
        "cd '$ProjectRoot\frontend'; npm run dev" `
        -WindowStyle Normal
}

if ($BackendOnly) {
    Start-Backend
} elseif ($FrontendOnly) {
    Start-Frontend
} else {
    Start-Backend
    Start-Sleep -Seconds 2
    Start-Frontend
    Write-Host ""
    Write-Host "[FVG] Both services starting..." -ForegroundColor Green
    Write-Host "[FVG] Backend API:  http://localhost:8000" -ForegroundColor Yellow
    Write-Host "[FVG] Frontend UI:  http://localhost:1420" -ForegroundColor Yellow
    Write-Host "[FVG] API Docs:     http://localhost:8000/docs" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Tip: Also start ComfyUI on port 8188 for image generation." -ForegroundColor DarkGray
}
