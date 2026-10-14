@echo off
setlocal
cd /d "%~dp0backend"
where py >nul 2>&1
if errorlevel 1 (
  echo Python launcher was not found. Install Python 3.12 and enable PATH.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" py -3.12 -m venv .venv
if not exist ".venv\Scripts\python.exe" (
  echo Could not create the Python 3.12 virtual environment.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
if not exist ".env" copy .env.example .env >nul
python -c "import fastapi, jose, apscheduler, langgraph, chromadb, sentence_transformers, sqlalchemy" >nul 2>&1
if errorlevel 1 (
  python -m pip install --upgrade pip
  pip install -r requirements.txt
  if errorlevel 1 (
    echo Backend dependency installation failed. Check your internet connection and Python version.
    pause
    exit /b 1
  )
)
python -m uvicorn app.api.main:app --reload
pause
