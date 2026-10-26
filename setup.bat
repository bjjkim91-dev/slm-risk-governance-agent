@echo off
cd /d "%~dp0"

echo ============================================
echo  SLM Risk Governance Agent - Setup
echo ============================================
echo.
echo This script only prepares the Python app in this folder:
echo   1. Check Python 3.10+
echo   2. Create a virtual environment (venv) here if missing
echo   3. Install packages from requirements.txt into that venv
echo   4. Create data\uploads and data\outputs
echo   5. If Ollama is already installed and running, download gemma2:2b
echo.
echo Ollama itself is not installed by this file - see README.md first.
echo Installing into:
echo   %CD%
echo You may place this project anywhere (Desktop, Documents, USB, etc.).
echo.

:: ---------------------------------------------------------------------------
:: STEP 1 of 5 - Python
:: ---------------------------------------------------------------------------
echo [STEP 1/5] Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found on PATH.
    echo         Install Python 3.10 or newer from https://www.python.org/downloads/
    echo         Re-run the installer and enable "Add python.exe to PATH", then open a
    echo         new Command Prompt and run setup.bat again.
    pause
    exit /b 1
)
python --version
echo [OK] Python is available.
echo.

:: ---------------------------------------------------------------------------
:: STEP 2 of 5 - Virtual environment
:: ---------------------------------------------------------------------------
echo [STEP 2/5] Virtual environment...
if not exist "venv" (
    echo [INFO] Creating venv in this folder ^(first run only^)...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Could not create venv. Check Python installation and disk space.
        pause
        exit /b 1
    )
    echo [OK] venv created.
) else (
    echo [OK] venv already exists ^(skipping create^).
)
echo.

:: ---------------------------------------------------------------------------
:: STEP 3 of 5 - Dependencies
:: ---------------------------------------------------------------------------
echo [STEP 3/5] Installing Python dependencies into venv...
echo         This may take a few minutes the first time.
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] pip install failed. Read messages above ^(network, disk, or conflict^).
    pause
    exit /b 1
)
echo [OK] requirements.txt installed.
echo.

:: ---------------------------------------------------------------------------
:: STEP 4 of 5 - Data folders
:: ---------------------------------------------------------------------------
echo [STEP 4/5] Data folders for uploads and exports...
if not exist "data" mkdir data
if not exist "data\uploads" mkdir data\uploads
if not exist "data\outputs" mkdir data\outputs
echo [OK] data\uploads and data\outputs are ready.
echo.

:: ---------------------------------------------------------------------------
:: STEP 5 of 5 - Ollama model (Ollama app must already be installed; see README)
:: ---------------------------------------------------------------------------
echo [STEP 5/5] Ollama - optional model download...
echo         If Ollama is running, we pull gemma2:2b (~1.5 GB^). If not, skip and
echo         pull later after you start Ollama:  ollama pull gemma2:2b
echo.
where curl >nul 2>&1
if %errorlevel% neq 0 (
    echo [SKIP] curl not in PATH - cannot probe Ollama. When Ollama runs:  ollama pull gemma2:2b
    goto :after_ollama
)
curl -s http://localhost:11434/api/version >nul 2>&1
if %errorlevel% neq 0 (
    echo [SKIP] Ollama is not responding at http://localhost:11434
    echo        Start Ollama, then either re-run setup.bat or run:  ollama pull gemma2:2b
) else (
    echo [OK] Ollama is running. Pulling gemma2:2b ^(may take several minutes^)...
    ollama pull gemma2:2b
    if %errorlevel% neq 0 (
        echo [WARN] ollama pull failed. When ready, run:  ollama pull gemma2:2b
    ) else (
        echo [OK] gemma2:2b is ready.
    )
)
:after_ollama

echo.
echo ============================================
echo  Setup finished.
echo ============================================
echo.
echo NEXT:
echo   1. Double-click launcher.bat ^(same folder as this file^)
echo   2. Open the browser URL shown ^(usually http://localhost:8501^)
echo.
echo If the app cannot talk to the model: start Ollama and ensure gemma2:2b is pulled.
echo See README.md for full steps and troubleshooting.
echo ============================================
pause
