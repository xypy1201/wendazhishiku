@echo off
cd /d "%~dp0"
python -B -X utf8 scripts\verify_upload.py
pause
