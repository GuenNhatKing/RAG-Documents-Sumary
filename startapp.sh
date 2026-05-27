ollama serve &
source .venv/bin/activate
cd /work/backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
cd ../frontend
npm run dev