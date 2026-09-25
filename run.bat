@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (set "PY=py -3") else (set "PY=python")
if not exist .venv ( %PY% -m venv .venv || (pause & exit /b 1) )
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt || (pause & exit /b 1)
where ffmpeg >nul 2>nul || (echo FFmpeg not found in PATH. & pause & exit /b 1)
start "" http://127.0.0.1:5000
python app.py
pause
