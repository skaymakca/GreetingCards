import fitz  # PyMuPDF
from pathlib import Path
from PIL import Image
import io


def _capped_zoom(page, dpi: int) -> fitz.Matrix:
    """Compute a zoom matrix targeting the given DPI, capped at native image resolution."""
    target_zoom = dpi / 72
    image_infos = page.get_image_info()
    if image_infos:
        max_native_dpi = max(
            max(info.get("xres", 72), info.get("yres", 72))
            for info in image_infos
        )
        target_zoom = min(target_zoom, max_native_dpi / 72)
    return fitz.Matrix(target_zoom, target_zoom)


def render_pdf_page(pdf_path: Path, page_num: int = 0, dpi: int = 600) -> Image.Image:
    """Render a single PDF page to a PIL Image (capped at native resolution)."""
    doc = fitz.open(str(pdf_path))
    try:
        page = doc[page_num]
        pix = page.get_pixmap(matrix=_capped_zoom(page, dpi))
        img_data = pix.tobytes("png")
        return Image.open(io.BytesIO(img_data))
    finally:
        doc.close()


def render_all_pages(pdf_path: Path, dpi: int = 600) -> list[Image.Image]:
    """Render all pages of a PDF to PIL Images (capped at native resolution)."""
    doc = fitz.open(str(pdf_path))
    images = []
    try:
        for page in doc:
            pix = page.get_pixmap(matrix=_capped_zoom(page, dpi))
            img_data = pix.tobytes("png")
            images.append(Image.open(io.BytesIO(img_data)))
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
