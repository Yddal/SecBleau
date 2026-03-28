@echo off
title SecBleau — Start
cd /d "%~dp0"

echo.
echo  ==============================
echo   SecBleau — Starting up
echo  ==============================
echo.

REM Check Docker is running
docker info >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Docker Desktop is not running.
    echo  Please start Docker Desktop and try again.
    echo.
    pause
    exit /b 1
)

REM Copy .env if not present
if not exist ".env" (
    echo  First run detected — creating .env from .env.example
    copy ".env.example" ".env" >nul
    echo  NOTE: Edit .env to set credentials and optional Netatmo keys.
    echo.
)

REM Read DB_USER and DB_NAME from .env for healthcheck
for /f "usebackq tokens=1,2 delims==" %%a in (".env") do (
    if "%%a"=="DB_USER" set DB_USER=%%b
    if "%%a"=="DB_NAME" set DB_NAME=%%b
)
if "%DB_USER%"=="" set DB_USER=secbleau
if "%DB_NAME%"=="" set DB_NAME=secbleau_db

REM Start containers
echo  Starting containers...
docker compose up -d
if errorlevel 1 (
    echo.
    echo  ERROR: docker compose failed. See output above.
    pause
    exit /b 1
)

echo.
echo  Waiting for database to be ready...
:wait_db
docker compose exec db pg_isready -U %DB_USER% -d %DB_NAME% >nul 2>&1
if errorlevel 1 (
    timeout /t 2 /nobreak >nul
    goto wait_db
)

REM Sync Boolder climbing data.
REM The script checks GitHub for a new version — if data is already up to date
REM it exits in seconds. Only downloads on first run or when Boolder releases an update.
echo  Checking Boolder data…
docker compose exec -T api python data/boolder_import.py
if errorlevel 1 (
    echo.
    echo  WARNING: Boolder sync had errors. The app will still start.
    echo  Run start.bat again once the issue is resolved.
)

echo  Calibrating area drying parameters…
docker compose exec -T api python data/calibrate_areas.py
if errorlevel 1 (
    echo.
    echo  WARNING: Area calibration had errors. Scores will use default parameters.
)

echo.
echo  ==============================
echo   SecBleau is running!
echo   http://localhost:5173
echo  ==============================
echo.

REM Open browser
start "" "http://localhost:5173"

echo  Press any key to view live logs (Ctrl+C to exit logs without stopping).
pause >nul
docker compose logs -f
