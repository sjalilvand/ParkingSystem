@echo off
title ParkingSystem - STOP
set "ROOT=%~dp0"
cd /d "%ROOT%"
docker compose -f docker-compose.prod.yml --env-file .env.prod down
echo PROD stack stopped (volumes preserved).
pause
