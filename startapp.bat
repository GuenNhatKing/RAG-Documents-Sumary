@echo off
cd /D "%~dp0backend"
start /B uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
cd /D "%~dp0frontend"
npm run dev
