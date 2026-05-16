import os
import json
import time
import re
from pathlib import Path

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type
from dotenv import load_dotenv

from app.services.pageindex.page_index_md import md_to_tree
from app.services.pageindex.utils import ConfigLoader

load_dotenv()


def _log(step: str):
    print(f"[LOG] {step}", flush=True)


def split_text_by_paragraphs(text: str, max_words: int = 1024) -> list[str]:
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


def is_hard_structural_line(line: str) -> bool:
    stripped = line.strip()

    patterns = [
        r"^={3,}\s*PAGE\s+\d+\s*={3,}$",
        r"^CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM$",
        r"^Độc lập\s*-\s*Tự do\s*-\s*Hạnh phúc$",
        r"^THỦ TƯỚNG CHÍNH PHỦ$",
        r"^(QUYẾT ĐỊNH|NGHỊ QUYẾT|CHỈ THỊ|CÔNG ĐIỆN|BÁO CÁO)$",
        r"^(Điều|ĐIỀU)\s+\d+\.?",
        r"^(Chương|CHƯƠNG)\s+[IVXLCDM\d]+",
        r"^(Mục|MỤC)\s+\d+",
        r"^(Phần|PHẦN)\s+[IVXLCDM\d]+",
    ]

    return any(re.match(pattern, stripped) for pattern in patterns)


def should_merge_lines(prev_line: str, curr_line: str) -> bool:
    prev = prev_line.strip()
    curr = curr_line.strip()

    if not prev or not curr:
        return False

    if is_hard_structural_line(curr):
        return False

    score = 0

    if prev.endswith((",", "-", "–")):
        score += 4

    if not prev.endswith((".", ";", ":", "?", "!", ".”", "”")):
        score += 3

    if re.match(r"^[a-zà-ỹ]", curr):
        score += 3

    if re.match(r"^\((i|ii|iii|iv|v|vi|vii|viii|ix|x)\)", curr.lower()):
        score += 3

    if curr.lower().startswith(
        (
            "và ",
            "hoặc ",
            "của ",
            "theo ",
            "trong ",
            "để ",
            "gửi ",
            "kinh tế ",
            "mục tiêu ",
            "đơn giản ",
            "báo cáo ",
            "hoàn thiện ",
            "liên quan ",
        )
    ):
        score += 2

    if prev.endswith((".", "?", "!")):
        score -= 3

    return score >= 3


def normalize_ocr_line_breaks(text: str) -> str:
    lines = [line.strip() for line in text.splitlines()]
    result: list[str] = []

    for line in lines:
        if not line:
            if result and result[-1] != "":
                result.append("")
            continue

        if not result:
            result.append(line)
            continue

        prev = result[-1]

        if prev == "":
            result.append(line)
            continue

        if should_merge_lines(prev, line):
            result[-1] = prev.rstrip() + " " + line.lstrip()
        else:
            result.append(line)

    normalized = "\n".join(result)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    normalized = re.sub(r"[ \t]{2,}", " ", normalized)

    return normalized.strip()


def extract_markdown_headers(markdown_text: str, max_headers: int = 40) -> list[str]:
    headers = []

    for line in markdown_text.splitlines():
        stripped = line.strip()

        if re.match(r"^#{1,4}\s+", stripped):
            headers.append(stripped)

    return headers[-max_headers:]


def split_inline_roman_headings(markdown_text: str) -> str:
    roman_pattern = r"\((?:i|ii|iii|iv|v|vi|vii|viii|ix|x)\)"

    blocks = markdown_text.split("\n\n")
    result = []

    for block in blocks:
        matches = list(
            re.finditer(
                roman_pattern,
                block,
                flags=re.IGNORECASE,
            )
        )

        if len(matches) >= 2:
            block = re.sub(
                rf"\s+({roman_pattern})\s+",
                r"\n\n#### \1 ",
                block,
                flags=re.IGNORECASE,
            )

        result.append(block)

    return "\n\n".join(result)


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
        raise ValueError("API trả về None hoặc rỗng.")

    return content.strip()


def process_chunks_with_retry(
    client: OpenAI,
    prompt_template: str,
    text_data: str,
    stage_name: str,
) -> str:
    model_name = os.getenv("OPENROUTER_MODEL")

    chunks = split_text_by_paragraphs(text_data, max_words=1024)
    total_chunks = len(chunks)

    _log(f"[{stage_name}] Đã gom văn bản thành {total_chunks} phần.")

    successful_results = []

    for idx, chunk_text in enumerate(chunks, start=1):
        try:
            _log(f"[{stage_name}] Đang xử lý phần {idx}/{total_chunks}...")

            prompt = prompt_template + f"\n\nINPUT:\n{chunk_text}"

            content = call_openrouter_with_retry(
                client=client,
                model_name=model_name,
                prompt=prompt,
            )

            successful_results.append(content)
            _log(f"[{stage_name}] -> Phần {idx} THÀNH CÔNG.")

        except Exception as e:
            _log(f"[{stage_name}] -> THẤT BẠI phần {idx} sau 12 lần thử.")
            _log(f"[{stage_name}] -> Lỗi cuối cùng: {str(e)}")

    final_text = "\n\n".join(successful_results)

    _log(
        f"[{stage_name}] HOÀN THÀNH. "
        f"Có {len(successful_results)}/{total_chunks} phần thành công."
    )

    return final_text


def process_markdown_chunks_with_context(
    client: OpenAI,
    prompt_template: str,
    text_data: str,
    stage_name: str,
) -> str:
    model_name = os.getenv("OPENROUTER_MODEL")

    chunks = split_text_by_paragraphs(text_data, max_words=1024)
    total_chunks = len(chunks)

    _log(f"[{stage_name}] Đã gom văn bản thành {total_chunks} phần có context header.")

    successful_results = []
    previous_headers: list[str] = []

    for idx, chunk_text in enumerate(chunks, start=1):
        try:
            _log(f"[{stage_name}] Đang xử lý phần {idx}/{total_chunks}...")

            context_headers = "\n".join(previous_headers)

            prompt = f"""{prompt_template}

CONTEXT FROM PREVIOUS MARKDOWN BLOCKS:
These headers were created in previous blocks.
Use them only to understand document hierarchy.
Do NOT repeat them unless the current input contains the same heading line.

{context_headers if context_headers else "(No previous headers)"}

CURRENT BLOCK:
{idx}/{total_chunks}

INPUT:
{chunk_text}
"""

            content = call_openrouter_with_retry(
                client=client,
                model_name=model_name,
                prompt=prompt,
            )

            successful_results.append(content)

            previous_headers = extract_markdown_headers(
                "\n\n".join(successful_results),
                max_headers=40,
            )

            _log(f"[{stage_name}] -> Phần {idx} THÀNH CÔNG.")

        except Exception as e:
            _log(f"[{stage_name}] -> THẤT BẠI phần {idx} sau 12 lần thử.")
            _log(f"[{stage_name}] -> Lỗi cuối cùng: {str(e)}")

    final_text = "\n\n".join(successful_results)

    _log(
        f"[{stage_name}] HOÀN THÀNH. "
        f"Có {len(successful_results)}/{total_chunks} phần thành công."
    )

    return final_text


def _clean_and_format_to_markdown(doc_id: str) -> Path:
    _log(f"START markdown pipeline: {doc_id}")

    base_path = Path("data/extracted_text") / doc_id
    _log(f"Checking extracted path: {base_path}")

    page_files = sorted(base_path.glob("page_*.txt"))
    _log(f"Found pages: {len(page_files)}")

    if not page_files:
        raise FileNotFoundError(f"Không tìm thấy file tại {base_path}")

    _log("Loading page content...")

    pages = []
    for idx, page_file in enumerate(page_files, start=1):
        content = page_file.read_text(encoding="utf-8")
        pages.append(f"=== PAGE {idx} ===\n{content}")

    raw_text = "\n\n".join(pages)
    raw_text = normalize_ocr_line_breaks(raw_text)

    _log(f"Raw text length: {len(raw_text)} chars")

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("Thiếu OPENROUTER_API_KEY")

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        default_headers={
            "HTTP-Referer": "http://localhost",
            "X-Title": "OCR_Pipeline",
        },
    )

    # =============================
    # STAGE 1A - OCR REPAIR
    # =============================

    repair_prompt = """YOU ARE A STRICT OCR REPAIR ENGINE FOR VIETNAMESE ADMINISTRATIVE DOCUMENTS.

Your task is to repair OCR errors while preserving the legal meaning and structure.

CRITICAL RULES:
- Do NOT summarize.
- Do NOT paraphrase.
- Do NOT invent missing legal content.
- Preserve all meaningful legal content, numbers, dates, names, agencies, article numbers, clause numbers, and document codes.
- Preserve paragraph order and document order.
- Only correct text when the OCR corruption is obvious or highly likely.
- If uncertain, keep the original text.

LINE BREAK REPAIR:
- Merge OCR-broken lines that belong to the same sentence or paragraph.
- Do not preserve PDF visual wrapping.
- Preserve paragraph breaks only for real structural boundaries.
- Enumerations like (i), (ii), (iii) inside one sentence must stay in the same logical paragraph.

YOU MUST FIX:
- Vietnamese diacritics and spelling errors.
- So -> Số when followed by a legal document number.
- căn cử -> căn cứ.
- thâm quyền -> thẩm quyền.
- nghi dinh -> nghị định.
- thang -> tháng when used in dates.
- nam -> năm when used in dates.
- Random OCR symbols such as @, ””, ?, ¬, | when clearly artifacts.
- Broken administrative headers when context is clear.
- Meaningless OCR fragments only when they carry no legal meaning.

OUTPUT:
- Plain cleaned Vietnamese text only.
- No Markdown.
- No explanations.
- No comments."""

    _log("STAGE 1A: OCR repair start")
    start_time_stage_1a = time.time()

    cleaned_text = process_chunks_with_retry(
        client=client,
        prompt_template=repair_prompt,
        text_data=raw_text,
        stage_name="STAGE 1A",
    )

    _log(f"STAGE 1A DONE in {time.time() - start_time_stage_1a:.2f}s")

    # =============================
    # STAGE 1B - OCR CONSISTENCY REVIEW
    # =============================

    consistency_repair_prompt = """YOU ARE A FINAL OCR CONSISTENCY REVIEWER FOR VIETNAMESE ADMINISTRATIVE DOCUMENTS.

You receive text that was already OCR-repaired once.
Your job is to find remaining OCR mistakes, strange characters, broken Vietnamese words, malformed legal headers, and inconsistent administrative document formatting.

CRITICAL RULES:
- Do NOT summarize.
- Do NOT paraphrase.
- Do NOT add new legal content.
- Do NOT remove meaningful legal content.
- Preserve document order and paragraph order.
- Preserve legal numbers, dates, document codes, article numbers, clause numbers.
- Only fix obvious OCR mistakes.
- If uncertain, keep the original text.

LINE BREAK REPAIR:
- Merge OCR-broken lines that belong to the same sentence or paragraph.
- Do not preserve PDF visual wrapping.
- Preserve paragraph breaks only for real structural boundaries.
- Enumerations like (i), (ii), (iii) inside one sentence must stay in the same logical paragraph.

YOU MUST SPECIFICALLY CHECK AND FIX:
- CÔNG HỘ XÃ HỘI -> CỘNG HÒA XÃ HỘI when used in national heading.
- CÔNG HỘ XÃ HỘI CHỦ NGHĨA VIỆT NAM -> CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM.
- đề bao gồm -> để bao gồm when context means purpose.
- dự luận -> dư luận when context means public opinion.
- RHO CHỦ NHIỆM -> PHÓ CHỦ NHIỆM when context is signature title.
- một đầu mỗi quản lý -> một đầu mối quản lý.
- CDS -> CĐS if the same document uses CĐS elsewhere.
- VPCP-CDS -> VPCP-CĐS if context is Vietnamese document code.
- Strange symbols: @, ””, ?, random Latin fragments, duplicated punctuation.
- So: -> Số: if followed by a legal document code.
- Naty -> Ngày if context clearly means a date line.
- thang -> tháng if used in date context.
- nam -> năm if used in date context.

OUTPUT:
- Plain cleaned Vietnamese text only.
- No Markdown.
- No explanations.
- No comments."""

    _log("STAGE 1B: OCR consistency repair start")
    start_time_stage_1b = time.time()

    cleaned_text = process_chunks_with_retry(
        client=client,
        prompt_template=consistency_repair_prompt,
        text_data=cleaned_text,
        stage_name="STAGE 1B",
    )

    cleaned_text = normalize_ocr_line_breaks(cleaned_text)

    _log(f"STAGE 1B DONE in {time.time() - start_time_stage_1b:.2f}s")
    _log(f"Cleaned text length: {len(cleaned_text)}")

    normalized_dir = Path("data/normalized_text")
    normalized_dir.mkdir(parents=True, exist_ok=True)

    normalized_path = normalized_dir / f"{doc_id}.txt"
    normalized_path.write_text(cleaned_text, encoding="utf-8")

    _log(f"Saved normalized text: {normalized_path}")

    # =============================
    # STAGE 2 - MARKDOWN WITH HEADER CONTEXT
    # =============================

    structure_prompt = """YOU ARE A STRICT LOSSLESS MARKDOWN STRUCTURING ENGINE FOR VIETNAMESE ADMINISTRATIVE DOCUMENTS.

CRITICAL RULES:
- Do NOT change, rewrite, summarize, or reformat content.
- Do NOT add ANY new characters not present in input, EXCEPT Markdown heading tags (#, ##, ###, ####).
- Use previous headers only to understand hierarchy.
- Do NOT repeat previous headers unless the current input contains that exact heading line.

ABSOLUTE FORBIDDEN:
- No emojis.
- No icons.
- No decorative symbols.
- No fancy bullets.
- No extra punctuation added for styling.
- No commentary text.
- No explanations.

MANDATORY MARKDOWN FORMATTING:
Analyze the document hierarchy and insert Markdown headings by adding '# ' at the beginning of relevant lines.

1. LEVEL 1 HEADINGS (#):
- Document titles/types: CÔNG ĐIỆN, QUYẾT ĐỊNH, CHỈ THỊ, NGHỊ QUYẾT, BÁO CÁO, CÔNG VĂN.
- Lines starting with PHẦN or CHƯƠNG.
- Lines containing the main subject after "V/v" if it represents the main document subject.

2. LEVEL 2 HEADINGS (##):
- Lines starting with MỤC or ĐIỀU.
- Lines starting with Roman numerals: I., II., III.
- Lines starting with "Kính gửi:".
- Lines starting with "Nơi nhận:".
- Lines starting with "Số:" if the line contains document number/date metadata.
- Lines introducing instruction body such as "Thủ tướng Chính phủ ... có ý kiến chỉ đạo như sau:".

3. LEVEL 3 HEADINGS (###):
- Lines starting with numbered major sections: 1., 2., 3.
- If a numbered section is a very long line containing body content, only the section heading/prefix should be treated as the heading when clear.

4. LEVEL 4 HEADINGS (####):
- Lines starting with lowercase letters: a), b), c), d).
- Lines starting with inline roman enumerations after they are separated: (i), (ii), (iii).

PRESERVE EXACTLY:
- Every original word.
- Line breaks.
- Punctuation.
- Legal numbers and dates.

OUTPUT RULE:
- Output must be pure Markdown text.
- Only add Markdown heading markers.
- Do not delete or modify actual content words."""

    _log("STAGE 2: Markdown conversion start")
    start_time_stage_2 = time.time()

    md_content = process_markdown_chunks_with_context(
        client=client,
        prompt_template=structure_prompt,
        text_data=cleaned_text,
        stage_name="STAGE 2",
    )

    # =============================
    # STAGE 2B - SPLIT INLINE ROMAN ENUMERATIONS
    # =============================

    md_content = split_inline_roman_headings(md_content)

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
            if_add_node_id=opt.if_add_node_id,
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