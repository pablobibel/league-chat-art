@echo off
setlocal
cd /d "%~dp0"

set "ART_IMAGE=%~1"
if not defined ART_IMAGE set "ART_IMAGE=%USERPROFILE%\Downloads\kawaiilogo.png"

if not exist "%ART_IMAGE%" (
    echo Image not found: "%ART_IMAGE%"
    echo Drag a PNG, JPEG, WebP, or BMP image onto this launcher.
    pause
    exit /b 2
)

if not exist ".venv\Scripts\python.exe" (
    echo Setup is missing. Run the installation steps in README.md once.
    pause
    exit /b 2
)

".venv\Scripts\python.exe" "league_art.py" "%ART_IMAGE%" --channel all
echo.
echo Sender finished. Press any key to close this window.
pause >nul
