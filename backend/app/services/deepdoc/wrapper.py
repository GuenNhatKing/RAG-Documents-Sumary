import numpy as np
from PIL import Image
from .module.ocr import OCR as DeepdocOCR
from .pipeline import image_to_markdown as _image_to_markdown

_ocr_instance = None

def get_ocr_instance():
    global _ocr_instance
    if _ocr_instance is None:
        _ocr_instance = DeepdocOCR()
    return _ocr_instance

def extract_text_from_image(pil_image: Image.Image) -> str:
    ocr = get_ocr_instance()
    img_array = np.array(pil_image.convert("RGB"))
    results = ocr(img_array)
    texts = [text for _, (text, score) in results]
    return "\n".join(texts)

def extract_markdown_from_image(pil_image: Image.Image, threshold=0.5) -> str:
    return _image_to_markdown(pil_image, threshold=threshold)
