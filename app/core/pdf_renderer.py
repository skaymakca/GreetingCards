import fitz  # PyMuPDF
from pathlib import Path
from PIL import Image
import io


def render_pdf_page(pdf_path: Path, page_num: int = 0, dpi: int = 200) -> Image.Image:
    """Render a single PDF page to a PIL Image."""
    doc = fitz.open(str(pdf_path))
    try:
        page = doc[page_num]
        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        img_data = pix.tobytes("png")
        return Image.open(io.BytesIO(img_data))
    finally:
        doc.close()


def render_all_pages(pdf_path: Path, dpi: int = 200) -> list[Image.Image]:
    """Render all pages of a PDF to PIL Images."""
    doc = fitz.open(str(pdf_path))
    images = []
    try:
        for page in doc:
            zoom = dpi / 72
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
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
