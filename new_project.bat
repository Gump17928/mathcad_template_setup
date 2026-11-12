@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Please double-click setup.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" tool\new_project.py
echo.
pause
