"""PDF processing orchestration service.

Manages the ProcessPoolExecutor lifecycle and worker dispatch.  Has zero
wxPython dependency — the caller wraps callbacks with ``wx.CallAfter``.
"""

from __future__ import annotations

import logging
import multiprocessing
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from app.core.card_store import CardStore
from app.core.constants import OCR_WORKERS
from app.core.pipeline.pdf_worker import process_pdf_worker

logger = logging.getLogger(__name__)


class ProcessingService:
    """Process PDF files via multiprocessing and feed results into CardStore."""

    def __init__(self, store: CardStore) -> None:
        self._store = store

    def process_files(
        self,
        files: list[Path],
        on_progress: Callable[[int, int, str], None] | None = None,
        on_complete: Callable[[], None] | None = None,
    ) -> None:
        """Process *files* using a ``ProcessPoolExecutor``.

        Runs synchronously in the calling thread (caller is responsible for
        launching a background thread).  Calls ``on_progress(completed, total,
        filename)`` after each file and ``on_complete()`` when done.
        """
        # Set spawn method for PyInstaller
        try:
            multiprocessing.set_start_method("spawn", force=True)
        except RuntimeError as exc:
            if "context has already been set" not in str(exc):
                raise

        total = len(files)
        pdf_paths_str = [str(p) for p in files]
        completed = 0

        with ProcessPoolExecutor(max_workers=min(total, OCR_WORKERS)) as executor:
            futures = {executor.submit(process_pdf_worker, path_str): path_str for path_str in pdf_paths_str}
            for future in as_completed(futures):
                try:
                    worker_result = future.result()
                except Exception:
                    path_str = futures[future]
                    logger.exception("Worker failed for %s", path_str)
                    completed += 1
                    if on_progress:
                        on_progress(completed, total, Path(path_str).name)
                    continue

                pdf_path = Path(worker_result.pdf_path)
                card, _ = self._store.add_or_update(worker_result, pdf_path)

                completed += 1
                if on_progress:
                    on_progress(completed, total, card.filename)

        if on_complete:
            on_complete()
