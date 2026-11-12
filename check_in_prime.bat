@echo off
rem Opens every worksheet of a project in Mathcad Prime and lists the calculated results.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Please double-click setup.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" tool\verify_in_prime.py "%~1"
echo.
pause
