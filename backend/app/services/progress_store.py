import time
from typing import Any

_progress: dict[str, dict[str, Any]] = {}

def update(document_id: str, **data: Any) -> None:
    payload = dict(data)
    payload["document_id"] = document_id
    payload["updated_at"] = time.time()
    _progress[document_id] = payload

def get(document_id: str) -> dict[str, Any] | None:
    return _progress.get(document_id)
