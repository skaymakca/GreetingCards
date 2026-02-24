#!/usr/bin/env python3
"""Preprocessing Concurrency Benchmark.

Measures how well different Python concurrency models scale for the CPU-bound
image preprocessing step used in greeting card PDF processing.  Helps choose
the right concurrency approach for the main app and future benchmarks.

Six concurrency models are compared:

    sequential          Single-threaded baseline
    threads             concurrent.futures.ThreadPoolExecutor.submit()
    futures_processes   concurrent.futures.ProcessPoolExecutor.map()
    asyncio_threads     asyncio + loop.run_in_executor(ThreadPoolExecutor)
    asyncio_processes   asyncio + loop.run_in_executor(ProcessPoolExecutor)
    mp_queue            multiprocessing.Queue with dedicated workers

Three preprocessing pipelines are tested (sauvola is excluded because its
preprocessing is identical to pillow — the difference is a Tesseract config
flag, not a preprocessing step):

    pillow    grayscale -> autocontrast -> sharpen (Pillow only)
    clahe     CLAHE + denoising + adaptive threshold (OpenCV)
    otsu      Otsu threshold + sharpen (OpenCV)

Output
------
    index.html    Self-contained HTML report with per-pipeline data tables,
                  CSS bar charts showing speedup scaling, and a cross-pipeline
                  comparison table.

    timing.csv    One row per scenario with wall time, speedup, efficiency,
                  throughput, avg job time, Amdahl's max speedup, and errors.

Usage
-----
    uv run python scripts/benchmark_pre_processing_concurrency.py ~/Desktop/cards

    uv run python scripts/benchmark_pre_processing_concurrency.py ~/Desktop/cards \\
        --levels 1,2,4,8 --models sequential,futures_processes

Dependencies
------------
Always available:
    Pillow, PyMuPDF

May need installing (``uv add --dev <package>``):
    opencv-python-headless   Enables clahe and otsu preprocessing pipelines.

    Whether this is already installed depends on the main app's current
    OCR library choice.  If missing, only the pillow pipeline is available.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import multiprocessing as mp
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.text import Text

from scripts.benchmark.common import (
    HAS_OPENCV,
    PREPROCESS_FNS,
    build_jobs,
    find_pdfs,
    html_escape,
    html_page,
    image_to_png_bytes,
    quartile_class,
    render_all_pages,
    sortable_th,
)


console = Console(stderr=True, highlight=False)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ScenarioResult:
    preprocess_name: str
    concurrency_model: str
    worker_count: int
    num_jobs: int
    wall_time_s: float
    job_times: list[float] = field(default_factory=list)
    errors: int = 0

    @property
    def throughput(self) -> float:
        return self.num_jobs / self.wall_time_s if self.wall_time_s > 0 else 0.0

    @property
    def avg_job_time(self) -> float:
        return sum(self.job_times) / len(self.job_times) if self.job_times else 0.0


@dataclass
class BenchmarkResult:
    corpus_path: Path
    dpi: int
    num_files: int
    concurrency_levels: list[int]
    concurrency_models: list[str]
    preprocess_names: list[str]
    warmup_time_s: float
    scenarios: list[ScenarioResult] = field(default_factory=list)
    total_time_s: float = 0.0

    def baseline_time(self, preprocess_name: str) -> float:
        for s in self.scenarios:
            if (
                s.preprocess_name == preprocess_name
                and s.concurrency_model == "sequential"
                and s.worker_count == 1
            ):
                return s.wall_time_s
        return 0.0

    def speedup(self, scenario: ScenarioResult) -> float:
        baseline = self.baseline_time(scenario.preprocess_name)
        return baseline / scenario.wall_time_s if scenario.wall_time_s > 0 and baseline > 0 else 0.0

    def efficiency(self, scenario: ScenarioResult) -> float:
        n = scenario.worker_count
        return (self.speedup(scenario) / n) * 100 if n > 0 else 0.0

    def amdahl_max(self, preprocess_name: str, n: int) -> float:
        """Theoretical max speedup from Amdahl's law.

        Estimates serial fraction f from the n=2 run (if available).
        Amdahl: S(n) = 1 / (f + (1-f)/n)
        From n=2 run: f = (2/S2 - 1)
        """
        # Find n=2 sequential-based speedup
        for s in self.scenarios:
            if (
                s.preprocess_name == preprocess_name
                and s.concurrency_model == "futures_processes"
                and s.worker_count == 2
            ):
                s2 = self.speedup(s)
                if s2 > 0:
                    f = max(0.0, 2.0 / s2 - 1.0)
                    return 1.0 / (f + (1.0 - f) / n) if n > 0 else 1.0
        return float(n)  # optimistic fallback


# ---------------------------------------------------------------------------
# Worker function (module-level for pickling)
# ---------------------------------------------------------------------------


def _process_job(pdf_path_str: str, preprocess_name: str, dpi: int) -> list[bytes]:
    """Render PDF pages and apply preprocessing. Returns list of PNG bytes.

    This is a module-level function so it can be pickled for multiprocessing
    on macOS (which uses the 'spawn' start method).
    """
    pages = render_all_pages(Path(pdf_path_str), dpi)
    preprocess_fn = PREPROCESS_FNS[preprocess_name]
    return [image_to_png_bytes(preprocess_fn(page)) for page in pages]


def _process_job_wrapper(
    args: tuple[int, str, str, int],
) -> tuple[int, bytes | None, float, str | None]:
    """Picklable wrapper for ProcessPoolExecutor.map().

    Args: (job_id, pdf_path_str, preprocess_name, dpi)
    Returns: (job_id, result_marker, elapsed_s, error)
    """
    job_id, pdf_path_str, preprocess_name, dpi = args
    t0 = time.monotonic()
    try:
        _process_job(pdf_path_str, preprocess_name, dpi)
        elapsed = time.monotonic() - t0
        return (job_id, b"ok", elapsed, None)
    except Exception as exc:
        err = exc
        elapsed = time.monotonic() - t0
        return (job_id, None, elapsed, str(err))


def _queue_worker(
    job_queue: mp.Queue,
    result_queue: mp.Queue,
    preprocess_name: str,
    dpi: int,
) -> None:
    """Worker process for mp.Queue pattern."""
    while True:
        item = job_queue.get()
        if item is None:
            break
        job_id, pdf_path_str = item
        t0 = time.monotonic()
        try:
            _process_job(pdf_path_str, preprocess_name, dpi)
            elapsed = time.monotonic() - t0
            result_queue.put((job_id, elapsed, None))
        except Exception as exc:
            err = exc
            elapsed = time.monotonic() - t0
            result_queue.put((job_id, elapsed, str(err)))


# ---------------------------------------------------------------------------
# Dispatch functions
# ---------------------------------------------------------------------------


def _dispatch_sequential(
    jobs: list[tuple[int, Path]],
    preprocess_name: str,
    dpi: int,
    _worker_count: int,
) -> list[tuple[int, float, str | None]]:
    results: list[tuple[int, float, str | None]] = []
    for job_id, pdf_path in jobs:
        t0 = time.monotonic()
        try:
            _process_job(str(pdf_path), preprocess_name, dpi)
            elapsed = time.monotonic() - t0
            results.append((job_id, elapsed, None))
        except Exception as exc:
            err = exc
            elapsed = time.monotonic() - t0
            results.append((job_id, elapsed, str(err)))
    return results


def _dispatch_threads(
    jobs: list[tuple[int, Path]],
    preprocess_name: str,
    dpi: int,
    worker_count: int,
) -> list[tuple[int, float, str | None]]:
    results = []
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {}
        for job_id, pdf_path in jobs:
            f = executor.submit(_timed_job, str(pdf_path), preprocess_name, dpi)
            futures[f] = job_id
        for f in futures:
            job_id = futures[f]
            elapsed, error = f.result()
            results.append((job_id, elapsed, error))
    return results


def _timed_job(pdf_path_str: str, preprocess_name: str, dpi: int) -> tuple[float, str | None]:
    """Run a single job and return (elapsed_s, error_or_None)."""
    t0 = time.monotonic()
    try:
        _process_job(pdf_path_str, preprocess_name, dpi)
        return (time.monotonic() - t0, None)
    except Exception as exc:
        err = exc
        return (time.monotonic() - t0, str(err))


def _dispatch_futures_processes(
    jobs: list[tuple[int, Path]],
    preprocess_name: str,
    dpi: int,
    worker_count: int,
) -> list[tuple[int, float, str | None]]:
    work_items = [(jid, str(path), preprocess_name, dpi) for jid, path in jobs]
    with ProcessPoolExecutor(max_workers=worker_count) as executor:
        raw = list(executor.map(_process_job_wrapper, work_items))
    return [(job_id, elapsed, error) for job_id, _, elapsed, error in raw]


def _dispatch_asyncio_threads(
    jobs: list[tuple[int, Path]],
    preprocess_name: str,
    dpi: int,
    worker_count: int,
) -> list[tuple[int, float, str | None]]:
    async def _run() -> list[tuple[int, float, str | None]]:
        loop = asyncio.get_event_loop()
        executor = ThreadPoolExecutor(max_workers=worker_count)

        async def run_one(job_id: int, pdf_path: Path) -> tuple[int, float, str | None]:
            elapsed, error = await loop.run_in_executor(
                executor, _timed_job, str(pdf_path), preprocess_name, dpi,
            )
            return (job_id, elapsed, error)

        tasks = [run_one(jid, path) for jid, path in jobs]
        results = await asyncio.gather(*tasks)
        executor.shutdown(wait=False)
        return list(results)

    return asyncio.run(_run())


def _dispatch_asyncio_processes(
    jobs: list[tuple[int, Path]],
    preprocess_name: str,
    dpi: int,
    worker_count: int,
) -> list[tuple[int, float, str | None]]:
    async def _run() -> list[tuple[int, float, str | None]]:
        loop = asyncio.get_event_loop()
        executor = ProcessPoolExecutor(max_workers=worker_count)

        async def run_one(job_id: int, pdf_path: Path) -> tuple[int, float, str | None]:
            try:
                _, _, elapsed, error = await loop.run_in_executor(
                    executor,
                    _process_job_wrapper,
                    (job_id, str(pdf_path), preprocess_name, dpi),
                )
            except Exception as exc:
                err = exc
                elapsed, error = 0.0, str(err)
            return (job_id, elapsed, error)

        tasks = [run_one(jid, path) for jid, path in jobs]
        results = await asyncio.gather(*tasks)
        executor.shutdown(wait=False)
        return list(results)

    return asyncio.run(_run())


def _dispatch_mp_queue(
    jobs: list[tuple[int, Path]],
    preprocess_name: str,
    dpi: int,
    worker_count: int,
) -> list[tuple[int, float, str | None]]:
    job_queue: mp.Queue = mp.Queue()
    result_queue: mp.Queue = mp.Queue()

    workers = []
    for _ in range(worker_count):
        p = mp.Process(
            target=_queue_worker,
            args=(job_queue, result_queue, preprocess_name, dpi),
        )
        p.start()
        workers.append(p)

    for job_id, pdf_path in jobs:
        job_queue.put((job_id, str(pdf_path)))

    for _ in range(worker_count):
        job_queue.put(None)

    results = []
    for _ in range(len(jobs)):
        results.append(result_queue.get())

    for p in workers:
        p.join()

    return results


DISPATCHERS = {
    "sequential": _dispatch_sequential,
    "threads": _dispatch_threads,
    "futures_processes": _dispatch_futures_processes,
    "asyncio_threads": _dispatch_asyncio_threads,
    "asyncio_processes": _dispatch_asyncio_processes,
    "mp_queue": _dispatch_mp_queue,
}

ALL_MODELS = list(DISPATCHERS.keys())
ALL_PIPELINES = ["pillow", "clahe", "otsu"]
DEFAULT_LEVELS = [1, 2, 4, 8, 12, 14, 16]


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------


def run_benchmark(
    corpus_path: Path,
    dpi: int,
    concurrency_levels: list[int],
    concurrency_models: list[str],
    preprocess_names: list[str],
) -> BenchmarkResult:
    pdf_paths = find_pdfs(corpus_path)
    if not pdf_paths:
        console.print(f"[red]No PDF files found in {corpus_path}[/]")
        sys.exit(1)

    # Filter pipelines based on OpenCV availability
    if not HAS_OPENCV:
        available = [p for p in preprocess_names if p == "pillow"]
        skipped = [p for p in preprocess_names if p != "pillow"]
        if skipped:
            console.print(f"[yellow]Warning: skipping {skipped} pipelines (OpenCV not installed)[/]")
        preprocess_names = available
        if not preprocess_names:
            console.print("[red]No preprocessing pipelines available![/]")
            sys.exit(1)

    console.print(Panel(
        f"  Corpus:    {corpus_path} ({len(pdf_paths)} files)\n"
        f"  DPI:       {dpi}\n"
        f"  Pipelines: {', '.join(preprocess_names)}\n"
        f"  Models:    {', '.join(concurrency_models)}\n"
        f"  Levels:    {', '.join(map(str, concurrency_levels))}",
        title="Preprocessing Concurrency Benchmark",
        title_align="left",
        expand=False,
    ))

    total_t0 = time.monotonic()

    # Warmup: one pass through all files x all pipelines
    warmup_total = len(preprocess_names) * len(pdf_paths)
    warmup_t0 = time.monotonic()
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=True,
    ) as progress:
        warmup_task = progress.add_task("Warmup", total=warmup_total)
        for pipeline in preprocess_names:
            for pdf_path in pdf_paths:
                try:
                    _process_job(str(pdf_path), pipeline, dpi)
                except Exception as exc:
                    err = exc
                    console.print(f"[yellow]Warning: warmup failed for {pdf_path.name}/{pipeline}: {err}[/]")
                progress.advance(warmup_task)
    warmup_time = time.monotonic() - warmup_t0
    console.print(f"  Warmup complete: {warmup_time:.1f}s\n")

    result = BenchmarkResult(
        corpus_path=corpus_path,
        dpi=dpi,
        num_files=len(pdf_paths),
        concurrency_levels=concurrency_levels,
        concurrency_models=concurrency_models,
        preprocess_names=preprocess_names,
        warmup_time_s=warmup_time,
    )

    # Count total scenarios for progress bar
    total_scenarios = 0
    for model in concurrency_models:
        for level in concurrency_levels:
            if model == "sequential" and level != 1:
                continue
            total_scenarios += 1
    total_scenarios *= len(preprocess_names)

    # Compute fixed-width description for stable progress bar
    _MAX_LINE = 200
    _BAR_OVERHEAD = 40
    max_label_len = max(
        len(f"{pipeline} — {model} @ {level}w")
        for pipeline in preprocess_names
        for model in concurrency_models
        for level in concurrency_levels
        if not (model == "sequential" and level != 1)
    )
    max_desc_len = min(max_label_len, _MAX_LINE - _BAR_OVERHEAD)

    def _bench_desc(pipeline: str, model: str, level: int) -> str:
        label = f"{pipeline} — {model} @ {level}w"
        if len(label) > max_desc_len:
            label = label[: max_desc_len - 3] + "..."
        return f"{label:<{max_desc_len}}"

    # Table overhead: header(1) + header separator(1) + top/bottom border(2) + progress bar(1) + blank(1)
    _TABLE_OVERHEAD = 6

    def _build_results_table(
        scenarios: list[ScenarioResult], *, max_rows: int | None = None,
    ) -> Table:
        """Build the master results table.

        When *max_rows* is set (live display), only the last *max_rows* data rows
        are shown and a caption indicates how many earlier rows were elided.  When
        None (final print), all rows are included.
        """
        display = scenarios
        elided = 0
        if max_rows is not None and len(scenarios) > max_rows:
            elided = len(scenarios) - max_rows
            display = scenarios[elided:]

        table = Table(show_header=True, header_style="bold", pad_edge=False)
        table.add_column("#", style="dim", width=4, justify="right")
        table.add_column("Pipeline", no_wrap=True)
        table.add_column("Model", no_wrap=True)
        table.add_column("Workers", justify="right")
        table.add_column("Jobs", justify="right")
        table.add_column("Wall Time", justify="right")
        table.add_column("Speedup", justify="right")
        table.add_column("Efficiency", justify="right")
        table.add_column("Throughput", justify="right")
        table.add_column("Errors", justify="right")

        if elided:
            table.caption = f"  ({elided} earlier rows hidden)"
            table.caption_style = "dim"

        for s in display:
            # Row number is the 1-based index in the full list
            idx = scenarios.index(s) + 1
            sp = result.speedup(s)
            eff = result.efficiency(s)
            err_style = "red" if s.errors else "dim"
            table.add_row(
                str(idx),
                s.preprocess_name,
                s.concurrency_model,
                str(s.worker_count),
                str(s.num_jobs),
                f"{s.wall_time_s:.2f}s",
                f"{sp:.2f}x",
                f"{eff:.1f}%",
                f"{s.throughput:.1f}/s",
                f"[{err_style}]{s.errors}[/]",
            )
        return table

    progress = Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
    )
    bench_task = progress.add_task("Benchmarking", total=total_scenarios)

    with Live(progress, console=console, refresh_per_second=10, screen=True) as live:
        for pipeline in preprocess_names:
            for model in concurrency_models:
                for level in concurrency_levels:
                    # Sequential only runs at level=1
                    if model == "sequential" and level != 1:
                        continue

                    progress.update(
                        bench_task,
                        description=_bench_desc(pipeline, model, level),
                    )

                    jobs = build_jobs(pdf_paths, level)
                    dispatch_fn = DISPATCHERS[model]
                    wall_t0 = time.monotonic()
                    raw_results = dispatch_fn(jobs, pipeline, dpi, level)
                    wall_time = time.monotonic() - wall_t0

                    job_times = [elapsed for _, elapsed, _ in raw_results]
                    errors = sum(1 for _, _, err in raw_results if err is not None)

                    scenario = ScenarioResult(
                        preprocess_name=pipeline,
                        concurrency_model=model,
                        worker_count=level,
                        num_jobs=len(jobs),
                        wall_time_s=wall_time,
                        job_times=job_times,
                        errors=errors,
                    )
                    result.scenarios.append(scenario)
                    progress.advance(bench_task)

                    # Cap visible rows to terminal height (re-read on each update for resize)
                    term_h = console.size.height
                    progress_h = 1
                    max_rows = term_h - _TABLE_OVERHEAD - progress_h
                    table = _build_results_table(result.scenarios, max_rows=max_rows)

                    # Measure actual rendered table height, pad to pin progress at bottom
                    measure_console = Console(
                        stderr=True, width=console.size.width, force_terminal=True,
                    )
                    with measure_console.capture() as capture:
                        measure_console.print(table, end="")
                    table_h = capture.get().count("\n")
                    pad_lines = max(0, term_h - table_h - progress_h)
                    # Text("") = 1 rendered line, Text("\n") = 2, etc.
                    # So for N blank lines of padding, use Text("\n" * (N-1)).
                    # For 0 padding, omit it entirely.
                    if pad_lines > 0:
                        padding = Text("\n" * (pad_lines - 1))
                        live.update(Group(table, padding, progress))
                    else:
                        live.update(Group(table, progress))

    console.print(_build_results_table(result.scenarios))
    console.print()

    result.total_time_s = time.monotonic() - total_t0
    return result


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------

EXTRA_CSS = """
.bar-container {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin: 0.15rem 0;
}
.bar-label {
    width: 160px;
    font-size: 0.75rem;
    text-align: right;
    flex-shrink: 0;
}
.bar-track {
    flex: 1;
    height: 20px;
    background: var(--bg-alt);
    border: 1px solid var(--border);
    border-radius: 3px;
    overflow: hidden;
    position: relative;
}
.bar-fill {
    display: block;
    height: 100%;
    border-radius: 3px;
    min-width: 2px;
    transition: width 0.3s ease;
}
.bar-value {
    width: 60px;
    font-size: 0.75rem;
    font-variant-numeric: tabular-nums;
    flex-shrink: 0;
}
.bar-fill.model-sequential { background: #6b7280; }
.bar-fill.model-threads { background: #3b82f6; }
.bar-fill.model-futures_processes { background: #22c55e; }
.bar-fill.model-asyncio_threads { background: #a855f7; }
.bar-fill.model-asyncio_processes { background: #f97316; }
.bar-fill.model-mp_queue { background: #ef4444; }
.legend {
    display: flex;
    gap: 1.5rem;
    flex-wrap: wrap;
    margin: 1rem 0;
    font-size: 0.85rem;
}
.legend-item {
    display: flex;
    align-items: center;
    gap: 0.4rem;
}
.legend-swatch {
    width: 14px;
    height: 14px;
    border-radius: 2px;
    border: 1px solid var(--border);
}
h3 { font-size: 1.05rem; margin: 1.5rem 0 0.5rem; }
"""

MODEL_COLORS = {
    "sequential": "#6b7280",
    "threads": "#3b82f6",
    "futures_processes": "#22c55e",
    "asyncio_threads": "#a855f7",
    "asyncio_processes": "#f97316",
    "mp_queue": "#ef4444",
}


def _generate_report(result: BenchmarkResult) -> str:
    """Generate the full HTML report."""
    lines: list[str] = []

    # Header
    lines.append("<h1>Preprocessing Concurrency Benchmark</h1>")
    lines.append("<div class='meta'>")
    lines.append(f"  <span>Corpus: <code>{html_escape(str(result.corpus_path))}</code></span>")
    lines.append(f"  <span>Files: {result.num_files}</span>")
    lines.append(f"  <span>DPI: {result.dpi}</span>")
    lines.append(f"  <span>Warmup: {result.warmup_time_s:.1f}s</span>")
    lines.append(f"  <span>Total: {result.total_time_s:.1f}s</span>")
    lines.append("</div>")

    # Color legend
    lines.append("<div class='legend'>")
    for model, color in MODEL_COLORS.items():
        if model in result.concurrency_models:
            lines.append(
                f"<span class='legend-item'>"
                f"<span class='legend-swatch' style='background:{color}'></span>"
                f"{html_escape(model)}</span>"
            )
    lines.append("</div>")

    # Collect unique values for filter dropdowns (across all pipelines)
    all_models = sorted({s.concurrency_model for s in result.scenarios})
    all_workers = sorted({str(s.worker_count) for s in result.scenarios}, key=lambda x: int(x))

    # Quartile label maps
    _q_label_higher = {
        "heatmap-q4": "Q4 (best)", "heatmap-q3": "Q3",
        "heatmap-q2": "Q2", "heatmap-q1": "Q1 (worst)",
    }
    _q_label_lower = {
        "heatmap-q4": "Q4 (fastest)", "heatmap-q3": "Q3",
        "heatmap-q2": "Q2", "heatmap-q1": "Q1 (slowest)",
    }

    # Filter toolbar (single toolbar for all pipeline tables)
    lines.append("<div class='filter-toolbar'>")
    model_options = "".join(f"<option value='{m}'>{m}</option>" for m in all_models)
    lines.append(
        f"<label>Model: <select class='filter-select' data-axis='model' "
        f"onchange='applyFilters()'><option value=''>All</option>{model_options}</select></label>"
    )
    worker_options = "".join(f"<option value='{w}'>{w}</option>" for w in all_workers)
    lines.append(
        f"<label>Workers: <select class='filter-select' data-axis='workers' "
        f"onchange='applyFilters()'><option value=''>All</option>{worker_options}</select></label>"
    )
    if len(result.preprocess_names) > 1:
        pipeline_options = "".join(f"<option value='{p}'>{p}</option>" for p in result.preprocess_names)
        lines.append(
            f"<label>Pipeline: <select class='filter-select' data-axis='pipeline' "
            f"onchange='applyFilters()'><option value=''>All</option>{pipeline_options}</select></label>"
        )
    lines.append("<button onclick='resetFilters()'>Reset</button>")
    lines.append("</div>")
    # Quartile filters — second row
    lines.append("<div class='filter-toolbar'>")
    q_lower_options = "".join(f"<option value='{q}'>{q}</option>" for q in ["Q4 (fastest)", "Q3", "Q2", "Q1 (slowest)"])
    q_higher_options = "".join(f"<option value='{q}'>{q}</option>" for q in ["Q4 (best)", "Q3", "Q2", "Q1 (worst)"])
    lines.append(
        f"<label>Wall Time: <select class='filter-select' data-axis='walltimeq' "
        f"onchange='applyFilters()'><option value=''>All</option>{q_lower_options}</select></label>"
    )
    lines.append(
        f"<label>Speedup: <select class='filter-select' data-axis='speedupq' "
        f"onchange='applyFilters()'><option value=''>All</option>{q_higher_options}</select></label>"
    )
    lines.append(
        f"<label>Efficiency: <select class='filter-select' data-axis='efficiencyq' "
        f"onchange='applyFilters()'><option value=''>All</option>{q_higher_options}</select></label>"
    )
    lines.append(
        f"<label>Throughput: <select class='filter-select' data-axis='throughputq' "
        f"onchange='applyFilters()'><option value=''>All</option>{q_higher_options}</select></label>"
    )
    lines.append(
        f"<label>Avg Job: <select class='filter-select' data-axis='avgjobq' "
        f"onchange='applyFilters()'><option value=''>All</option>{q_lower_options}</select></label>"
    )
    lines.append(
        f"<label>Amdahl Max: <select class='filter-select' data-axis='amdahlq' "
        f"onchange='applyFilters()'><option value=''>All</option>{q_higher_options}</select></label>"
    )
    lines.append("</div>")

    # Per-pipeline sections
    for pipeline in result.preprocess_names:
        scenarios = [s for s in result.scenarios if s.preprocess_name == pipeline]
        if not scenarios:
            continue

        lines.append(f"<h2>Pipeline: {html_escape(pipeline)}</h2>")

        # Collect quartile values for this pipeline
        wall_values = [s.wall_time_s for s in scenarios]
        sp_values = [result.speedup(s) for s in scenarios]
        eff_values = [result.efficiency(s) for s in scenarios]
        tp_values = [s.throughput for s in scenarios]
        avg_values = [s.avg_job_time for s in scenarios]
        amdahl_values = [result.amdahl_max(pipeline, s.worker_count) for s in scenarios]

        # Data table
        lines.append("<table class='filterable-table'>")
        lines.append("<thead><tr>")
        lines.append(sortable_th("#", is_num=True))
        lines.append(sortable_th("Model"))
        lines.append(sortable_th("Workers", is_num=True))
        lines.append(sortable_th("Jobs", is_num=True))
        lines.append(sortable_th("Wall Time", is_num=True))
        lines.append(sortable_th("Speedup", is_num=True))
        lines.append(sortable_th("Efficiency", is_num=True))
        lines.append(sortable_th("Throughput", is_num=True))
        lines.append(sortable_th("Avg Job", is_num=True))
        lines.append(sortable_th("Amdahl Max", is_num=True))
        lines.append(sortable_th("Errors", is_num=True))
        lines.append("</tr></thead>")
        lines.append("<tbody>")

        for idx, s in enumerate(scenarios, 1):
            sp = result.speedup(s)
            eff = result.efficiency(s)
            tp = s.throughput
            avg = s.avg_job_time
            amdahl = result.amdahl_max(pipeline, s.worker_count)

            # Quartile classes
            wall_hm = quartile_class(s.wall_time_s, wall_values, reverse=True)
            sp_hm = quartile_class(sp, sp_values)
            eff_hm = quartile_class(eff, eff_values)
            tp_hm = quartile_class(tp, tp_values)
            avg_hm = quartile_class(avg, avg_values, reverse=True)
            amdahl_hm = quartile_class(amdahl, amdahl_values)

            # Quartile labels for filtering
            wall_ql = _q_label_lower[wall_hm]
            sp_ql = _q_label_higher[sp_hm]
            eff_ql = _q_label_higher[eff_hm]
            tp_ql = _q_label_higher[tp_hm]
            avg_ql = _q_label_lower[avg_hm]
            amdahl_ql = _q_label_higher[amdahl_hm]

            lines.append(
                f"<tr data-model='{html_escape(s.concurrency_model)}' "
                f"data-workers='{s.worker_count}' "
                f"data-pipeline='{html_escape(pipeline)}' "
                f"data-walltimeq='{wall_ql}' "
                f"data-speedupq='{sp_ql}' "
                f"data-efficiencyq='{eff_ql}' "
                f"data-throughputq='{tp_ql}' "
                f"data-avgjobq='{avg_ql}' "
                f"data-amdahlq='{amdahl_ql}'>"
            )
            lines.append(f"  <td class='num' data-value='{idx}'>{idx}</td>")
            lines.append(f"  <td>{html_escape(s.concurrency_model)}</td>")
            lines.append(f"  <td class='num' data-value='{s.worker_count}'>{s.worker_count}</td>")
            lines.append(f"  <td class='num' data-value='{s.num_jobs}'>{s.num_jobs}</td>")
            lines.append(f"  <td class='num {wall_hm}' data-value='{s.wall_time_s:.4f}'>{s.wall_time_s:.2f}s</td>")
            lines.append(f"  <td class='num {sp_hm}' data-value='{sp:.4f}'>{sp:.2f}x</td>")
            lines.append(f"  <td class='num {eff_hm}' data-value='{eff:.2f}'>{eff:.1f}%</td>")
            lines.append(f"  <td class='num {tp_hm}' data-value='{tp:.2f}'>{tp:.1f}/s</td>")
            lines.append(f"  <td class='num {avg_hm}' data-value='{avg:.4f}'>{avg:.3f}s</td>")
            lines.append(f"  <td class='num {amdahl_hm}' data-value='{amdahl:.4f}'>{amdahl:.2f}x</td>")
            err_cls = " style='color:var(--red)'" if s.errors else ""
            lines.append(f"  <td class='num'{err_cls} data-value='{s.errors}'>{s.errors}</td>")
            lines.append("</tr>")

        lines.append("</tbody></table>")

        # Bar chart: speedup by model and level
        lines.append(f"<h3>Speedup Scaling — {html_escape(pipeline)}</h3>")
        max_speedup = max((result.speedup(s) for s in scenarios), default=1.0)
        max_speedup = max(max_speedup, 1.0)

        for s in scenarios:
            sp = result.speedup(s)
            pct = (sp / max_speedup) * 100
            label = f"{s.concurrency_model} @ {s.worker_count}"
            lines.append(
                f"<div class='bar-container'>"
                f"<span class='bar-label'>{html_escape(label)}</span>"
                f"<span class='bar-track'>"
                f"<span class='bar-fill model-{html_escape(s.concurrency_model)}' "
                f"style='width:{pct:.1f}%'></span></span>"
                f"<span class='bar-value'>{sp:.2f}x</span>"
                f"</div>"
            )

    # Cross-pipeline comparison
    lines.append("<h2>Cross-Pipeline Comparison — Best Speedup</h2>")
    lines.append("<table>")
    lines.append("<thead><tr>")
    lines.append("<th>Model</th>")
    for pipeline in result.preprocess_names:
        lines.append(f"<th class='num'>{html_escape(pipeline)}</th>")
    lines.append("</tr></thead>")
    lines.append("<tbody>")

    for model in result.concurrency_models:
        lines.append("<tr>")
        lines.append(f"  <td>{html_escape(model)}</td>")
        for pipeline in result.preprocess_names:
            best = 0.0
            for s in result.scenarios:
                if s.preprocess_name == pipeline and s.concurrency_model == model:
                    sp = result.speedup(s)
                    if sp > best:
                        best = sp
            lines.append(f"  <td class='num'>{best:.2f}x</td>")
        lines.append("</tr>")

    lines.append("</tbody></table>")

    return html_page("Preprocessing Concurrency Benchmark", "\n".join(lines), EXTRA_CSS)


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------


def _write_csv(path: Path, result: BenchmarkResult) -> None:
    headers = [
        "preprocess", "concurrency_model", "workers", "num_jobs", "wall_time_s",
        "speedup", "efficiency_pct", "throughput_per_s", "avg_job_time_s",
        "amdahl_max", "errors",
    ]
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for s in result.scenarios:
            sp = result.speedup(s)
            eff = result.efficiency(s)
            amdahl = result.amdahl_max(s.preprocess_name, s.worker_count)
            writer.writerow([
                s.preprocess_name,
                s.concurrency_model,
                s.worker_count,
                s.num_jobs,
                f"{s.wall_time_s:.4f}",
                f"{sp:.4f}",
                f"{eff:.2f}",
                f"{s.throughput:.2f}",
                f"{s.avg_job_time:.4f}",
                f"{amdahl:.4f}",
                s.errors,
            ])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

from scripts.helpers import make_output_dir

_FOLDER_NAME = "benchmark_pre_processing_concurrency"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preprocessing Concurrency Benchmark — test concurrency models for PDF preprocessing"
    )
    parser.add_argument("corpus", type=Path, help="Path to directory containing PDF files")
    parser.add_argument(
        "-o", "--output", type=Path, default=None,
        help="Output directory for reports (default: timestamped)",
    )
    parser.add_argument("--dpi", type=int, default=200, help="DPI for rendering (default: 200)")
    parser.add_argument(
        "--levels", type=str, default=",".join(map(str, DEFAULT_LEVELS)),
        help=f"Comma-separated concurrency levels (default: {','.join(map(str, DEFAULT_LEVELS))})",
    )
    parser.add_argument(
        "--models", type=str, default=None,
        help=f"Comma-separated models to test (default: all — {','.join(ALL_MODELS)})",
    )
    parser.add_argument(
        "--pipelines", type=str, default=None,
        help=f"Comma-separated pipelines (default: {','.join(ALL_PIPELINES)})",
    )
    parser.add_argument(
        "--no-open", action="store_true",
        help="Don't open the report in a browser when done",
    )
    args = parser.parse_args()

    corpus_path = args.corpus.expanduser().resolve()
    if not corpus_path.is_dir():
        console.print(f"[red]Error: {corpus_path} is not a directory[/]")
        sys.exit(1)

    levels = sorted(set(int(x) for x in args.levels.split(",")))
    models = [x.strip() for x in args.models.split(",")] if args.models else list(ALL_MODELS)
    pipelines = [x.strip() for x in args.pipelines.split(",")] if args.pipelines else list(ALL_PIPELINES)

    # Validate model names
    for m in models:
        if m not in DISPATCHERS:
            console.print(f"[red]Error: unknown model '{m}'. Available: {', '.join(ALL_MODELS)}[/]")
            sys.exit(1)

    if args.output:
        output_dir = Path(args.output)
        output_dir.mkdir(parents=True, exist_ok=True)
    else:
        output_dir = make_output_dir(_FOLDER_NAME)

    result = run_benchmark(corpus_path, args.dpi, levels, models, pipelines)

    # Generate outputs
    with console.status("Generating reports..."):
        report_html = _generate_report(result)
        (output_dir / "index.html").write_text(report_html)
        _write_csv(output_dir / "timing.csv", result)

    index_path = output_dir / "index.html"
    console.print(
        f"  index.html — HTML report\n"
        f"  timing.csv — timing data\n"
        f"  Total time: {result.total_time_s:.1f}s\n"
        f"\nOpen {index_path} in a browser to view results.",
    )

    if not args.no_open:
        subprocess.Popen(["open", str(index_path)])


if __name__ == "__main__":
    main()
