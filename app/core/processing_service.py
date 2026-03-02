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
from app.core.pipeline.card_processor import scan_for_pdfs
from app.core.pipeline.pdf_worker import process_pdf_worker

logger = logging.getLogger(__name__)


class ProcessingService:
    """Process PDF files via multiprocessing and feed results into CardStore."""

    def __init__(self, store: CardStore) -> None:
        self._store = store

    @staticmethod
    def scan_for_pdfs(path: Path) -> list[Path]:
        """Recursively scan path for PDFs.

        Wraps ``scan_for_pdfs()`` so GUI callers don't import core
        pipeline internals directly.
        """
        return scan_for_pdfs(path)

    def ingest_paths(self, paths: list[Path]) -> tuple[list[Path], int]:
        """Scan paths for PDFs and register new ones with the store.

        Args:
            paths: File or folder paths to scan.

        Returns:
            (new_pdfs, skipped_count) — new PDF paths and count of already-loaded ones.
        """
        all_pdfs: list[Path] = []
        for path in paths:
            all_pdfs.extend(scan_for_pdfs(path))
        new_pdfs, skipped = self._store.filter_and_register(all_pdfs)
        return new_pdfs, len(skipped)

    def compute_reload(self, *, mtime_only: bool = False) -> tuple[list[Path], list[Path]]:
        """Compute deleted and modified paths, then register modified for reprocessing.

        Args:
            mtime_only: When True, use mtime as a fast pre-filter.

        Returns:
            (deleted_paths, needs_processing) — paths removed and paths needing reprocessing.
        """
        deleted, modified = self._store.compute_reload_diff(mtime_only=mtime_only)
        if modified:
            self._store.register_new_pdfs(modified)
        return deleted, modified

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
