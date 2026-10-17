# ============================================================
# update.ps1 — One-command project update from GitHub
# Usage:  powershell -ExecutionPolicy Bypass -File .\update.ps1
# ============================================================
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host ""
Write-Host "=== ParkingSystem Update ===" -ForegroundColor Cyan

# 1. Check git repo
if (-not (Test-Path ".git")) {
    Write-Host "[ERROR] This folder is not a git repository." -ForegroundColor Red
    exit 1
}

# 2. Fetch latest from GitHub
Write-Host "[1/3] Fetching from GitHub ..." -ForegroundColor Yellow
git fetch origin
if ($LASTEXITCODE -ne 0) { Write-Host "[ERROR] git fetch failed - check internet/token." -ForegroundColor Red; exit 1 }

$local  = git rev-parse HEAD
$remote = git rev-parse origin/main
Write-Host "      local : $local"
Write-Host "      remote: $remote"

if ($local -eq $remote) {
    Write-Host "[OK] Project is already up to date." -ForegroundColor Green
    git log --oneline -3
    exit 0
}

# 3. Stash local (uncommitted) changes safely
Write-Host "[2/3] Stashing local changes (safe) ..." -ForegroundColor Yellow
git stash push -u -m "auto-stash before update" 2>$null | Out-Null

# 4. Pull latest main
Write-Host "[3/3] Pulling latest main ..." -ForegroundColor Yellow
git pull origin main
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] git pull failed. Your local changes are SAFE in the stash." -ForegroundColor Red
    Write-Host "        Restore them later with:  git stash pop" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "=== Update finished ===" -ForegroundColor Green
git log --oneline -3
Write-Host ""
Write-Host "Notes:"
Write-Host " - Your previous local changes are saved in stash. If everything works,"
Write-Host "   clean it with:   git stash drop"
Write-Host "   (the same changes are already included in the new code)"
Write-Host " - New OCR dependencies (first time only):"
Write-Host "   cd backend; .\.venv\Scripts\Activate.ps1; pip install -r requirements-ocr.txt"
Write-Host " - Start the system from the project ROOT (not backend folder):"
Write-Host "   .\start-all.ps1"
Write-Host " - Plate OCR test page:  http://localhost:8000/plate-test" -ForegroundColor Cyan
