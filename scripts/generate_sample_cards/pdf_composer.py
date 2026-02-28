"""PDF composition from full-card images."""

from __future__ import annotations

from pathlib import Path

import fitz  # type: ignore[import-untyped]

# Card dimensions: 5 x 7 inches = 360 x 504 points
CARD_W = 360
CARD_H = 504


def compose_pdf_from_images(
    image_paths: list[Path],
    output_path: Path,
    *,
    jpeg_quality: int = 75,
) -> None:
    """Build a PDF where each image is a full-bleed page.

    Pages are sized to 5x7 inches (360x504 points) like real greeting cards.

    Args:
        image_paths: Source image files (one per page).
        output_path: Destination PDF file.
        jpeg_quality: JPEG quality level (1-100). Default 75 gives ~12x
            compression vs lossless PNG with no visible degradation.
            Set to -1 to embed images as lossless PNG with deflate
            compression (much larger files).
    """
    lossless = jpeg_quality < 0
    doc = fitz.open()
    for img_path in image_paths:
        if lossless:
            stream = Path(img_path).read_bytes()
        else:
            pix = fitz.Pixmap(str(img_path))
            if pix.alpha:
                pix = fitz.Pixmap(fitz.csRGB, pix)  # drop alpha for JPEG
            stream = pix.tobytes(output="jpeg", jpg_quality=jpeg_quality)
        page = doc.new_page(width=CARD_W, height=CARD_H)
        page.insert_image(page.rect, stream=stream)
    doc.save(str(output_path), deflate=lossless, garbage=3)
    doc.close()
