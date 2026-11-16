@echo off
rem Makes a template skeleton for another Mathcad Prime version. Drag a worksheet saved by that Prime onto this file.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Please double-click setup.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" tool\capture_skeleton.py %*
echo.
pause
