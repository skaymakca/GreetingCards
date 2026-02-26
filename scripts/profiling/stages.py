"""Per-stage profiling functions for the PDF processing pipeline."""

from __future__ import annotations

import asyncio
import multiprocessing
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image
from pyinstrument import Profiler
from rich.progress import Progress

from app.core.constants import AI_CONCURRENCY, PDF_DPI


@dataclass
class StageResult:
    """Result from profiling a single pipeline stage."""

    name: str
    total_seconds: float
    per_card_seconds: float
    card_count: int
    profile_html: str | None  # pyinstrument HTML (None for parallel/unprofiled)
    profile_filename: str  # e.g. "profile_render.html"
    extra: dict[str, Any] = field(default_factory=dict)


def _worker_init(db_path_str: str) -> None:
    """Initializer for subprocess workers: patch DB path to temp location."""
    import app.core.database as db_mod
    import app.core.paths as paths_mod

    paths_mod.get_db_path = lambda: Path(db_path_str)  # type: ignore[assignment]
    db_mod._engine = None  # type: ignore[attr-defined]
    db_mod._Session = None  # type: ignore[attr-defined]


def _save_profile(profiler: Profiler, output_dir: Path, filename: str) -> str:
    """Save pyinstrument HTML profile and return the HTML string."""
    html = profiler.output_html()
    (output_dir / filename).write_text(html)
    return html


# ---------------------------------------------------------------------------
# Stage: Hash
# ---------------------------------------------------------------------------


def profile_hash(pdfs: list[Path], output_dir: Path, progress: Progress) -> StageResult:
    """Profile compute_file_hash() on all PDFs."""
    from app.core.database import compute_file_hash

    profiler = Profiler()
    task = progress.add_task("Hash computation", total=len(pdfs))
    profiler.start()
    for pdf in pdfs:
        compute_file_hash(pdf)
        progress.advance(task)
    profiler.stop()

    total = profiler.last_session.duration  # type: ignore[union-attr]
    filename = "profile_hash.html"
    html = _save_profile(profiler, output_dir, filename)

    return StageResult(
        name="Hash",
        total_seconds=total,
        per_card_seconds=total / len(pdfs),
        card_count=len(pdfs),
        profile_html=html,
        profile_filename=filename,
    )


# ---------------------------------------------------------------------------
# Stage: Database
# ---------------------------------------------------------------------------


def profile_database(pdfs: list[Path], output_dir: Path, progress: Progress) -> StageResult:
    """Profile database round-trip: save_raw_ocr + reprocess + get_card_state."""
    from app.core.database import compute_file_hash, get_card_state, reprocess_candidates_from_raw, save_raw_ocr

    profiler = Profiler()
    task = progress.add_task("Database ops", total=len(pdfs))
    profiler.start()
    for pdf in pdfs:
        file_hash = compute_file_hash(pdf)
        save_raw_ocr(file_hash, "profiling dummy text for database timing")
        reprocess_candidates_from_raw(file_hash)
        get_card_state(file_hash)
        progress.advance(task)
    profiler.stop()

    total = profiler.last_session.duration  # type: ignore[union-attr]
    filename = "profile_database.html"
    html = _save_profile(profiler, output_dir, filename)

    return StageResult(
        name="Database",
        total_seconds=total,
        per_card_seconds=total / len(pdfs),
        card_count=len(pdfs),
        profile_html=html,
        profile_filename=filename,
    )


# ---------------------------------------------------------------------------
# Stage: Render
# ---------------------------------------------------------------------------


def profile_render(
    pdfs: list[Path], output_dir: Path, progress: Progress
) -> tuple[StageResult, dict[Path, list[Image.Image]]]:
    """Profile render_all_pages() on all PDFs. Returns images for downstream stages."""
    from app.core.pdf_renderer import render_all_pages

    images_by_path: dict[Path, list[Image.Image]] = {}
    profiler = Profiler()

    task = progress.add_task("PDF rendering", total=len(pdfs))
    profiler.start()
    for pdf in pdfs:
        images_by_path[pdf] = render_all_pages(pdf, dpi=PDF_DPI)
        progress.advance(task)
    profiler.stop()

    total = profiler.last_session.duration  # type: ignore[union-attr]
    filename = "profile_render.html"
    html = _save_profile(profiler, output_dir, filename)

    result = StageResult(
        name="Render",
        total_seconds=total,
        per_card_seconds=total / len(pdfs),
        card_count=len(pdfs),
        profile_html=html,
        profile_filename=filename,
    )
    return result, images_by_path


# ---------------------------------------------------------------------------
# Stage: OCR
# ---------------------------------------------------------------------------


def profile_ocr(
    images_by_path: dict[Path, list[Image.Image]], output_dir: Path, progress: Progress
) -> tuple[StageResult, dict[Path, str]]:
    """Profile extract_text_all_pages() on pre-rendered images."""
    from app.core.ocr_engine import extract_text_all_pages

    texts_by_path: dict[Path, str] = {}
    profiler = Profiler()
    count = len(images_by_path)

    task = progress.add_task("OCR", total=count)
    profiler.start()
    for path, images in images_by_path.items():
        texts_by_path[path] = extract_text_all_pages(images)
        progress.advance(task)
    profiler.stop()

    total = profiler.last_session.duration  # type: ignore[union-attr]
    filename = "profile_ocr.html"
    html = _save_profile(profiler, output_dir, filename)

    result = StageResult(
        name="OCR",
        total_seconds=total,
        per_card_seconds=total / count,
        card_count=count,
        profile_html=html,
        profile_filename=filename,
    )
    return result, texts_by_path


# ---------------------------------------------------------------------------
# Stage: Name extraction
# ---------------------------------------------------------------------------


def profile_names(texts_by_path: dict[Path, str], output_dir: Path, progress: Progress) -> StageResult:
    """Profile extract_family_names() on pre-extracted OCR text."""
    from app.core.name_extractor import extract_family_names

    profiler = Profiler()
    count = len(texts_by_path)

    task = progress.add_task("Name extraction", total=count)
    profiler.start()
    for text in texts_by_path.values():
        extract_family_names(text)
        progress.advance(task)
    profiler.stop()

    total = profiler.last_session.duration  # type: ignore[union-attr]
    filename = "profile_names.html"
    html = _save_profile(profiler, output_dir, filename)

    return StageResult(
        name="Name extraction",
        total_seconds=total,
        per_card_seconds=total / count,
        card_count=count,
        profile_html=html,
        profile_filename=filename,
    )


# ---------------------------------------------------------------------------
# Stage: Full pipeline (sequential)
# ---------------------------------------------------------------------------


def profile_full_sequential(pdfs: list[Path], output_dir: Path, progress: Progress) -> StageResult:
    """Profile process_pdf_worker() sequentially under pyinstrument."""
    from app.core.pdf_worker import process_pdf_worker

    profiler = Profiler()

    task = progress.add_task("Full (sequential)", total=len(pdfs))
    profiler.start()
    for pdf in pdfs:
        process_pdf_worker(str(pdf))
        progress.advance(task)
    profiler.stop()

    total = profiler.last_session.duration  # type: ignore[union-attr]
    filename = "profile_full_sequential.html"
    html = _save_profile(profiler, output_dir, filename)

    return StageResult(
        name="Full (sequential)",
        total_seconds=total,
        per_card_seconds=total / len(pdfs),
        card_count=len(pdfs),
        profile_html=html,
        profile_filename=filename,
    )


# ---------------------------------------------------------------------------
# Stage: Full pipeline (parallel)
# ---------------------------------------------------------------------------


def profile_full_parallel(
    pdfs: list[Path], output_dir: Path, progress: Progress, sequential_seconds: float, db_path: Path
) -> StageResult:
    """Profile process_pdf_worker() with ProcessPoolExecutor. Wall time only."""
    workers = min(len(pdfs), multiprocessing.cpu_count())

    task = progress.add_task("Full (parallel)", total=len(pdfs))
    start = time.perf_counter()
    with ProcessPoolExecutor(
        max_workers=workers,
        initializer=_worker_init,
        initargs=(str(db_path),),
    ) as executor:
        futures = {executor.submit(process_pdf_worker_str, str(pdf)): pdf for pdf in pdfs}
        for future in as_completed(futures):
            future.result()  # propagate exceptions
            progress.advance(task)
    total = time.perf_counter() - start

    speedup = sequential_seconds / total if total > 0 else 0

    return StageResult(
        name="Full (parallel)",
        total_seconds=total,
        per_card_seconds=total / len(pdfs),
        card_count=len(pdfs),
        profile_html=None,
        profile_filename="",
        extra={"workers": workers, "speedup": speedup},
    )


def process_pdf_worker_str(pdf_path_str: str) -> None:
    """Thin wrapper for ProcessPoolExecutor — imports inside worker process."""
    from app.core.pdf_worker import process_pdf_worker

    process_pdf_worker(pdf_path_str)


# ---------------------------------------------------------------------------
# Stage: AI analysis (optional)
# ---------------------------------------------------------------------------


def profile_ai(images_by_path: dict[Path, list[Image.Image]], output_dir: Path, progress: Progress) -> StageResult:
    """Profile AI analysis stage with a mock (100ms sleep per card, no real API calls).

    Measures async concurrency overhead and pipeline plumbing without spending API credits.
    """
    count = len(images_by_path)
    image_lists = list(images_by_path.values())

    async def _run_all() -> None:
        semaphore = asyncio.Semaphore(AI_CONCURRENCY)

        async def _analyze(_imgs: list[Image.Image]) -> None:
            async with semaphore:
                # Simulate API latency (100ms) without real Anthropic calls
                await asyncio.sleep(0.1)

        await asyncio.gather(*[_analyze(imgs) for imgs in image_lists])

    profiler = Profiler(async_mode="enabled")

    task = progress.add_task("AI analysis (mock)", total=count)
    profiler.start()
    asyncio.run(_run_all())
    profiler.stop()
    progress.update(task, completed=count)

    total = profiler.last_session.duration  # type: ignore[union-attr]
    filename = "profile_ai.html"
    html = _save_profile(profiler, output_dir, filename)

    return StageResult(
        name="AI analysis",
        total_seconds=total,
        per_card_seconds=total / count,
        card_count=count,
        profile_html=html,
        profile_filename=filename,
    )
