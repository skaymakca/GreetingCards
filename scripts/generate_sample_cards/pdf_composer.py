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
) -> None:
    """Build a PDF where each image is a full-bleed page.

    Pages are sized to 5x7 inches (360x504 points) like real greeting cards.
    """
    doc = fitz.open()
    for img_path in image_paths:
        page = doc.new_page(width=CARD_W, height=CARD_H)
        page.insert_image(page.rect, filename=str(img_path))
    doc.save(str(output_path), deflate=True, garbage=3)
    doc.close()
