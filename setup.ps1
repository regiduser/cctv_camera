$ErrorActionPreference = "Stop"

Write-Host "CCTV Camera - environment setup" -ForegroundColor Cyan
if (-not (Test-Path "requirements.txt")) {
    Write-Error "requirements.txt was not found. Open PowerShell in the extracted cctv_camera-main folder."
    exit 1
}

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example. Edit CCTV_STREAM_TOKEN before running." -ForegroundColor Yellow
} else {
    Write-Host ".env already exists; left it unchanged."
}

Write-Host "Setup complete. Next:" -ForegroundColor Green
Write-Host "  1. Edit .env and set a unique CCTV_STREAM_TOKEN."
Write-Host "  2. Start receiver: .\.venv\Scripts\python.exe receiver.py"
Write-Host "  3. Start sender in another terminal: .\.venv\Scripts\python.exe sender.py"
