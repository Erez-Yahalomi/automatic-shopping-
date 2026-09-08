@echo off
setlocal

cd /d "%~dp0"

echo Checking Docker Desktop...
docker info >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: Docker Desktop is not running or Docker is not available.
    echo Start Docker Desktop and try again.
    exit /b 1
)

echo.
echo Building the complete detector image...
docker build -t weight-event-detector-complete .
if errorlevel 1 (
    echo.
    echo ERROR: Docker image build failed.
    exit /b 1
)

if not exist results mkdir results

echo.
echo Running the annotated detector...
docker run --rm -v "%CD%\results:/app/results" weight-event-detector-complete python weight_event_detector_annotated.py /app/data/50_gr.csv /app/data/500_gr.csv /app/data/1000_gr.csv --plot --output-directory /app/results
if errorlevel 1 (
    echo.
    echo ERROR: The annotated detector failed.
    exit /b 1
)

echo.
echo Annotated detector finished. Text files and plots are in the results folder.
exit /b 0
