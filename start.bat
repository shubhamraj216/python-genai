@echo off
REM Windows startup script for Image Generation API

echo ================================================
echo   Image Generation API - Startup Script
echo ================================================
echo.

REM Check if .env file exists
if not exist .env (
    echo [WARNING] .env file not found
    echo Creating .env from .env.example...
    
    if exist .env.example (
        copy .env.example .env
        echo [SUCCESS] Created .env file from .env.example
        echo Please edit .env and add your API keys before continuing
        echo.
        pause
        exit /b 1
    ) else (
        echo [ERROR] .env.example not found. Please create a .env file manually
        echo.
        pause
        exit /b 1
    )
)

echo [SUCCESS] Found .env file

REM Check if virtual environment exists
if not exist venv (
    if not exist .venv (
        echo [WARNING] Virtual environment not found
        echo Creating virtual environment...
        python -m venv venv
        echo [SUCCESS] Virtual environment created
    )
)

REM Activate virtual environment
if exist venv\Scripts\activate.bat (
    echo Activating virtual environment (venv)...
    call venv\Scripts\activate.bat
) else if exist .venv\Scripts\activate.bat (
    echo Activating virtual environment (.venv)...
    call .venv\Scripts\activate.bat
)

echo [SUCCESS] Virtual environment activated

REM Check if dependencies are installed
echo Checking dependencies...
python -c "import fastapi" 2>nul
if errorlevel 1 (
    echo [WARNING] Dependencies not installed
    echo Installing dependencies from requirements.txt...
    pip install -r requirements.txt
    echo [SUCCESS] Dependencies installed
) else (
    echo [SUCCESS] Dependencies already installed
)

REM Create necessary directories
echo Creating necessary directories...
if not exist assets\generated mkdir assets\generated
if not exist assets\db mkdir assets\db
if not exist logs mkdir logs
echo [SUCCESS] Directories ready

echo.
echo ================================================
echo Starting FastAPI Application
echo ================================================
echo.
echo Press Ctrl+C to stop the server
echo.

REM Run the application
python app.py

