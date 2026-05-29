"""Semantic tree generation module.

This module depends on markdown_docs.py. It ensures the Markdown document exists,
then calls PageIndex md_to_tree and saves data/semantic_trees/{document_id}.json.
"""

import argparse
import asyncio
import json
import time
from pathlib import Path

try:
    from app.env import load_backend_env
    load_backend_env()
except Exception:
    pass

from app.services.pageindex.page_index_md import md_to_tree
from app.services.pageindex.utils import ConfigLoader
from app.services.master_tree import add_doc_to_master_tree
from app.services.progress_store import update as update_progress_store


TREE_WORK_DIR = Path("data") / "tree_work"


def _log(step: str) -> None:
    print(f"[TREE] {step}", flush=True)


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _update_progress(document_id: str, **data) -> None:
    payload = dict(data)
    payload["document_id"] = document_id
    payload["updated_at"] = time.time()
    _save_json(TREE_WORK_DIR / document_id / "progress.json", payload)
    update_progress_store(document_id, **data)


def ensure_markdown_doc(document_id: str, md_path: str | Path | None = None) -> Path:
    if md_path is not None:
        path = Path(md_path)
        if path.exists():
            return path
        raise FileNotFoundError(f"Không tìm thấy Markdown file: {path}")

    path = Path("data/markdown_docs") / f"{document_id}.md"
    if path.exists():
        return path

    try:
        try:
            from .markdown_docs import generate_markdown_doc
        except ImportError:
            from markdown_docs import generate_markdown_doc

        return generate_markdown_doc(document_id)
    except Exception as e:
        raise FileNotFoundError(
            f"Không tìm thấy markdown_docs/{document_id}.md và không thể tự tạo. Lỗi: {e}"
        ) from e


async def generate_semantic_tree(document_id: str, md_path: str | Path | None = None) -> Path:
    _log(f"START semantic tree: {document_id}")

    md_path = ensure_markdown_doc(document_id=document_id, md_path=md_path)
    _log(f"Markdown ready: {md_path}")
    _update_progress(document_id, status="parsing", message="Đang phân tích Markdown...")

    out_dir = Path("data/semantic_trees")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{document_id}.json"

    try:
        _log("Bắt đầu parse Markdown bằng PageIndex md_to_tree...")
        start = time.time()

        config_loader = ConfigLoader()
        opt = config_loader.load({})
        _update_progress(document_id, status="building", message="Đang xây dựng cây ngữ nghĩa...", model=opt.model)

        semantic_tree = await md_to_tree(
            md_path=str(md_path),
            if_thinning=False,
            min_token_threshold=5000,
            if_add_node_summary=opt.if_add_node_summary,
            summary_token_threshold=200,
            model=opt.model,
            if_add_doc_description=opt.if_add_doc_description,
            if_add_node_text=opt.if_add_node_text,
            if_add_node_id=opt.if_add_node_id,
        )

        _log(f"TREE DONE in {time.time() - start:.2f}s")
        _log("Saving JSON...")

        with out_path.open("w", encoding="utf-8") as f:
            json.dump(semantic_tree, f, ensure_ascii=False, indent=2)
        _update_progress(document_id, status="saving", message="Đang lưu cây ngữ nghĩa...")

        _log(f"SAVED: {out_path}")

        # Update master tree with document summary
        try:
            doc_name = Path(md_path).stem
            _update_progress(document_id, status="updating", message="Đang cập nhật cây tổng thể...")
            add_doc_to_master_tree(document_id, doc_name, semantic_tree)
            _log("Master tree updated.")
        except Exception as mt_err:
            _log(f"Warning: master tree update failed: {mt_err}")

        _update_progress(document_id, status="done", message="Hoàn thành")
        return out_path

    except Exception as e:
        _update_progress(document_id, status="error", message=str(e))
        _log(f"ERROR OCCURRED: {str(e)}")
        raise
