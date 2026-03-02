"""Application-wide processing constants."""

import multiprocessing
from datetime import datetime

PDF_DPI = 200
AI_CONCURRENCY = 3
OCR_WORKERS = multiprocessing.cpu_count()
RELOAD_COOLDOWN = 2.0  # seconds between auto-reloads


def default_year() -> str:
    """Return the default year for naming (previous calendar year)."""
    return str(datetime.now().year - 1)
