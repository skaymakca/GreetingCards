"""PDF processing worker for multiprocessing.

This module contains the worker function that runs in subprocess workers
via ProcessPoolExecutor. It performs PDF rendering, OCR, database operations,
and image serialization — all core logic with zero GUI dependencies.
"""

import io
from pathlib import Path
from typing import Any

from app.core.constants import PDF_DPI
from app.core.database import (
    compute_file_hash, get_card_state, save_raw_ocr,
    reprocess_candidates_from_raw,
)
from app.core.ocr_engine import extract_text_all_pages
from app.core.pdf_renderer import render_all_pages


def process_pdf_worker(pdf_path_str: str) -> dict[str, Any]:
    """Worker function to process a single PDF in a separate process.

    Returns dict of results (serializable for multiprocessing).
    """
    pdf_path = Path(pdf_path_str)
    result = {
        'pdf_path': pdf_path_str,
        'file_hash': None,
        'family_name': '',
        'confidence': 'none',
        'method': 'missing',
        'alternates': [],
        'candidates': [],
        'remove_family': False,
        'selected_candidate_id': None,
        'ocr_text': '',
        'error': None,
        # Store images as PNG bytes for pickling
        'preview_image_bytes': None,
        'page_images_bytes': [],
    }

    try:
        # Compute file hash
        file_hash = compute_file_hash(pdf_path)
        result['file_hash'] = file_hash

        # Check DB cache first
        card_state = get_card_state(file_hash)

        # Always render preview (needed for AI later)
        images = render_all_pages(pdf_path, dpi=PDF_DPI)
        if images:
            # Serialize images to bytes
            preview_buf = io.BytesIO()
            images[0].save(preview_buf, format='PNG')
            result['preview_image_bytes'] = preview_buf.getvalue()

            for img in images:
                buf = io.BytesIO()
                img.save(buf, format='PNG')
                result['page_images_bytes'].append(buf.getvalue())

        if card_state:
            # Card exists - reprocess candidates from raw data with current cleaning logic
            reprocess_candidates_from_raw(file_hash)
        else:
            # New file - run OCR and save raw data
            if images:
                ocr_text = extract_text_all_pages(images)
                result['ocr_text'] = ocr_text
                save_raw_ocr(file_hash, ocr_text)
                reprocess_candidates_from_raw(file_hash)

        # Load state after processing/reprocessing
        card_state = get_card_state(file_hash)
        if card_state:
            result['family_name'] = card_state.display_name
            result['confidence'] = card_state.confidence
            result['alternates'] = [c.family_name for c in card_state.candidates]
            result['candidates'] = card_state.candidates
            result['remove_family'] = card_state.remove_family
            result['selected_candidate_id'] = card_state.selected_candidate_id
            result['method'] = card_state.method

    except Exception as e:
        result['error'] = str(e)

    return result
