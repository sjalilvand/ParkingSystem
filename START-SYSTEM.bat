@echo off
title ParkingSystem - START
set "ROOT=%~dp0"
cd /d "%ROOT%"
set "APP_PORT=8880"
if exist ".env.prod" for /f "usebackq tokens=1,* delims==" %%A in (".env.prod") do if /i "%%A"=="APP_PORT" set "APP_PORT=%%B"

echo ================================================
echo   ParkingSystem - START  (root: %ROOT%)
echo ================================================
echo.
echo [1/4] Checking Docker engine...
docker info >nul 2>&1
if not errorlevel 1 goto docker_ok
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
set /a tries=0
:wait_docker
timeout /t 10 /nobreak >nul
docker info >nul 2>&1
if not errorlevel 1 goto docker_ok
set /a tries+=1
echo      waiting for Docker... (%tries%/30)
if %tries% lss 30 goto wait_docker
echo [X] Docker did not start in 5 minutes. Open it manually and retry.
pause
exit /b 1

:docker_ok
echo [OK] Docker engine is running.

echo.
echo [2/4] Starting PROD stack (isolated project: parkingsystem-prod)...
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d

echo.
echo [3/4] Waiting for backend health (max 8 minutes)...
set /a tries=0
:wait_health
timeout /t 5 /nobreak >nul
curl.exe -s http://localhost:%APP_PORT%/health/live 2>nul | findstr /C:"ok" >nul
if not errorlevel 1 goto healthy
set /a tries+=1
echo      waiting... (%tries%/96)
if %tries% lss 96 goto wait_health
echo [X] Backend NOT healthy after 8 minutes. Last logs:
docker compose -f docker-compose.prod.yml --env-file .env.prod logs --tail 30 backend
pause
exit /b 1

:healthy
echo [OK] Backend is HEALTHY.

echo.
echo [4/4] Container status:
docker compose -f docker-compose.prod.yml --env-file .env.prod ps

echo.
echo ================================================
echo   SYSTEM IS UP
echo   Web (this PC)   : http://localhost:%APP_PORT%
echo   Web (other PCs) : http://SERVER-IP:%APP_PORT%
echo   Swagger         : http://localhost:%APP_PORT%/api/docs
echo ================================================
start "" http://localhost:%APP_PORT%
echo.
pause
