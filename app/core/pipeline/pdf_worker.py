"""PDF processing worker for multiprocessing.

This module contains the worker function that runs in subprocess workers
via ProcessPoolExecutor. It performs PDF rendering, OCR, database operations,
and image serialization — all core logic with zero GUI dependencies.
"""

import io
import logging
from pathlib import Path

from app.core.constants import PDF_DPI
from app.core.database import (
    compute_file_hash,
    get_card_state,
    reprocess_candidates_from_raw,
    save_raw_ocr,
)
from app.core.pipeline.ocr_engine import extract_text_all_pages
from app.core.pipeline.pdf_renderer import render_all_pages
from app.models.card import PdfWorkerResult


def process_pdf_worker(pdf_path_str: str) -> PdfWorkerResult:
    """Worker function to process a single PDF in a separate process.

    Returns a PdfWorkerResult (pickled across process boundaries).
    """
    pdf_path = Path(pdf_path_str)
    result = PdfWorkerResult(pdf_path=pdf_path_str)

    try:
        # Compute file hash
        file_hash = compute_file_hash(pdf_path)
        result.file_hash = file_hash

        # Check DB cache first
        card_state = get_card_state(file_hash)

        # Always render preview (needed for AI later)
        images = render_all_pages(pdf_path, dpi=PDF_DPI)
        if images:
            # Serialize images to bytes
            preview_buf = io.BytesIO()
            images[0].save(preview_buf, format="PNG")
            result.preview_image_bytes = preview_buf.getvalue()

            for img in images:
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                result.page_images_bytes.append(buf.getvalue())

        # New file: run OCR and save raw data
        if not card_state and images:
            ocr_text = extract_text_all_pages(images)
            save_raw_ocr(file_hash, ocr_text)

        # (Re)process candidates from raw data with current cleaning logic
        reprocess_candidates_from_raw(file_hash)

        # Load state after processing
        card_state = get_card_state(file_hash)
        if card_state:
            result.family_name = card_state.display_name
            result.confidence = card_state.confidence
            result.candidates = card_state.candidates
            result.remove_family = card_state.remove_family
            result.selected_candidate_id = card_state.selected_candidate_id
            result.method = card_state.method

    except Exception as e:
        logging.getLogger(__name__).exception("Error processing PDF %s", pdf_path)
        # TODO: Wrap in structured error type once PdfWorkerResult carries
        # typed errors across the pickle boundary.
        result.error = str(e)

    return result
