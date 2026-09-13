@echo off
REM ===================================================================
REM  Esquared Academy LMS - start the site.
REM
REM  Double-click this. It starts the database, then the web server, and
REM  leaves this window open. The site is live only while this window
REM  stays open - closing it stops the site.
REM
REM  To stop: press Ctrl+C, or just close the window.
REM ===================================================================
setlocal
cd /d "%~dp0"
set "PY=venv\Scripts\python.exe"

if not exist "%PY%" (
  echo.
  echo   Could not find %PY%
  echo   This file has to sit in the project folder, beside manage.py.
  echo.
  pause
  exit /b 1
)

echo.
echo   Starting the database container...
docker start esquared-mysql >nul 2>&1
if errorlevel 1 (
  echo   Could not start it with 'docker start'. Trying docker compose...
  docker compose up -d db
  if errorlevel 1 (
    echo.
    echo   The database would not start. Docker Desktop is probably not
    echo   running - start Docker Desktop, wait for the whale icon to go
    echo   steady, then run this file again.
    echo.
    pause
    exit /b 1
  )
) else (
  echo   Database is up.
)

echo.
echo ===================================================================
echo   The site will be at:   http://127.0.0.1:8000/admin/
echo.
echo   Leave this window open. Closing it stops the site.
echo   Press Ctrl+C to stop.
echo ===================================================================
echo.

"%PY%" manage.py runserver

echo.
echo   The server has stopped.
pause
