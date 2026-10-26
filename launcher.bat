@echo off
cd /d "%~dp0"

echo ============================================
echo  SLM Risk Governance Agent - Launcher
echo ============================================
echo.
echo Starts the Streamlit app from this folder. If you have not run setup.bat yet, do that first.
echo.
echo [INFO] Running from: %CD%
echo.

:: Check virtual environment exists
if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found. Run setup.bat first.
    pause
    exit /b 1
)

:: Activate virtual environment
call venv\Scripts\activate.bat

:: Check Ollama (optional; app still starts if Ollama is down)
echo [INFO] Checking Ollama...
curl -s http://localhost:11434/api/version >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARN] Ollama not reachable at http://localhost:11434
    echo        The app will start but LLM calls will fail.
    echo        Open another terminal and run: ollama serve
    echo        Then: ollama pull gemma2:2b
    echo.
)

:: Launch Streamlit
echo [INFO] Starting Streamlit app...
echo        Close this window or press Ctrl+C to stop.
echo.
streamlit run app.py --server.port 8501 --browser.gatherUsageStats false
