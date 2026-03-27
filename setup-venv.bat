@echo off
title SecBleau — Python venv setup
cd /d "%~dp0"

echo.
echo  ==============================
echo   SecBleau — Local Python setup
echo   (optional — only needed for
echo    IDE support or running scripts
echo    outside Docker)
echo  ==============================
echo.

REM Check Python 3.11+
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python not found. Install Python 3.11+ from https://python.org
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo  Found Python %PY_VER%

REM Create venv in backend/
if not exist "backend\.venv" (
    echo.
    echo  Creating virtual environment in backend\.venv ...
    python -m venv "backend\.venv"
) else (
    echo  Virtual environment already exists at backend\.venv
)

echo.
echo  Activating and installing dependencies...
call "backend\.venv\Scripts\activate.bat"

REM Try uv first (faster), fall back to pip
uv --version >nul 2>&1
if not errorlevel 1 (
    echo  Installing with uv...
    uv pip install -e "backend/[dev]"
) else (
    echo  Installing with pip...
    pip install -e "backend/"
)

echo.
echo  ==============================
echo   Done!
echo.
echo   To activate the venv manually:
echo     backend\.venv\Scripts\activate
echo.
echo   To run the import script locally:
echo     backend\.venv\Scripts\activate
echo     python backend/data/boolder_import.py
echo  ==============================
echo.
pause
