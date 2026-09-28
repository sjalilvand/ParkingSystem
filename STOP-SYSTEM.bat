@echo off
title ParkingSystem - STOP
cd /d E:\ParkingSystem
echo Stopping ParkingSystem containers (data is KEPT)...
docker compose -f docker-compose.prod.yml --env-file .env.prod down
echo.
echo Stopped. (To start again: double-click START-SYSTEM.bat)
pause