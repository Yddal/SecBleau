@echo off
title SecBleau — Restore
cd /d "%~dp0"

echo.
echo  ==============================
echo   SecBleau — Database Restore
echo  ==============================
echo.

REM Read credentials from .env
for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
    if "%%a"=="DB_USER"     set DB_USER=%%b
    if "%%a"=="DB_PASSWORD" set DB_PASSWORD=%%b
    if "%%a"=="DB_NAME"     set DB_NAME=%%b
)

if "%DB_USER%"=="" set DB_USER=secbleau
if "%DB_NAME%"==""  set DB_NAME=secbleau_db

REM Check Docker is running
docker info >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Docker Desktop is not running.
    pause & exit /b 1
)

REM Check db container is up
docker compose ps db | findstr /i /c:"Up" /c:"running" >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Database container is not running. Run start.bat first.
    pause & exit /b 1
)

REM If a file was passed as argument, use it directly
if not "%~1"=="" (
    set BACKUP_FILE=%~1
    goto do_restore
)

REM Otherwise list available backups and ask user to choose
if not exist "backups\*.dump" (
    echo  No backup files found in the backups\ folder.
    echo  Run backup.bat first to create one.
    echo.
    pause & exit /b 1
)

echo  Available backups:
echo.
set COUNT=0
for %%f in (backups\*.dump) do (
    set /a COUNT+=1
    echo    [!COUNT!] %%f
)
echo.

REM Enable delayed expansion for the selection loop
setlocal enabledelayedexpansion
set COUNT=0
for %%f in (backups\*.dump) do (
    set /a COUNT+=1
    set FILE_!COUNT!=%%f
)

set /p CHOICE= Enter number to restore (or Q to quit):
if /i "%CHOICE%"=="Q" exit /b 0

set BACKUP_FILE=!FILE_%CHOICE%!
if "%BACKUP_FILE%"=="" (
    echo  Invalid selection.
    pause & exit /b 1
)

:do_restore
if not exist "%BACKUP_FILE%" (
    echo  ERROR: File not found: %BACKUP_FILE%
    pause & exit /b 1
)

echo.
echo  Restoring from: %BACKUP_FILE%
echo  Target database: %DB_NAME%  (user: %DB_USER%)
echo.
echo  WARNING: This will overwrite all current data in the database.
set /p CONFIRM= Type YES to continue:
if /i not "%CONFIRM%"=="YES" (
    echo  Cancelled.
    pause & exit /b 0
)

echo.
echo  Restoring...

docker compose exec -T -e "PGPASSWORD=%DB_PASSWORD%" db ^
    pg_restore -U %DB_USER% -d %DB_NAME% --clean --if-exists --no-owner --no-privileges ^
    < "%BACKUP_FILE%"

if errorlevel 1 (
    echo.
    echo  WARNING: Restore finished with warnings above. This is often normal
    echo  (e.g. dropping objects that did not exist yet). Check the app works.
) else (
    echo.
    echo  Restore complete.
)

echo.
pause
