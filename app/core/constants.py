"""Processing constants shared between core and GUI layers."""

import multiprocessing

PDF_DPI = 200
AI_CONCURRENCY = 3
OCR_WORKERS = multiprocessing.cpu_count()
