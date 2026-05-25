from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

from app import models

_BACKEND_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


def load_backend_env() -> None:
    """Load environment variables from backend/.env only.

    This prevents accidentally loading a different .env from the current working directory.
    """

    load_dotenv(dotenv_path=_BACKEND_ENV_PATH, override=False)
