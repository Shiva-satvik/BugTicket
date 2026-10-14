@echo off
setlocal
cd /d "%~dp0bugpilot-frontend"
where node >nul 2>&1
if errorlevel 1 (
  echo Node.js was not found. Install Node.js 22.12 or newer and restart this terminal.
  pause
  exit /b 1
)
where npm >nul 2>&1
if errorlevel 1 (
  echo npm was not found. Reinstall Node.js with npm enabled.
  pause
  exit /b 1
)
if not exist ".env" copy .env.example .env >nul
if not exist "node_modules\vite\bin\vite.js" (
  npm install
  if errorlevel 1 (
    echo Frontend dependency installation failed. Check your internet connection.
    pause
    exit /b 1
  )
)
npm run dev
pause
