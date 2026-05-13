from fastapi import FastAPI
from celery import Celery
import os

# Initialize FastAPI application
app = FastAPI()

@app.get("/ping")
async def ping():
    return {"status": "ok"}

# Initialize Celery application
# REDIS_URL is expected to be set in the environment (from .env)
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
celery_app = Celery(__name__, broker=redis_url, backend=redis_url)

# Example task to verify worker startup (optional)
@celery_app.task
def add(x: int, y: int) -> int:
    return x + y
