@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -c "import jieba" >nul 2>nul
if errorlevel 1 (
    echo Please install dependencies: python -m pip install -r requirements.txt
    pause
    exit /b 1
)
echo http://127.0.0.1:8765/
python -X utf8 app.py --port 8765
pause
