@echo off
rem Exports every worksheet of a project to PDF through Mathcad Prime.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Please double-click setup.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" tool\export_pdf.py "%~1"
echo.
pause
