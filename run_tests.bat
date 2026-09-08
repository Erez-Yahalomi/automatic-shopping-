@echo off
setlocal

cd /d "%~dp0"

echo Checking Docker Desktop...
docker info >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: Docker Desktop is not running or Docker is not available.
    echo Start Docker Desktop, wait until it is running, and try again.
    exit /b 1
)

if not exist results mkdir results

echo.
echo Building the annotated detector image...
docker build -t weight-event-detector-complete .
if errorlevel 1 (
    echo.
    echo ERROR: Docker image build failed.
    exit /b 1
)

echo.
echo Running the complete test suite and creating the text report...
docker run --rm ^
  -e TEST_REPORT_PATH=/app/results/test_results.txt ^
  -v "%CD%\results:/app/results" ^
  --entrypoint python weight-event-detector-complete test_weight_event_detector.py
if errorlevel 1 (
    echo.
    echo TESTS FAILED. See results\test_results.txt for details.
    exit /b 1
)

echo.
echo All tests passed successfully.
echo Detailed report saved to results\test_results.txt
exit /b 0
