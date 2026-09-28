@echo off
title ParkingSystem - STATUS
cd /d E:\ParkingSystem
echo === Containers ===
docker compose -f docker-compose.prod.yml --env-file .env.prod ps
echo.
echo === Health ===
curl.exe -s http://localhost/health/live
echo.
echo.
echo === Backend last 15 log lines ===
for /f "tokens=*" %%c in ('docker compose -f docker-compose.prod.yml ps -q backend') do docker logs %%c --tail 15
pause