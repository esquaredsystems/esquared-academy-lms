@echo off
REM ===================================================================
REM  Esquared Academy LMS - setup, with a log.
REM
REM  Double-click this file. Every step's output is written to
REM  setup_log.txt beside it, and printed to the screen at the end, so
REM  the result survives the window being closed.
REM
REM  Safe to run as often as you like: migrations, roles, the import and
REM  the lesson generator all match on what is already there and update
REM  rather than duplicate.
REM ===================================================================
setlocal
cd /d "%~dp0"
set "PY=venv\Scripts\python.exe"
set "LOG=setup_log.txt"

if not exist "%PY%" (
  echo.
  echo   Could not find %PY%
  echo   This file has to sit in the project folder, beside manage.py.
  echo.
  pause
  exit /b 1
)

echo Esquared Academy LMS setup - %DATE% %TIME% > "%LOG%"

echo.
echo   Running setup. Each step is logged to setup_log.txt
echo.

call :step "1 of 6  Applying database migrations"            migrate
if errorlevel 1 goto :failed
call :step "2 of 6  Creating the twelve roles"               seed_roles
if errorlevel 1 goto :failed
call :step "3 of 6  Importing staff, students and timetable" import_setup docs\setup_data.json
if errorlevel 1 goto :failed
call :step "4 of 6  Creating logins for students"            seed_student_logins --commit
if errorlevel 1 goto :failed
call :step "5 of 6  Building this fortnight's lessons"       generate_lessons --weeks 2
if errorlevel 1 goto :failed
call :step "6 of 6  Where every account stands"              account_status

echo.
echo ===================================================================
echo   Everything above, in full
echo ===================================================================
type "%LOG%"

echo.
echo ===================================================================
echo   Now set the password for the teacher account.
echo   Type it twice. Nothing appears as you type - that is normal.
echo ===================================================================
"%PY%" manage.py reset_login uxair.ahm --set

echo.
echo   Finished. Start the server with:
echo       venv\Scripts\python.exe manage.py runserver
echo   then open  http://127.0.0.1:8000/admin/
echo.
pause
exit /b 0

REM -- run one manage.py command, on screen and into the log -----------
:step
set "TITLE=%~1"
shift
echo   %TITLE%
echo. >> "%LOG%"
echo =================================================================== >> "%LOG%"
echo %TITLE% >> "%LOG%"
echo =================================================================== >> "%LOG%"
"%PY%" manage.py %1 %2 %3 %4 %5 >> "%LOG%" 2>&1
if errorlevel 1 (
  echo      ^^^ this step FAILED - see setup_log.txt
  exit /b 1
)
echo      done
exit /b 0

:failed
echo.
echo ===================================================================
echo   A step failed. The error is in setup_log.txt, printed below.
echo ===================================================================
type "%LOG%"
echo.
pause
exit /b 1
