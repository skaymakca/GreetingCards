"""CLI and orchestration for the profiling script."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from rich.console import Console
from rich.table import Table

from scripts.helpers import script_output_dir
from scripts.profiling.report import generate_report
from scripts.profiling.stages import (
    StageResult,
    profile_ai,
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
    parser.add_argument("--with-ai", action="store_true", help="Include AI analysis stage (costs API credits)")
    parser.add_argument("--ai-only", action="store_true", help="Profile only AI analysis (skip OCR stages)")
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


def _check_api_key() -> bool:
    """Check if Anthropic API key is configured."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _print_summary(results: list[StageResult], console: Console) -> None:
    """Print a Rich summary table to the console."""
    # Find sequential time for speedup display
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


def _fmt_seconds(seconds: float) -> str:
    """Format seconds for console display."""
    if seconds < 0.001:
        return f"{seconds * 1_000_000:.0f}\u00b5s"
    if seconds < 1:
        return f"{seconds * 1000:.1f}ms"
    if seconds < 60:
        return f"{seconds:.2f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}m {secs:.1f}s"


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    console = Console()

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
    ai_mode = args.with_ai or args.ai_only
    if not args.ai_only and not _check_tessdata():
        console.print("[red]Error:[/red] tessdata not found. Run [bold]make tessdata[/bold] first.")
        sys.exit(1)

    if ai_mode and not _check_api_key():
        console.print("[red]Error:[/red] ANTHROPIC_API_KEY not set. Required for --with-ai / --ai-only.")
        sys.exit(1)

    console.print(f"Profiling [bold]{len(pdfs)}[/bold] PDFs from {corpus_path}")
    if args.limit:
        console.print(f"[dim](limited to {args.limit} files)[/dim]")
    console.print()

    # Database isolation
    with tempfile.TemporaryDirectory(prefix="gc_profiling_") as tmp_str:
        tmp_dir = Path(tmp_str)
        db_path = tmp_dir / "profiling.sqlite"
        _isolate_database(tmp_dir)

        with script_output_dir("profiling") as output_dir:
            results: list[StageResult] = []

            if args.ai_only:
                # AI-only mode: render images (unprofiled) then profile AI
                console.print("[dim]Rendering images for AI analysis...[/dim]")
                from app.core.pdf_renderer import render_all_pages

                images_by_path = {}
                for pdf in pdfs:
                    images_by_path[pdf] = render_all_pages(pdf, dpi=200)

                results.append(profile_ai(images_by_path, output_dir))
            else:
                # Full profiling pipeline
                results.append(profile_hash(pdfs, output_dir))

                render_result, images_by_path = profile_render(pdfs, output_dir)
                results.append(render_result)

                ocr_result, texts_by_path = profile_ocr(images_by_path, output_dir)
                results.append(ocr_result)

                results.append(profile_names(texts_by_path, output_dir))

                seq_result = profile_full_sequential(pdfs, output_dir)
                results.append(seq_result)

                results.append(profile_full_parallel(pdfs, output_dir, seq_result.total_seconds, db_path))

                if args.with_ai:
                    results.append(profile_ai(images_by_path, output_dir))

            # Generate HTML report
            report_path = generate_report(
                results=results,
                corpus_path=corpus_path,
                pdf_count=len(pdfs),
                output_dir=output_dir,
                with_ai=ai_mode,
            )

            # Console summary
            _print_summary(results, console)
            console.print()
            console.print(f"Output: [link=file://{output_dir}]{output_dir}[/link]")

            # Open output folder
            if not args.no_open:
                subprocess.run(["open", str(report_path)], check=False)
