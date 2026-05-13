import os
import subprocess
from pathlib import Path

def generate_semantic_tree(document_id: str) -> Path:
    """
    Sử dụng PageIndex Framework kết nối với OpenRouter LLM.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("Thiếu biến môi trường OPENROUTER_API_KEY")

    pdf_path = Path("data/raw/test-38.pdf")
    if not pdf_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file {pdf_path}")

    out_dir = Path("data/semantic_trees")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{document_id}.json"

    # Set up environment variables for PageIndex according to Issue #237
    env = os.environ.copy()
    env["OPENAI_API_BASE"] = "https://openrouter.ai/api/v1"
    env["OPENAI_API_KEY"] = api_key

    # Choose model from OpenRouter (prefix openai/ to bypass PageIndex validation)
    model_name = "openai/google/gemini-2.5-flash"  # or openai/anthropic/claude-3.5-sonnet

    print(f"Đang kích hoạt PageIndex Framework với model: {model_name}...")

    # Run PageIndex CLI (assumed to be provided by the package)
    try:
        cmd = [
            "python3", "-m", "pageindex",
            "--model", model_name,
            "--pdf_path", str(pdf_path),
            "--output_path", str(out_path)
        ]
        print(f"[NOTE] Hệ thống đã thiết lập ENV. Đang chạy xử lý...")
        # Execute the command
        result = subprocess.run(cmd, env=env, capture_output=True, text=True, check=True)
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Lỗi khi chạy PageIndex local: {e.stderr}")
        raise
    except Exception as e:
        print(f"Lỗi khi chạy PageIndex local: {e}")
        raise

    return out_path
