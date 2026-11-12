@echo off
rem Runs the automated tests, then the code-style checks if the developer tools are installed.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Please double-click setup.bat first.
    pause
    exit /b 1
)

echo === Tests ===
".venv\Scripts\python.exe" -m unittest discover -s tests
set "RESULT=%errorlevel%"

".venv\Scripts\python.exe" -m ruff --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo Style check skipped. To enable it run:  .venv\Scripts\python.exe -m pip install -r requirements-dev.txt
) else (
    echo.
    echo === Style check ===
    ".venv\Scripts\python.exe" -m ruff check tool tests
    if errorlevel 1 set "RESULT=1"
)

echo.
if "%RESULT%"=="0" (echo ALL OK) else (echo PROBLEMS FOUND - see above)
pause
exit /b %RESULT%
