import re


def _is_heading_line(line: str) -> int | None:
    stripped = line.strip()
    if not stripped:
        return None

    # Already has heading marker
    m = re.match(r'^(#{1,6})\s', stripped)
    if m:
        return len(m.group(1))

    # Divider
    if re.match(r'^[-—]{3,}$', stripped):
        return None

    # Document type keywords (H1) — ONLY these specific ones
    if re.match(
        r'^(CÔNG ĐIỆN|CHỈ THỊ|QUYẾT ĐỊNH|THÔNG BÁO|THÔNG TƯ|'
        r'NGHỊ ĐỊNH|NGHỊ QUYẾT|CÔNG VĂN|BÁO CÁO|TỜ TRÌNH|'
        r'THÔNG CÁO|KẾ HOẠCH|PHÁP LỆNH|LUẬT|HIẾN PHÁP|'
        r'CHƯƠNG TRÌNH|PHƯƠNG ÁN|ĐỀ ÁN)',
        stripped,
    ):
        return 1

    # "Về ..." subject line following a doc type → NOT a heading, handled via merging
    # (not detected here, will be merged with previous doc type in paragraph grouping)

    # Major administrative sections: PHẦN, CHƯƠNG, MỤC, TIỂU MỤC (H2)
    if re.match(r'^(PHẦN|CHƯƠNG|MỤC|TIỂU\s+MỤC)\s+([IVXLCDM\d]+|THỨ\s+\w+)', stripped, re.I):
        return 2

    # Articles: Điều 1, Điều 2... (H3)
    if re.match(r'^Điều\s+\d+', stripped, re.I):
        return 3

    # "Nhằm..." section intro (H2)
    if re.match(r'^Nhằm\s', stripped):
        return 2

    # Section labels (H2)
    if re.match(r'^[Nn]ơi nhận:', stripped):
        return 2
    if re.match(r'^[Kk]ính gửi:', stripped):
        return 2

    # Numbered headings: 1., 2., ... (H3) — with or without space after dot
    if re.match(r'^[1-9]\d*\.', stripped):
        return 3
    # Roman numeral: I., II. (H2)
    if re.match(r'^[IVXLCDM]+\.\s*', stripped):
        return 2
    # Sub-numbered: a), b), c), đ) (H4) — both lowercase and uppercase
    if re.match(r'^[a-zđ]\)\s*', stripped):
        return 4
    if re.match(r'^[A-Z]\)\s*', stripped):
        return 4
    # Roman numeral lower: i), ii) (H5)
    if re.match(r'^[ivxlcdm]+\)\s*', stripped):
        return 5

    return None


def _starts_new_para(line: str, prev_line: str | None) -> bool:
    if prev_line is None:
        return False

    stripped = line.strip()
    prev_stripped = prev_line.strip()
    if not stripped or not prev_stripped:
        return True

    # Line starts with dash/bullet → break (list item)
    if re.match(r'^[-–•*]\s', stripped):
        return True

    # Current line is a heading → break
    if _is_heading_line(line) is not None:
        return True

    # Starts lowercase → continuation
    if stripped[0].islower() or (stripped.startswith("đ") and len(stripped) > 1 and stripped[1].islower()):
        return False

    # Previous line ends with colon → break (label like "Nơi nhận:")
    if re.search(r':$', prev_stripped):
        return True

    # Previous doesn't end with sentence punctuation → continuation (text wrap)
    if not re.search(r'[.!?]$', prev_stripped):
        return False

    # Starts with Vietnamese sentence continuers → continuation
    _continuers = {
        "tuy nhiên", "do đó", "vì vậy", "vì thế", "ngoài ra",
        "bên cạnh đó", "đồng thời", "trong đó", "trong khi",
        "mặt khác", "trên cơ sở", "theo đó", "như vậy", "cụ thể",
        "với tinh thần", "trên tinh thần", "về việc", "về phía",
        "đối với", "nếu", "mặc dù", "tuy", "song",
    }
    lower = stripped.lower()
    for w in _continuers:
        if lower.startswith(w):
            after = lower[len(w):]
            if not after or not after[0].isalpha():
                return False

    # Previous is a heading → break
    if _is_heading_line(prev_line) is not None:
        return True

    # Starts uppercase and is reasonably long → new sentence in same paragraph
    if len(stripped) > 40:
        return False

    return True


_ARTIFACT_PATTERNS = [
    re.compile(r'^#\s*Trang\s+\d+', re.IGNORECASE),
    re.compile(r'^Trang\s+\d+', re.IGNORECASE),
    re.compile(r'^#\s*TDT\s*$', re.IGNORECASE),
    re.compile(r'^TDT\s*$', re.IGNORECASE),
    re.compile(r'^\d+$'), # Standalone page numbers
]


def _is_artifact(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    for pat in _ARTIFACT_PATTERNS:
        if pat.match(stripped):
            return True
    return False


def _split_midline_headings(text: str) -> str:
    # Insert \n before heading patterns that appear mid-line.
    # Lookahead is used so trailing whitespace/formatting is preserved.
    # 1. Numbered: "ra 4.Yêu" or "ra 4. Yêu" → "ra\n4.Yêu"
    text = re.sub(r'\s+(\d+\.)(?=\s*[A-ZÀ-Ỹ])', r'\n\1', text)
    # 2. Lowercase letter+paren: "quy a) Bộ" → "quy\na) Bộ"
    text = re.sub(r'\s+([a-zđ]\))(?=\s+[A-ZÀ-Ỹ])', r'\n\1', text)
    # 3. Uppercase letter+paren: "định C) Đề" → "định\nC) Đề"
    text = re.sub(r'\s+([A-Z]\))(?=\s+[A-ZÀ-Ỹ])', r'\n\1', text)
    return text


def format_markdown(text: str) -> str:
    text = _split_midline_headings(text)
    raw_lines = text.split("\n")

    # Step 1: Filter artifacts and group into paragraphs
    paragraphs: list[list[str]] = []
    current: list[str] = []

    for line in raw_lines:
        stripped = line.strip()
        if not stripped:
            if current:
                paragraphs.append(current)
                current = []
            continue

        if _is_artifact(stripped):
            if current:
                paragraphs.append(current)
                current = []
            continue

        prev = current[-1] if current else None
        if _starts_new_para(stripped, prev):
            if current:
                paragraphs.append(current)
            current = [stripped]
        else:
            current.append(stripped)

    if current:
        paragraphs.append(current)

    # Step 2: Render each paragraph
    result: list[str] = []
    for para in paragraphs:
        first_heading = _is_heading_line(para[0])
        if first_heading:
            result.append(f"{'#' * first_heading} {' '.join(para)}")
        else:
            result.append(" ".join(para))

    return "\n\n".join(result)
