@echo off
setlocal

poetry install --with dev
poetry run pyinstaller ^
  --noconfirm ^
  --clean ^
  --name TG-Broadcaster ^
  --windowed ^
  --onefile ^
  --paths src ^
  --collect-submodules webview ^
  --add-data "src/tg_spam/web;tg_spam/web" ^
  src/tg_spam/desktop.py

endlocal
