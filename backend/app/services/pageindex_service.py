import os
import json
import time
from pathlib import Path
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

from app.services.pageindex.page_index_md import md_to_tree
from app.services.pageindex.utils import ConfigLoader
from dotenv import load_dotenv

load_dotenv()


def _log(step: str):
    print(f"[LOG] {step}", flush=True)


def split_text_by_paragraphs(text: str, max_words: int = 1024) -> list[str]:
    """
    Chia văn bản theo các đoạn (dựa trên 2 lần xuống dòng \n\n).
    Gom các đoạn lại thành các khối (chunk) không vượt quá giới hạn từ để tối ưu API,
    đảm bảo không bao giờ cắt ngang giữa câu hoặc giữa đoạn.
    """
    paragraphs = text.split("\n\n")

    chunks = []
    current_chunk = []
    current_word_count = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        word_count = len(para.split())

        if current_word_count + word_count > max_words and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            current_chunk = [para]
            current_word_count = word_count
        else:
            current_chunk.append(para)
            current_word_count += word_count

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return chunks


@retry(
    stop=stop_after_attempt(12),
    wait=wait_fixed(30),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def call_openrouter_with_retry(
    client: OpenAI,
    model_name: str,
    prompt: str,
):
    response = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )

    content = response.choices[0].message.content

    if not content:
        raise ValueError("API trả về None hoặc rỗng (Khả năng do quá tải hoặc filter).")

    return content.strip()


def process_chunks_with_retry(client: OpenAI, prompt_template: str, text_data: str, stage_name: str) -> str:
    """Xử lý cắt nhỏ văn bản, gọi API với cơ chế retry 12 lần, mỗi lần chờ 30s, và ghép lại."""

    model_name = os.getenv("OPENROUTER_MODEL")

    chunks = split_text_by_paragraphs(text_data, max_words=1024)
    total_chunks = len(chunks)

    _log(f"[{stage_name}] Đã gom văn bản thành {total_chunks} phần (nguyên vẹn theo từng đoạn, tối đa ~1024 từ/phần).")

    successful_results = []

    for idx, chunk_text in enumerate(chunks, start=1):
        try:
            _log(f"[{stage_name}] Đang xử lý phần {idx}/{total_chunks}...")

            prompt = prompt_template + f"\nINPUT:\n{chunk_text}"

            content = call_openrouter_with_retry(
                client=client,
                model_name=model_name,
                prompt=prompt,
            )

            successful_results.append(content)
            _log(f"[{stage_name}] -> Phần {idx} THÀNH CÔNG.")

        except Exception as e:
            _log(f"[{stage_name}] -> THẤT BẠI HOÀN TOÀN phần {idx} sau 12 lần thử. Bỏ qua phần này.")
            _log(f"[{stage_name}] -> Lỗi cuối cùng: {str(e)}")

    final_text = "\n\n".join(successful_results)

    _log(f"[{stage_name}] HOÀN THÀNH. Có {len(successful_results)}/{total_chunks} phần thành công.")

    return final_text


def _clean_and_format_to_markdown(doc_id: str) -> Path:
    _log(f"START markdown pipeline: {doc_id}")

    base_path = Path("data/extracted_text") / doc_id
    _log(f"Checking extracted path: {base_path}")

    page_files = sorted(base_path.glob("page_*.txt"))
    _log(f"Found pages: {len(page_files)}")

    if not page_files:
        raise FileNotFoundError(f"Không tìm thấy file tại {base_path}")

    # =============================
    # LOAD TEXT
    # =============================
    _log("Loading page content...")
    pages = []
    for idx, page_file in enumerate(page_files, start=1):
        content = page_file.read_text(encoding="utf-8")
        pages.append(f"=== PAGE {idx} ===\n{content}")

    raw_text = "\n\n".join(pages)
    _log(f"Raw text length: {len(raw_text)} chars")

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("Thiếu OPENROUTER_API_KEY")

    _log("OpenRouter API key OK")

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        default_headers={
            "HTTP-Referer": "http://localhost",
            "X-Title": "OCR_Pipeline"
        }
    )

    # =============================
    # STAGE 1 - OCR REPAIR
    # =============================
    _log("STAGE 1: OCR repair start")

    repair_prompt = """YOU ARE A LOSSLESS OCR CORRECTION ENGINE FOR VIETNAMESE ADMINISTRATIVE DOCUMENTS.
    Rules:
    - Preserve original meaning exactly.
    - Do NOT summarize, paraphrase, rewrite, or simplify.
    - Preserve numbering, clauses, hierarchy, and document structure.
    - If uncertain, keep original text unchanged.

    Required operations:

    1. Merge broken sentences caused by OCR line breaks or page breaks into continuous paragraphs.

    2. Repair OCR corruption caused by:
    - broken Vietnamese diacritics
    - missing accents
    - symbol substitution
    - random inserted characters
    - mixed encoding
    - visually similar characters
    - OCR spelling mistakes

    Examples:
    - "thâm quyền" -> "thẩm quyền"
    - "căn cử" -> "căn cứ"
    - "nghi dinh" -> "nghị định"
    - "Van b2e" -> "Vấn đề"
    - "$30" -> "số"

    Use surrounding context to infer intended text.
    Only correct when highly confident.
    Prefer semantic consistency over literal character preservation when corruption is obvious.

    3. Remove OCR noise:
    - digital signature metadata
    - repeated headers/footers
    - page markers
    - standalone page numbers
    - meaningless OCR symbols
    - duplicated broken fragments

    Output:
    - plain clean text only
    - no markdown
    - no explanations
    - no comments
    - preserve meaningful paragraphs and punctuation"""

    start_time_stage_1 = time.time()

    cleaned_text = process_chunks_with_retry(
        client=client,
        prompt_template=repair_prompt,
        text_data=raw_text,
        stage_name="STAGE 1"
    )

    _log(f"STAGE 1 DONE in {time.time() - start_time_stage_1:.2f}s")
    _log(f"Cleaned text length: {len(cleaned_text)}")

    normalized_dir = Path("data/normalized_text")
    normalized_dir.mkdir(parents=True, exist_ok=True)
    normalized_path = normalized_dir / f"{doc_id}.txt"
    normalized_path.write_text(cleaned_text, encoding="utf-8")
    _log(f"Saved normalized text: {normalized_path}")

    # =============================
    # STAGE 2 - MARKDOWN
    # =============================
    _log("STAGE 2: Markdown conversion start")

    structure_prompt = """YOU ARE A STRICT LOSSLESS MARKDOWN STRUCTURING ENGINE FOR VIETNAMESE ADMINISTRATIVE DOCUMENTS.

    CRITICAL RULES (HARD CONSTRAINTS):
    - DO NOT change, rewrite, summarize, or reformat content.
    - DO NOT add ANY new characters not present in input, EXCEPT Markdown heading tags (#, ##, ###, ####).

    ABSOLUTE FORBIDDEN:
    - No emojis
    - No icons
    - No decorative symbols
    - No fancy bullets (•, ➤, ▪, etc.)
    - No extra punctuation added for styling
    - No commentary text
    - No explanations

    MANDATORY MARKDOWN FORMATTING (YOU MUST APPLY THIS):
    You must analyze the document's hierarchy and insert standard Markdown Headings by adding '#' and a SPACE at the beginning of the relevant lines. Apply the following rules based on Vietnamese document structures:

    1. LEVEL 1 HEADINGS (#):
    - Document Titles / Types (e.g., "CÔNG ĐIỆN", "QUYẾT ĐỊNH", "CHỈ THỊ", "NGHỊ QUYẾT", "BÁO CÁO")
    - Lines starting with "PHẦN" or "CHƯƠNG"

    2. LEVEL 2 HEADINGS (##):
    - Lines starting with "MỤC" or "ĐIỀU"
    - Lines starting with Roman numerals (e.g., "I.", "II.", "III.")

    3. LEVEL 3 HEADINGS (###):
    - Lines starting with "KHOẢN"
    - Lines starting with numbers indicating major sections (e.g., "1.", "2.", "3.")

    4. LEVEL 4 HEADINGS (####):
    - Lines starting with lowercase letters indicating subsections (e.g., "a)", "b)", "c)", "d)")

    PRESERVE EXACTLY:
    - Every character of the original text
    - Line breaks
    - Punctuation

    OUTPUT RULE: 
    - Output must be pure Markdown text.
    - Must be a character-level superset of the input (only adding '#' and spaces for headings, no deletion, no modification of actual words)."""

    start_time_stage_2 = time.time()

    md_content = process_chunks_with_retry(
        client=client,
        prompt_template=structure_prompt,
        text_data=cleaned_text,
        stage_name="STAGE 2"
    )

    _log(f"STAGE 2 DONE in {time.time() - start_time_stage_2:.2f}s")
    _log(f"Markdown length: {len(md_content)}")

    md_dir = Path("data/markdown_docs")
    md_dir.mkdir(parents=True, exist_ok=True)
    md_path = md_dir / f"{doc_id}.md"
    md_path.write_text(md_content, encoding="utf-8")
    _log(f"Saved markdown: {md_path}")

    _log("Markdown pipeline DONE")
    return md_path


async def generate_semantic_tree(document_id: str) -> Path:
    _log(f"START semantic tree: {document_id}")

    md_path = _clean_and_format_to_markdown(document_id)
    _log(f"Markdown ready: {md_path}")

    out_dir = Path("data/semantic_trees")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{document_id}.json"

    try:
        _log("Bắt đầu parse Markdown bằng PageIndex md_to_tree...")
        start = time.time()

        config_loader = ConfigLoader()
        opt = config_loader.load({})
        _log(f"Model thực tế đang chuẩn bị chạy: {opt.model}")

        semantic_tree = await md_to_tree(
            md_path=str(md_path),
            if_thinning=False,
            min_token_threshold=5000,
            if_add_node_summary=opt.if_add_node_summary,
            summary_token_threshold=200,
            model=opt.model,
            if_add_doc_description=opt.if_add_doc_description,
            if_add_node_text=opt.if_add_node_text,
            if_add_node_id=opt.if_add_node_id
        )

        _log(f"TREE DONE in {time.time() - start:.2f}s")
        _log("Saving JSON...")

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(semantic_tree, f, ensure_ascii=False, indent=2)

        _log(f"SAVED: {out_path}")
        return out_path

    except Exception as e:
        _log(f"ERROR OCCURRED: {str(e)}")
        raise