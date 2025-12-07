@echo off
REM TTB Label Verifier - Docker Test Script (Windows CMD)
REM Simple wrapper for Docker build and run commands

set IMAGE_NAME=ttb-label-verifier
set IMAGE_TAG=local
set CONTAINER_NAME=ttb-test
set PORT=8000

echo === TTB Label Verifier - Docker Test ===
echo.

echo Step 1: Building Docker image...
docker build -t %IMAGE_NAME%:%IMAGE_TAG% .

if errorlevel 1 (
    echo Build failed!
    exit /b 1
)

echo.
echo Step 2: Cleaning up existing containers...
docker stop %CONTAINER_NAME% 2>nul
docker rm %CONTAINER_NAME% 2>nul

echo.
echo Step 3: Starting container...
docker run -d --name %CONTAINER_NAME% -p %PORT%:8000 %IMAGE_NAME%:%IMAGE_TAG%

if errorlevel 1 (
    echo Failed to start container!
    exit /b 1
)

echo.
echo Container started successfully!
echo.
echo Application will be available at: http://localhost:%PORT%
echo API docs available at: http://localhost:%PORT%/docs
echo.
echo To stop the container, run:
echo   docker stop %CONTAINER_NAME% ^&^& docker rm %CONTAINER_NAME%
echo.
echo To view logs:
echo   docker logs -f %CONTAINER_NAME%
echo.
echo Waiting a few seconds for application to start...
timeout /t 5 /nobreak >nul
echo.
echo Testing health endpoint...
curl http://localhost:%PORT%/health
echo.
echo.
echo Container is running. Press any key to stop and remove it...
pause >nul

echo.
echo Stopping container...
docker stop %CONTAINER_NAME%
docker rm %CONTAINER_NAME%
echo Done!

