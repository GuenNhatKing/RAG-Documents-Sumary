import io
import os
import re
import sys
import time
import numpy as np
from PIL import Image, ImageDraw

from .module.ocr import OCR as _OCR
from .module import LayoutRecognizer, TableStructureRecognizer

# Singleton instances
_ocr_instance = None
_layout_instance = None
_tsr_instance = None

def _get_ocr():
    global _ocr_instance
    if _ocr_instance is None:
        _ocr_instance = _OCR()
    return _ocr_instance

def _get_layout():
    global _layout_instance
    if _layout_instance is None:
        _layout_instance = LayoutRecognizer("layout")
    return _layout_instance

def _get_tsr():
    global _tsr_instance
    if _tsr_instance is None:
        _tsr_instance = TableStructureRecognizer()
    return _tsr_instance


def extract_table_markdown(img, table_region, ocr):
    if "bbox" in table_region:
        x0, y0, x1, y1 = map(int, table_region["bbox"])
    else:
        x0, y0, x1, y1 = map(int, [table_region["x0"], table_region["top"], table_region["x1"], table_region["bottom"]])
    table_img = img.crop((x0, y0, x1, y1))
    tb_cpns = _get_tsr()([table_img])[0]
    boxes = ocr(np.array(table_img))
    boxes = LayoutRecognizer.sort_Y_firstly(
        [{"x0": b[0][0], "x1": b[1][0],
          "top": b[0][1], "text": t[0],
          "bottom": b[-1][1],
          "layout_type": "table",
          "page_number": 0} for b, t in boxes if b[0][0] <= b[1][0] and b[0][1] <= b[-1][1]],
        np.mean([b[-1][1] - b[0][1] for b, _ in boxes]) / 3
    )

    def gather(kwd, fzy=10, ption=0.6):
        nonlocal boxes
        eles = LayoutRecognizer.sort_Y_firstly(
            [r for r in tb_cpns if re.match(kwd, r["label"])], fzy)
        eles = LayoutRecognizer.layouts_cleanup(boxes, eles, 5, ption)
        return LayoutRecognizer.sort_Y_firstly(eles, 0)

    headers = gather(r".*header$")
    rows = gather(r".* (row|header)")
    spans = gather(r".*spanning")
    clmns = sorted([r for r in tb_cpns if re.match(
        r"table column$", r["label"])], key=lambda x: x["x0"])
    clmns = LayoutRecognizer.layouts_cleanup(boxes, clmns, 5, 0.5)

    for b in boxes:
        ii = LayoutRecognizer.find_overlapped_with_threashold(b, rows, thr=0.3)
        if ii is not None:
            b["R"] = ii
            b["R_top"] = rows[ii]["top"]
            b["R_bott"] = rows[ii]["bottom"]

        ii = LayoutRecognizer.find_overlapped_with_threashold(b, headers, thr=0.3)
        if ii is not None:
            b["H_top"] = headers[ii]["top"]
            b["H_bott"] = headers[ii]["bottom"]
            b["H_left"] = headers[ii]["x0"]
            b["H_right"] = headers[ii]["x1"]
            b["H"] = ii

        ii = LayoutRecognizer.find_horizontally_tightest_fit(b, clmns)
        if ii is not None:
            b["C"] = ii
            b["C_left"] = clmns[ii]["x0"]
            b["C_right"] = clmns[ii]["x1"]

        ii = LayoutRecognizer.find_overlapped_with_threashold(b, spans, thr=0.3)
        if ii is not None:
            b["H_top"] = spans[ii]["top"]
            b["H_bott"] = spans[ii]["bottom"]
            b["H_left"] = spans[ii]["x0"]
            b["H_right"] = spans[ii]["x1"]
            b["SP"] = ii

    markdown = TableStructureRecognizer.construct_table(boxes, markdown=True)
    return markdown


def image_to_markdown(pil_image, threshold=0.5):
    ocr = _get_ocr()
    layout_recognizer = _get_layout()

    layouts = layout_recognizer.forward([pil_image], thr=threshold)[0]

    mask = Image.new("1", pil_image.size, 0)
    draw = ImageDraw.Draw(mask)
    for region in layouts:
        if "bbox" in region:
            x0, y0, x1, y1 = map(int, region["bbox"])
        else:
            x0, y0, x1, y1 = map(int, [region.get("x0", 0), region.get("top", 0), region.get("x1", 0), region.get("bottom", 0)])
        draw.rectangle([x0, y0, x1, y1], fill=1)

    region_and_pos = []

    for region in layouts:
        label = region.get("type", "").lower()
        score = region.get("score", 1.0)
        bbox = region.get("bbox", [region.get("x0", 0), region.get("top", 0), region.get("x1", 0), region.get("bottom", 0)])
        y_pos = bbox[1]
        if label in ["table"] and score >= threshold:
            markdown = extract_table_markdown(pil_image, region, ocr)
            region_and_pos.append((y_pos, markdown))

    inv_mask = mask.point(lambda p: 1 - p)
    if inv_mask.getbbox():
        x0, y0, x1, y1 = inv_mask.getbbox()
        region_img = pil_image.crop((x0, y0, x1, y1))
        ocr_results = ocr(np.array(region_img))
        text = "\n".join([t[0] for _, t in ocr_results if t and t[0]])
        region_and_pos.append((y0, text))
    else:
        ocr_results = ocr(np.array(pil_image))
        text = "\n".join([t[0] for _, t in ocr_results if t and t[0]])
        region_and_pos.append((0, text))

    region_and_pos.sort(key=lambda x: x[0])
    return "\n\n".join([item[1] for item in region_and_pos])


def pdf_to_markdown(pdf_path, dpi=300, threshold=0.5):
    try:
        import pdfplumber
    except ImportError:
        raise ImportError("pdfplumber is required for PDF processing")

    _get_ocr()  # ensure loaded once
    _get_layout()
    results = []

    pdf = pdfplumber.open(pdf_path)
    for page_num, page in enumerate(pdf.pages):
        img = page.to_image(resolution=72 * dpi // 72).annotated
        md = image_to_markdown(img, threshold)
        results.append({"page": page_num + 1, "markdown": md})
    pdf.close()

    return results


def image_file_to_markdown(image_path, threshold=0.5):
    pil_image = Image.open(image_path).convert("RGB")
    md = image_to_markdown(pil_image, threshold=threshold)
    return md
