@echo off
setlocal
cd /d "%~dp0"
rem ------------------------------------------------------------------------------------------
rem One-time setup: finds Python 3.10+ on this PC, builds the private .venv folder, installs packages.
rem
rem Usage:   setup.bat                      find Python automatically
rem          setup.bat "D:\Tools\Python"    use this Python (a python.exe or the folder that holds it)
rem
rem Python is looked for, in order:
rem   1. the path given above, the MATHCAD_PYTHON environment variable, or python_path.txt (saved earlier)
rem   2. the "py" launcher     3. python on the PATH     4. the Windows registry (every normal installer)
rem   5. the usual install folders     6. a "python" folder next to this file
rem   7. otherwise you are asked to type the path, and it is saved in python_path.txt for next time
rem ------------------------------------------------------------------------------------------
echo ============================================================
echo  MathCAD Template - one-time setup
echo ============================================================
echo.

set "PY="
set "REMEMBER="
set "WHYNOT="

rem --- 1. a path chosen on purpose
if not "%~1"=="" set "REMEMBER=1"
if not "%~1"=="" call :try "%~1"
if not defined PY if defined MATHCAD_PYTHON call :try "%MATHCAD_PYTHON%"
if defined PY goto :found
set "SAVED="
if exist "python_path.txt" set /p SAVED=<"python_path.txt"
if defined SAVED set "SAVED=%SAVED:"=%"
if defined SAVED call :try "%SAVED%"
if defined PY goto :found

rem --- 2. the py launcher (it reports the real python.exe, which is what we need)
for /f "delims=" %%p in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do call :try "%%p"
if defined PY goto :found

rem --- 3. python on the PATH (a Microsoft Store placeholder that is not a real Python is skipped by the checks)
for /f "delims=" %%p in ('where python 2^>nul') do call :try "%%p"
if defined PY goto :found

rem --- 4. the registry: python.org, the Python install manager and most other installers register themselves here
for %%k in ("HKCU\Software\Python\PythonCore" "HKLM\Software\Python\PythonCore" "HKLM\Software\WOW6432Node\Python\PythonCore") do call :fromregistry %%k
if defined PY goto :found

rem --- 5. the usual install folders
for /d %%d in ("%LOCALAPPDATA%\Python\pythoncore-3*" "%LOCALAPPDATA%\Programs\Python\Python3*" "%ProgramFiles%\Python3*" "%ProgramFiles(x86)%\Python3*" "%SystemDrive%\Python3*") do call :try "%%~d"
if defined PY goto :found

rem --- 6. a python folder placed next to this file (a portable copy)
call :try "%~dp0python"
if defined PY goto :found

rem --- 7. ask
set "REMEMBER=1"
echo Python 3.10 or newer was not found automatically on this PC.
if defined WHYNOT echo ^(Last thing tried: %WHYNOT%^)
echo.
:ask
set "TYPED="
set /p "TYPED=Type the full path to python.exe (or the folder it is in), or press Enter to quit: "
if not defined TYPED goto :nopython
set "TYPED=%TYPED:"=%"
call :try "%TYPED%"
if defined PY goto :found
echo   That did not work: %WHYNOT%
echo.
goto :ask

:found
echo Using Python:
echo   %PY%
"%PY%" --version
if defined REMEMBER >"python_path.txt" echo %PY%
echo.

rem --- the private environment; rebuild it if it was copied from another PC or its Python was moved
if not exist ".venv\Scripts\python.exe" goto :makevenv
".venv\Scripts\python.exe" -c "import sys" >nul 2>&1
if not errorlevel 1 goto :havevenv
echo The existing .venv folder no longer works ^(it was probably copied from another PC^). Rebuilding it...
rmdir /s /q ".venv"
:makevenv
echo Creating a private Python environment in the .venv folder...
"%PY%" -m venv .venv
if errorlevel 1 goto :failed
:havevenv

echo Installing the required packages ^(needs internet, takes about a minute^)...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :pipfailed
".venv\Scripts\python.exe" -c "import lxml, win32com.client" >nul 2>&1
if errorlevel 1 goto :pipfailed

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

rem ------------------------------------------------------------------------------------------
rem :try "path"  - path is a python.exe or a folder holding one. Sets PY if it is a usable Python 3.10+.
rem                Otherwise leaves PY unset and puts the reason in WHYNOT.
:try
if defined PY exit /b 0
set "CAND=%~1"
if "%CAND%"=="" exit /b 1
if exist "%CAND%\python.exe" set "CAND=%CAND%\python.exe"
if not exist "%CAND%" set "WHYNOT=%CAND% does not exist"
if not exist "%CAND%" exit /b 1
"%CAND%" -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if errorlevel 1 set "WHYNOT=%CAND% is not Python 3.10 or newer"
if errorlevel 1 exit /b 1
"%CAND%" -c "import venv, ensurepip" >nul 2>&1
if errorlevel 1 set "WHYNOT=%CAND% is missing venv/pip - a stripped-down or embeddable Python cannot be used; install the full one"
if errorlevel 1 exit /b 1
set "PY=%CAND%"
exit /b 0

rem :fromregistry "key" - tries every Python registered under that registry key
:fromregistry
for /f "tokens=2,*" %%a in ('reg query %1 /s /v ExecutablePath 2^>nul ^| findstr /i "ExecutablePath"') do call :try "%%b"
exit /b 0

:nopython
echo.
echo No Python was chosen. Install Python 3.10 or newer from https://www.python.org/downloads/
echo   - On the first installer screen tick "Add python.exe to PATH".
echo Or, in a Command Prompt:  winget install Python.Python.3.12
echo Already installed somewhere unusual?  Run:  setup.bat "full\path\to\python.exe"
echo.
pause
exit /b 1

:pipfailed
echo.
echo The packages did not install. Check the messages above. Common causes:
echo   - no internet access, or a company proxy/firewall blocking pip ^(ask IT, or set the HTTPS_PROXY variable^)
echo   - the PC blocks installing software
echo.
pause
exit /b 1

:failed
echo.
echo Setup did not finish - see the messages above.
echo.
pause
exit /b 1
