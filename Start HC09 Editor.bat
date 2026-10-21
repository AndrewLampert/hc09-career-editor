@echo off
rem Double-click to start the HC09 editor. Checks that Python 3.9+ (with Tk) and Node.js 18+ are installed, installs the bridge's
rem dependencies the first time, then opens the editor without a console window.
rem   "Start HC09 Editor.bat" --check   only reports what is installed (nothing is installed or started); exit code 0 = ready
setlocal
cd /d "%~dp0"
title HC09 Editor
set "CHECK_ONLY="
if /i "%~1"=="--check" set "CHECK_ONLY=1"
set "PYCON="
set "PYGUI="
set "PROBLEM="

rem ---- Python 3.9 or newer with tkinter (the python.exe the Microsoft Store stub installs does not count)
call :trypy python
if not defined PYCON call :trypy py -3
if defined PYCON (
  echo [ok] Python found: %PYCON%
  if /i "%PYCON%"=="python" ( where pythonw >nul 2>nul && set "PYGUI=pythonw" )
  if /i "%PYCON%"=="py -3" ( where pyw >nul 2>nul && set "PYGUI=pyw -3" )
  if not defined PYGUI set "PYGUI=%PYCON%"
) else (
  echo [MISSING] Python 3.9 or newer, with Tk. Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  set "PROBLEM=1"
)

rem ---- Node.js 18 or newer
where node >nul 2>nul
if errorlevel 1 (
  echo [MISSING] Node.js 18 or newer. Install it from https://nodejs.org/ ^(the LTS version^).
  set "PROBLEM=1"
) else (
  node -e "process.exit(Number(process.versions.node.split('.')[0])>=18?0:1)" >nul 2>nul
  if errorlevel 1 (
    echo [MISSING] Node.js is older than 18. Install the current LTS version from https://nodejs.org/
    set "PROBLEM=1"
  ) else (
    echo [ok] Node.js found
  )
)

if defined PROBLEM goto :problem

rem ---- the bridge's dependencies (first start only)
if exist "hc09-bridge\node_modules\madden-file-tools\package.json" (
  echo [ok] The bridge's dependencies are installed
) else (
  if defined CHECK_ONLY (
    echo [info] The bridge's dependencies will be installed on the first start ^(npm install^)
  ) else (
    echo Installing the bridge's dependencies ^(first start only, needs internet^)...
    pushd hc09-bridge
    call npm install --no-audit --no-fund
    popd
    if not exist "hc09-bridge\node_modules\madden-file-tools\package.json" (
      echo [FAILED] npm install did not finish. Check your internet connection and run this again.
      goto :problem
    )
  )
)

if defined CHECK_ONLY (
  echo Ready: the editor would start with: %PYGUI% guiHC09.py
  exit /b 0
)
start "" %PYGUI% guiHC09.py
exit /b 0

:problem
echo.
if defined CHECK_ONLY exit /b 1
echo Fix the above, then double-click this file again.
pause
exit /b 1

:trypy
%* -c "import sys, tkinter; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
if not errorlevel 1 set "PYCON=%*"
exit /b 0
