@echo off
title SecBleau — Backup
cd /d "%~dp0"

echo.
echo  ==============================
echo   SecBleau — Database Backup
echo  ==============================
echo.

REM Read credentials from .env
for /f "usebackq tokens=1,2 delims==" %%a in (".env") do (
    if "%%a"=="DB_USER"     set DB_USER=%%b
    if "%%a"=="DB_PASSWORD" set DB_PASSWORD=%%b
    if "%%a"=="DB_NAME"     set DB_NAME=%%b
)

if "%DB_USER%"=="" set DB_USER=secbleau
if "%DB_NAME%"==""  set DB_NAME=secbleau_db

REM Build timestamped filename
for /f "tokens=1-4 delims=/ " %%a in ('date /t') do set DATE_STR=%%d%%b%%c
for /f "tokens=1-2 delims=:." %%a in ('time /t') do set TIME_STR=%%a%%b
set TIME_STR=%TIME_STR: =0%
set BACKUP_FILE=backups\secbleau_%DATE_STR%_%TIME_STR%.dump

REM Create backups directory if needed
if not exist "backups" mkdir backups

REM Check Docker is running
docker info >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Docker Desktop is not running.
    pause & exit /b 1
)

REM Check db container is up
docker compose ps db | findstr "running" >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Database container is not running. Run start.bat first.
    pause & exit /b 1
)

echo  Backing up database "%DB_NAME%" as user "%DB_USER%"...
echo  Output: %BACKUP_FILE%
echo.

docker compose exec -T -e PGPASSWORD=%DB_PASSWORD% db ^
    pg_dump -U %DB_USER% -d %DB_NAME% -Fc ^
    > "%BACKUP_FILE%"

if errorlevel 1 (
    echo.
    echo  ERROR: Backup failed. See output above.
    if exist "%BACKUP_FILE%" del "%BACKUP_FILE%"
    pause & exit /b 1
)

REM Show file size
for %%f in ("%BACKUP_FILE%") do set SIZE=%%~zf
set /a SIZE_KB=%SIZE% / 1024
echo  Backup complete — %BACKUP_FILE% (%SIZE_KB% KB)
echo.
pause
