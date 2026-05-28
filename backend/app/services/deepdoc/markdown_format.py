import re


def _is_all_upper(line: str) -> bool:
    stripped = line.strip()
    if len(stripped) < 3:
        return False
    letters = [c for c in stripped if c.isalpha()]
    return len(letters) > 3 and all(c.isupper() for c in letters)


def _looks_like_heading(line: str) -> int | None:
    stripped = line.strip()
    if not stripped:
        return None

    # Already has heading marker
    m = re.match(r'^(#{1,6})\s', stripped)
    if m:
        return len(m.group(1))

    # Vietnamese admin doc patterns
    if re.match(r'^(Số|Số|Number|Nos?)[\s.:]', stripped):
        return 1
    if re.match(r'^[A-ZÀ-Ỹ\s]{10,}$', stripped) and _is_all_upper(stripped):
        return 1
    if re.match(r'^[A-ZÀ-Ỹ][A-Za-zÀ-ỹ\s,;:]+[A-ZÀ-Ỹ]{2,}', stripped):
        return 2
    if re.match(r'^(Hà Nội|TP\.|Thành phố).*(ngày|date)', stripped):
        return 1
    if re.match(r'^CỘNG HÒA|^ĐỘC LẬP|^CỘNG HOÀ', stripped):
        return 0
    if re.match(r'^[-—]{3,}', stripped):
        return 0
    if re.match(r'^[Nn]ơi nhận:', stripped):
        return 2
    if re.match(r'^[Kk]ính gửi:', stripped):
        return 2
    if re.match(r'^[Tt]hủ tướng|^[Tt]hủ tướng chính phủ', stripped):
        return 2
    if re.match(r'^(CÔNG ĐIỆN|Công điện|CHỈ THỊ|QUYẾT ĐỊNH|THÔNG BÁO|THÔNG TƯ|NGHỊ ĐỊNH|NGHỊ QUYẾT|CÔNG VĂN|BÁO CÁO|TỜ TRÌNH)', stripped):
        return 1

    # Numbered headings: 1., 2., I., II., A., B., etc.
    if re.match(r'^[1-9]\d*\.\s', stripped):
        return 3
    if re.match(r'^[IVXLCDM]+\.\s', stripped):
        return 2
    if re.match(r'^[A-Z]\.\s', stripped):
        return 3
    if re.match(r'^[a-z]\)\s', stripped):
        return 4
    if re.match(r'^[a-z]\.\s', stripped):
        return 4
    if re.match(r'^[ivxlcdm]+\)\s', stripped):
        return 5
    if re.match(r'^[ivxlcdm]+\.\s', stripped):
        return 5
    if re.match(r'^[-–]\s', stripped):
        return 0

    return None


def format_markdown(text: str) -> str:
    lines = text.split("\n")
    result = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            result.append(line)
            continue
        level = _looks_like_heading(line)
        if level is not None and level > 0:
            result.append(f"{'#' * level} {stripped}")
        elif level == 0:
            result.append(stripped)
        else:
            result.append(line)
    return "\n".join(result)
