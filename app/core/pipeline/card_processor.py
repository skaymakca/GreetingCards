"""PDF/OCR processing utilities: scanning, conversion, and state loading.

Pure functions with no GUI dependencies — can be used from both the main window
and a CLI batch tool.
"""

import io
from pathlib import Path

from PIL import Image

from app.core.database import get_card_state
from app.models.card import CardResult, Confidence, PdfWorkerResult


def scan_for_pdfs(path: Path) -> list[Path]:
    """Recursively scan path for PDFs.

    Args:
        path: File or directory path

    Returns:
        List of PDF paths (absolute, resolved)
    """
    if path.is_file():
        if path.suffix.lower() == ".pdf":
            return [path.resolve()]
        return []

    # Recursive directory scan
    pdf_paths = [p.resolve() for p in path.rglob("*.[pP][dD][fF]")]
    return sorted(pdf_paths)


def worker_result_to_card(wr: PdfWorkerResult, card_id: int) -> CardResult:
    """Convert PdfWorkerResult from worker process to CardResult with assigned ID."""
    pdf_path = Path(wr.pdf_path)
    card = CardResult(
        id=card_id,
        file_paths=[pdf_path],
        primary_path=pdf_path,
        file_hash=wr.file_hash or "",
        family_name=wr.family_name,
        candidates=wr.candidates,
        remove_family=wr.remove_family,
        selected_candidate_id=wr.selected_candidate_id,
        method=wr.method,
    )

    try:
        card.confidence = Confidence(wr.confidence)
    except ValueError:
        card.confidence = Confidence.NONE

    # Deserialize images from bytes
    if wr.preview_image_bytes:
        card.preview_image = Image.open(io.BytesIO(wr.preview_image_bytes))

    if wr.page_images_bytes:
        card.page_images = [Image.open(io.BytesIO(img_bytes)) for img_bytes in wr.page_images_bytes]

    if wr.error:
        card.error = wr.error
        card.confidence = Confidence.NONE

    return card


def load_card_state_from_db(card: CardResult) -> None:
    """Load card state from database into a CardResult object.

    Reads the current card_state for the card's file_hash and updates
    the card's display fields (family_name, confidence, candidates, etc.).
    """
    if not card.file_hash:
        card.confidence = Confidence.NONE
        card.ai_analyzed = True
        return

    card_state = get_card_state(card.file_hash)
    if card_state:
        card.family_name = card_state.display_name
        try:
            card.confidence = Confidence(card_state.confidence)
        except ValueError:
            card.confidence = Confidence.NONE
        card.candidates = card_state.candidates
        card.remove_family = card_state.remove_family
        card.selected_candidate_id = card_state.selected_candidate_id
        card.method = card_state.method
        card.ai_analyzed = True
        # Only clear manual override if user hasn't manually edited
        if not card.manual_override or card.method != "manual":
            card.manual_override = ""
    else:
        # No DB state — reset to clean state
        card.family_name = ""
        card.confidence = Confidence.NONE
        card.method = "missing"
        card.candidates = []
        card.selected_candidate_id = None
        card.manual_override = ""
        card.ai_analyzed = True
