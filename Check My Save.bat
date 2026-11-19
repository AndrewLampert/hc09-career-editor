@echo off
rem Drag a Head Coach 09 save (the file, or the folder it is in) onto this file to see what the save holds. It reads the save and never changes it.
rem Use it when a tab of the editor is empty (Draft Picks, Playbooks): the report says whether the save has the table at all, has it empty, or has it filled,
rem and writes the same report to check_save_report.txt in this folder so it can be sent on. Double-click it instead to type or paste the save's path.
rem (This file does not change the folder it was started in, so a relative path given on the command line means what the person who typed it meant; check_save.py finds its own folder.)
setlocal
title HC09 save check
set "PYCON="

call :trypy python
if not defined PYCON call :trypy py -3
if not defined PYCON (
  echo [MISSING] Python 3.9 or newer. Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  echo.
  pause
  exit /b 1
)

%PYCON% "%~dp0check_save.py" %*
set "RC=%errorlevel%"
echo.
pause
exit /b %RC%

:trypy
%* -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
if not errorlevel 1 set "PYCON=%*"
exit /b 0
