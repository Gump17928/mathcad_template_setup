@echo off
setlocal
cd /d "%~dp0"
echo ============================================================
echo  MathCAD Template - one-time setup
echo ============================================================
echo.

set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY (
    python --version >nul 2>&1 && set "PY=python"
)
if not defined PY goto :nopython

%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if errorlevel 1 goto :oldpython

echo Using:
%PY% --version
echo.

if not exist ".venv\Scripts\python.exe" (
    echo Creating a private Python environment in the .venv folder...
    %PY% -m venv .venv
    if errorlevel 1 goto :failed
)

echo Installing the required packages ^(needs internet, takes about a minute^)...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :failed

echo.
reg query "HKCR\MathcadPrime.Application" >nul 2>&1
if errorlevel 1 (
    echo NOTE: Mathcad Prime was not found on this PC.
    echo       You can still build worksheets, but check_in_prime.bat and make_pdfs.bat need Prime installed.
) else (
    echo Mathcad Prime found.
)

echo.
echo Setup complete. Next: double-click new_project.bat
echo.
pause
exit /b 0

:nopython
echo Python is not installed ^(or is not on the PATH^).
echo.
echo Install Python 3.12 or newer from https://www.python.org/downloads/
echo   - On the first installer screen tick "Add python.exe to PATH".
echo Or, in a Command Prompt:  winget install Python.Python.3.12
echo Then double-click setup.bat again.
echo.
pause
exit /b 1

:oldpython
echo This tool needs Python 3.10 or newer. Please install a newer Python from https://www.python.org/downloads/
echo.
pause
exit /b 1

:failed
echo.
echo Setup did not finish - see the messages above.
echo.
pause
exit /b 1
