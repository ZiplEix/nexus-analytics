@echo off
pushd "%~dp0"
echo ==========================================
echo      NEXUS ANALYTICS - WINDOWS LAUNCH
echo ==========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python from https://www.python.org/downloads/
    pause
    exit /b
)

echo [1/2] Installing dependencies...
pip install flask requests google-generativeai python-dotenv urllib3

echo.
echo [2/2] Starting Server...
echo.
echo Open your browser at: http://127.0.0.1:5000
echo.

REM Unset WINDOWS_HOST to force localhost usage
set WINDOWS_HOST=127.0.0.1

python app.py
popd
pause
