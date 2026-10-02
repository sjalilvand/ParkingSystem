@echo off
title ParkingSystem - STATUS
set "ROOT=%~dp0"
cd /d "%ROOT%"
set "APP_PORT=8880"
if exist ".env.prod" for /f "usebackq tokens=1,* delims==" %%A in (".env.prod") do if /i "%%A"=="APP_PORT" set "APP_PORT=%%B"
echo --- PROD containers ---
docker compose -f docker-compose.prod.yml --env-file .env.prod ps
echo --- Health (port %APP_PORT%) ---
curl.exe -s http://localhost:%APP_PORT%/health/live
echo.
curl.exe -s http://localhost:%APP_PORT%/health/database
echo.
pause
