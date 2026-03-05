"""Generate diagnostic greeting card PDFs with fixed family name text.

Creates simple single-page PDFs with "The {NAME} Family" centered in
12pt Helvetica Bold on a white background. Pages are rasterized and
JPEG-compressed for realistic OCR testing.

Usage::

    uv run python -m scripts.generate_diagnostic_cards --names "Smith,O'Brien,Van Dyke"
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import fitz  # type: ignore[import-untyped]
from rich.console import Console

from scripts.helpers import script_output_dir

# Card dimensions: 5x7 inches = 360x504 points
CARD_W = 360
CARD_H = 504
FONT_NAME = "helv"
FONT_SIZE = 12
DPI = 200
JPEG_QUALITY = 75


def _create_diagnostic_pdf(name: str, output_path: Path) -> None:
    """Create a single diagnostic PDF for one family name.

    Pipeline: vector text → rasterize at DPI → JPEG compress → final PDF.
    """
    text = f"The {name} Family"

    # Step 1: Create a vector page with centered text
    vector_doc = fitz.open()
    page = vector_doc.new_page(width=CARD_W, height=CARD_H)

    # Calculate centered position
    text_width = fitz.get_text_length(text, fontname=FONT_NAME, fontsize=FONT_SIZE)
    x = (CARD_W - text_width) / 2
    y = CARD_H / 2

    # Insert text — fontname="helv" is Helvetica, with bold flag
    page.insert_text(
        fitz.Point(x, y),
        text,
        fontname=FONT_NAME,
        fontsize=FONT_SIZE,
        color=(0, 0, 0),
    )

    # Step 2: Rasterize to pixmap
    pix = page.get_pixmap(dpi=DPI)
    vector_doc.close()

    # Step 3: JPEG compress
    jpeg_data = pix.tobytes(output="jpeg", jpg_quality=JPEG_QUALITY)

    # Step 4: Create final PDF from the JPEG image
    final_doc = fitz.open()
    final_page = final_doc.new_page(width=CARD_W, height=CARD_H)
    final_page.insert_image(final_page.rect, stream=jpeg_data)
    final_doc.save(str(output_path), garbage=3)
    final_doc.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="generate_diagnostic_cards",
        description="Generate diagnostic greeting card PDFs with fixed family name text.",
    )
    parser.add_argument(
        "--names",
        type=str,
        required=True,
        metavar="LIST",
        help='Comma-separated family names (e.g. "Smith,O\'Brien,Van Dyke")',
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Don't open output folder when done",
    )
    args = parser.parse_args()

    names = [n.strip() for n in args.names.split(",") if n.strip()]
    if not names:
        print("Error: no valid names provided.")
        sys.exit(1)

    console = Console(highlight=False)
    console.print(f"Generating {len(names)} diagnostic card(s)\n")

    # noinspection PyTypeChecker
    with script_output_dir("diagnostic_cards") as output_dir:
        for i, name in enumerate(names, 1):
            filename = f"The {name} Family.pdf"
            output_path = output_dir / filename
            _create_diagnostic_pdf(name, output_path)
            size_kb = output_path.stat().st_size / 1024
            console.print(f"  [{i}/{len(names)}] {filename} ({size_kb:.0f} KB)")

        console.print(f"\n[bold green]Done![/bold green] {len(names)} cards in {output_dir}")

        if not args.no_open:
            try:  # noqa: SIM105
                subprocess.run(["open", str(output_dir)], check=False)
            except FileNotFoundError:
                pass
