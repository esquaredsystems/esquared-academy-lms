@echo off
setlocal
cd /d "%~dp0"

echo Stopping the previously running deployment...
docker compose down
if errorlevel 1 (
  echo.
  echo Could not stop the previous Docker deployment.
  exit /b 1
)

echo Building and starting Esquared Academy LMS...
docker compose up --build -d
if errorlevel 1 (
  echo.
  echo Docker deployment failed. Check the output above.
  exit /b 1
)

echo.
echo App is running at http://127.0.0.1:8000/admin/
echo Use "docker compose logs -f app" to view application logs.
endlocal
