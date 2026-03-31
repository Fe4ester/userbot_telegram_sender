@echo on
setlocal

where poetry >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Poetry not found in PATH.
  echo Install Poetry and reopen terminal.
  pause
  exit /b 1
)

poetry install --with dev
if errorlevel 1 (
  echo [ERROR] poetry install failed.
  pause
  exit /b 1
)

poetry run pyinstaller ^
  --noconfirm ^
  --clean ^
  --name TG-Broadcaster-Debug ^
  --console ^
  --onedir ^
  --paths src ^
  --hidden-import tg_spam.ui_app ^
  --hidden-import tg_spam.paths ^
  --add-data "src/tg_spam/web;tg_spam/web" ^
  src/tg_spam/browser_app.py
if errorlevel 1 (
  echo [ERROR] Build failed.
  pause
  exit /b 1
)

echo [OK] Build completed. Run dist\TG-Broadcaster-Debug\TG-Broadcaster-Debug.exe
pause
endlocal
