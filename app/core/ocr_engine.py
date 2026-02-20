import shutil

import pytesseract
from PIL import Image, ImageFilter, ImageOps

from app.core.paths import is_bundled

# macOS .app bundles have a minimal PATH that excludes Homebrew.
# Locate the tesseract binary at import time.
if is_bundled() and not shutil.which("tesseract"):
    _SEARCH_PATHS = [
        "/opt/homebrew/bin/tesseract",   # Apple Silicon Homebrew
        "/usr/local/bin/tesseract",      # Intel Homebrew / manual install
    ]
    import os as _os
    for _p in _SEARCH_PATHS:
        if _os.path.isfile(_p) and _os.access(_p, _os.X_OK):
            pytesseract.pytesseract.tesseract_cmd = _p
            break

_tesseract_available: bool | None = None  # None = not yet checked


def is_tesseract_available() -> bool:
    """Check if Tesseract is installed. Result is cached after first call."""
    global _tesseract_available
    if _tesseract_available is not None:
        return _tesseract_available

    cmd = pytesseract.pytesseract.tesseract_cmd or "tesseract"
    if shutil.which(cmd):
        _tesseract_available = True
        return True

    try:
        pytesseract.get_tesseract_version()
        _tesseract_available = True
    except pytesseract.TesseractNotFoundError:
        _tesseract_available = False

    return _tesseract_available


def preprocess_image(image: Image.Image) -> Image.Image:
    """Preprocess image for better OCR results."""
    img = image.copy()
    # Convert to grayscale
    img = ImageOps.grayscale(img)
    # Increase contrast
    img = ImageOps.autocontrast(img, cutoff=2)
    # Slight sharpen to help with text edges
    img = img.filter(ImageFilter.SHARPEN)
    return img


def extract_text(image: Image.Image) -> str:
    """Run OCR on an image and return extracted text."""
    if not is_tesseract_available():
        return ""
    processed = preprocess_image(image)
    text = pytesseract.image_to_string(processed, config="--psm 6")
    return text.strip()


def extract_text_all_pages(images: list[Image.Image]) -> str:
    """Run OCR on multiple page images and combine results."""
    if not is_tesseract_available():
        return ""
    texts = []
    for img in images:
        text = extract_text(img)
        if text:
            texts.append(text)
    return "\n\n".join(texts)
