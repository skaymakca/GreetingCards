import io
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image, ImageChops, ImageFilter


def _capped_zoom(page: fitz.Page, dpi: int) -> fitz.Matrix:
    """Compute a zoom matrix targeting the given DPI, capped at native image resolution."""
    target_zoom = dpi / 72
    image_infos = page.get_image_info()
    if image_infos:
        max_native_dpi = max(max(info.get("xres", 72), info.get("yres", 72)) for info in image_infos)
        target_zoom = min(target_zoom, max_native_dpi / 72)
    return fitz.Matrix(target_zoom, target_zoom)


def autocrop_whitespace(image: Image.Image, threshold: int = 245, padding: int = 10) -> Image.Image:
    """Crop near-white borders from a scanned page image.

    Applies a Gaussian blur before thresholding to ignore scanner speckle
    noise that would otherwise prevent effective cropping.

    Args:
        threshold: Grayscale value (0-255) above which pixels are considered white.
            245 catches near-white scanner backgrounds without clipping cream paper.
        padding: Pixels to keep around the detected content to avoid clipping edges.
    """
    gray = image.convert("L")
    blurred = gray.filter(ImageFilter.GaussianBlur(radius=5))
    bg = Image.new("L", blurred.size, threshold)
    diff = ImageChops.subtract(bg, blurred)
    bbox = diff.getbbox()
    if not bbox:
        return image
    left = max(0, bbox[0] - padding)
    top = max(0, bbox[1] - padding)
    right = min(image.width, bbox[2] + padding)
    bottom = min(image.height, bbox[3] + padding)
    return image.crop((left, top, right, bottom))


def render_pdf_page(pdf_path: Path, page_num: int = 0, dpi: int = 200) -> Image.Image:
    """Render a single PDF page to a PIL Image (capped at native resolution)."""
    doc = fitz.open(str(pdf_path))
    try:
        page = doc[page_num]
        pix = page.get_pixmap(matrix=_capped_zoom(page, dpi))
        img_data = pix.tobytes("png")
        return autocrop_whitespace(Image.open(io.BytesIO(img_data)))
    finally:
        doc.close()


def render_all_pages(pdf_path: Path, dpi: int = 200) -> list[Image.Image]:
    """Render all pages of a PDF to PIL Images (capped at native resolution)."""
    doc = fitz.open(str(pdf_path))
    images = []
    try:
        for page in doc:
            pix = page.get_pixmap(matrix=_capped_zoom(page, dpi))
            img_data = pix.tobytes("png")
            images.append(autocrop_whitespace(Image.open(io.BytesIO(img_data))))
    finally:
        doc.close()
    return images


def get_page_count(pdf_path: Path) -> int:
    """Return the number of pages in a PDF."""
    doc = fitz.open(str(pdf_path))
    try:
        return len(doc)
    finally:
        doc.close()
