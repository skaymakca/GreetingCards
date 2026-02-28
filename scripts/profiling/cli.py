"""CLI and orchestration for the profiling script."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from scripts.helpers import script_output_dir
from scripts.profiling.report import _fmt_time as _fmt_seconds
from scripts.profiling.report import generate_report
from scripts.profiling.stages import (
    StageResult,
    profile_ai,
    profile_database,
    profile_full_parallel,
    profile_full_sequential,
    profile_hash,
    profile_names,
    profile_ocr,
    profile_render,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="profiling",
        description="Profile the PDF processing pipeline (render, OCR, names, AI).",
    )
    parser.add_argument("corpus", type=Path, help="Directory containing PDF files")
    parser.add_argument("--limit", type=int, default=None, help="Max number of PDFs to process")
    parser.add_argument("--no-open", action="store_true", help="Don't open output folder when done")
    return parser


def _find_pdfs(corpus_path: Path, limit: int | None) -> list[Path]:
    """Discover PDFs from corpus path, applying --limit."""
    pdfs = sorted(corpus_path.glob("*.pdf"))
    if not pdfs:
        pdfs = sorted(corpus_path.rglob("*.pdf"))
    if limit:
        pdfs = pdfs[:limit]
    return pdfs


def _isolate_database(tmp_dir: Path) -> None:
    """Monkey-patch DB path to temp dir, reset engine/session globals."""
    import app.core.database as db_mod
    import app.core.paths as paths_mod

    db_path = tmp_dir / "profiling.sqlite"
    paths_mod.get_db_path = lambda: db_path  # type: ignore[assignment]
    db_mod._engine = None  # type: ignore[attr-defined]
    db_mod._Session = None  # type: ignore[attr-defined]


def _check_tessdata() -> bool:
    """Check if tessdata is available for OCR."""
    from app.core.paths import get_runtime_content_path

    tessdata_path = get_runtime_content_path("tessdata/fast/eng.traineddata")
    return tessdata_path.exists()


_PIPELINE_DESCRIPTION = """\
Pipeline stages (each profiled independently, then as full pipeline):

  Individual stages:
    1. Hash         SHA-256 of each PDF file
    2. Database     save_raw_ocr + reprocess_candidates + get_card_state
    3. Render       PDF pages to images (PyMuPDF)
    4. OCR          Tesseract on rendered images
    5. Names        Regex/dictionary name extraction from OCR text
    6. AI (mock)    Simulated API latency (100ms sleep x concurrency=3)

  Full pipeline:
    7. Sequential   process_pdf_worker() per PDF, one at a time
    8. Parallel     Same, via ProcessPoolExecutor across CPU cores

  AI analysis uses a mock (no API calls). The full-pipeline stages
  use a fresh database so timings are not affected by earlier stages.\
"""


def _print_summary(results: list[StageResult], console: Console) -> None:
    """Print a Rich summary table to the console."""
    seq_result = next((r for r in results if r.name == "Full (sequential)"), None)
    par_result = next((r for r in results if r.name == "Full (parallel)"), None)

    table = Table(title="Profiling Results")
    table.add_column("Stage", style="cyan")
    table.add_column("Total", justify="right")
    table.add_column("Per Card", justify="right")
    table.add_column("Throughput", justify="right")

    for r in results:
        total = _fmt_seconds(r.total_seconds)
        per_card = _fmt_seconds(r.per_card_seconds)
        throughput = f"{r.card_count / r.total_seconds:.1f}/s" if r.total_seconds > 0 else "\u2014"
        table.add_row(r.name, total, per_card, throughput)

    console.print()
    console.print(table)

    if seq_result and par_result:
        speedup = par_result.extra.get("speedup", 0)
        workers = par_result.extra.get("workers", "?")
        console.print(f"Parallel speedup: [bold]{speedup:.1f}x[/bold] ({workers} workers)")


def main(argv: list[str] | None = None) -> None:
    invocation = " ".join(sys.argv)
    parser = build_parser()
    args = parser.parse_args(argv)
    console = Console(highlight=False)

    # Validate corpus
    corpus_path: Path = args.corpus.expanduser().resolve()
    if not corpus_path.is_dir():
        console.print(f"[red]Error:[/red] Corpus directory not found: {corpus_path}")
        sys.exit(1)

    pdfs = _find_pdfs(corpus_path, args.limit)
    if not pdfs:
        console.print(f"[red]Error:[/red] No PDF files found in {corpus_path}")
        sys.exit(1)

    # Pre-flight checks
    if not _check_tessdata():
        console.print("[red]Error:[/red] tessdata not found. Run [bold]make tessdata[/bold] first.")
        sys.exit(1)

    console.print(f"Profiling [bold]{len(pdfs)}[/bold] PDFs from {corpus_path}")
    if args.limit:
        console.print(f"[dim](limited to {args.limit} files)[/dim]")
    console.print()
    console.print(_PIPELINE_DESCRIPTION)
    console.print()

    # Database isolation
    with tempfile.TemporaryDirectory(prefix="gc_profiling_") as tmp_str:
        tmp_dir = Path(tmp_str)
        db_path = tmp_dir / "profiling.sqlite"
        _isolate_database(tmp_dir)

        # noinspection PyTypeChecker
        with script_output_dir("profiling") as output_dir:
            # Create subdirectories
            profiles_dir = output_dir / "profiles"
            data_dir = output_dir / "data"
            profiles_dir.mkdir()
            data_dir.mkdir()

            results: list[StageResult] = []

            progress = Progress(
                TextColumn("  {task.description:<20s}"),
                BarColumn(),
                TaskProgressColumn(),
                TimeElapsedColumn(),
            )

            with progress:
                # Individual stage profiling
                results.append(profile_hash(pdfs, profiles_dir, progress))
                results.append(profile_database(pdfs, profiles_dir, progress))

                render_result, images_by_path = profile_render(pdfs, profiles_dir, progress)
                results.append(render_result)

                ocr_result, texts_by_path = profile_ocr(images_by_path, profiles_dir, progress)
                results.append(ocr_result)

                results.append(profile_names(texts_by_path, profiles_dir, progress))
                results.append(profile_ai(images_by_path, profiles_dir, progress))

                # Reset DB so sequential/parallel runs do full processing
                # (profile_database already populated entries that would cause OCR to be skipped)
                db_path.unlink(missing_ok=True)
                _isolate_database(tmp_dir)

                # Full pipeline profiling
                seq_result = profile_full_sequential(pdfs, profiles_dir, progress)
                results.append(seq_result)

                results.append(profile_full_parallel(pdfs, profiles_dir, progress, seq_result.total_seconds, db_path))

            # Generate reports and data files
            report_path = generate_report(
                results=results,
                corpus_path=corpus_path,
                pdf_count=len(pdfs),
                output_dir=output_dir,
                invocation=invocation,
            )

            # Console summary
            _print_summary(results, console)
            console.print()
            console.print(f"Output: [link=file://{output_dir}]{output_dir}[/link]")

            # Open output folder
            if not args.no_open:
                subprocess.run(["open", str(report_path)], check=False)
