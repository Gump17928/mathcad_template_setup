@echo off
rem Builds the worksheets for a project. Double-click, or drag a project folder onto this file.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Please double-click setup.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" tool\build_template.py "%~1" --open
echo.
pause
