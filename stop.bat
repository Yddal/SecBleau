@echo off
title SecBleau — Stop
cd /d "%~dp0"

echo.
echo  Stopping SecBleau...
docker compose down
echo.
echo  Stopped. Your data is preserved in the Docker volume.
echo  Run start.bat to start again.
echo.
pause
