#!/usr/bin/env python3
"""OCR Concurrency Benchmark.

Measures how well different Python concurrency models scale for the OCR step
in greeting card PDF processing.  Uses a single OCR configuration (specified
by short-name) and tests sequential, threads, and futures_processes dispatchers
across various concurrency levels.

Three concurrency models are compared:

    sequential          Single-threaded baseline
    threads             concurrent.futures.ThreadPoolExecutor.submit()
    futures_processes   concurrent.futures.ProcessPoolExecutor.map()

Output
------
    index.html    Self-contained HTML report with a data table, CSS bar chart
                  showing speedup scaling, and a collapsible OCR results sample.

    timing.csv    One row per scenario with wall time, speedup, efficiency,
                  throughput, avg job time, Amdahl's max speedup, and errors.

Usage
-----
    uv run python scripts/benchmark_ocr_concurrency.py ~/Desktop/cards

    uv run python scripts/benchmark_ocr_concurrency.py ~/Desktop/cards \\
        --config tesserocr-default-200-3-pillow-0.15 \\
        --levels 1,2,4,8 --models sequential,threads,futures_processes

Dependencies
------------
Always available:
    Pillow, PyMuPDF

May need installing (``uv add --dev <package>``):
    pytesseract              Python wrapper for the Tesseract CLI.
    tesserocr                Alternative OCR library wrapping the Tesseract C++ API.
    opencv-python-headless   Enables clahe and otsu preprocessing pipelines.
"""

from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console, Group
from rich.live import Live
from rich.markup import escape as rich_escape
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
    Config,
    HAS_OPENCV,
    HAS_PYTESSERACT,
    HAS_TESSEROCR,
    OCR_FNS,
    PREPROCESS_FNS,
    _detect_system_tessdata,
    build_jobs,
    ensure_tessdata_best,
    find_pdfs,
    html_escape,
    html_page,
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
    concurrency_model: str
    worker_count: int
    num_jobs: int
    wall_time_s: float
    job_times: list[float] = field(default_factory=list)
    ocr_texts: list[str] = field(default_factory=list)
    confidences: list[float] = field(default_factory=list)
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
    config: Config
    num_files: int
    concurrency_levels: list[int]
    concurrency_models: list[str]
    warmup_time_s: float
    scenarios: list[ScenarioResult] = field(default_factory=list)
    total_time_s: float = 0.0

    def baseline_time(self) -> float:
        for s in self.scenarios:
            if s.concurrency_model == "sequential" and s.worker_count == 1:
                return s.wall_time_s
        return 0.0

    def speedup(self, scenario: ScenarioResult) -> float:
        baseline = self.baseline_time()
        return baseline / scenario.wall_time_s if scenario.wall_time_s > 0 and baseline > 0 else 0.0

    def efficiency(self, scenario: ScenarioResult) -> float:
        n = scenario.worker_count
        return (self.speedup(scenario) / n) * 100 if n > 0 else 0.0

    def amdahl_max(self, n: int) -> float:
        """Theoretical max speedup from Amdahl's law.

        Estimates serial fraction f from the n=2 run (if available).
        Amdahl: S(n) = 1 / (f + (1-f)/n)
        From n=2 run: f = (2/S2 - 1)
        """
        for s in self.scenarios:
            if s.concurrency_model == "futures_processes" and s.worker_count == 2:
                s2 = self.speedup(s)
                if s2 > 0:
                    f = max(0.0, 2.0 / s2 - 1.0)
                    return 1.0 / (f + (1.0 - f) / n) if n > 0 else 1.0
        return float(n)  # optimistic fallback


# ---------------------------------------------------------------------------
# Worker function (module-level for pickling)
# ---------------------------------------------------------------------------


def _ocr_job(pdf_path_str: str, config_short_name: str, dpi: int) -> tuple[str, float]:
    """Render PDF -> preprocess -> OCR. Returns (ocr_text, confidence).

    Module-level for pickling (macOS spawn).
    """
    cfg = Config.from_short_name(config_short_name)
    pages = render_all_pages(Path(pdf_path_str), dpi)
    preprocess_fn = PREPROCESS_FNS[cfg.preprocess]
    ocr_fn = OCR_FNS[cfg.library]
    texts, confs = [], []
    for page in pages:
        processed = preprocess_fn(page)
        text, conf = ocr_fn(processed, cfg)
        texts.append(text)
        if conf >= 0:
            confs.append(conf)
    return "\n\n".join(texts), (sum(confs) / len(confs) if confs else -1.0)


def _ocr_job_wrapper(
    args: tuple[int, str, str, int],
) -> tuple[int, str, float, float, str | None]:
    """Picklable wrapper for ProcessPoolExecutor.map().

    Args: (job_id, pdf_path_str, config_short_name, dpi)
    Returns: (job_id, ocr_text, confidence, elapsed_s, error)
    """
    job_id, pdf_path_str, config_short_name, dpi = args
    t0 = time.monotonic()
    try:
        ocr_text, confidence = _ocr_job(pdf_path_str, config_short_name, dpi)
        elapsed = time.monotonic() - t0
        return (job_id, ocr_text, confidence, elapsed, None)
    except Exception as exc:
        err = exc
        elapsed = time.monotonic() - t0
        return (job_id, "", -1.0, elapsed, str(err))


def _timed_ocr_job(
    pdf_path_str: str, config_short_name: str, dpi: int,
) -> tuple[str, float, float, str | None]:
    """Run a single OCR job and return (ocr_text, confidence, elapsed_s, error_or_None)."""
    t0 = time.monotonic()
    try:
        ocr_text, confidence = _ocr_job(pdf_path_str, config_short_name, dpi)
        return (ocr_text, confidence, time.monotonic() - t0, None)
    except Exception as exc:
        err = exc
        return ("", -1.0, time.monotonic() - t0, str(err))


# ---------------------------------------------------------------------------
# Dispatchers
# ---------------------------------------------------------------------------


def _dispatch_sequential(
    jobs: list[tuple[int, Path]],
    config_short_name: str,
    dpi: int,
    _worker_count: int,
) -> list[tuple[int, str, float, float, str | None]]:
    results: list[tuple[int, str, float, float, str | None]] = []
    for job_id, pdf_path in jobs:
        t0 = time.monotonic()
        try:
            ocr_text, confidence = _ocr_job(str(pdf_path), config_short_name, dpi)
            elapsed = time.monotonic() - t0
            results.append((job_id, ocr_text, confidence, elapsed, None))
        except Exception as exc:
            err = exc
            elapsed = time.monotonic() - t0
            results.append((job_id, "", -1.0, elapsed, str(err)))
    return results


def _dispatch_threads(
    jobs: list[tuple[int, Path]],
    config_short_name: str,
    dpi: int,
    worker_count: int,
) -> list[tuple[int, str, float, float, str | None]]:
    results = []
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {}
        for job_id, pdf_path in jobs:
            f = executor.submit(_timed_ocr_job, str(pdf_path), config_short_name, dpi)
            futures[f] = job_id
        for f in futures:
            job_id = futures[f]
            ocr_text, confidence, elapsed, error = f.result()
            results.append((job_id, ocr_text, confidence, elapsed, error))
    return results


def _dispatch_futures_processes(
    jobs: list[tuple[int, Path]],
    config_short_name: str,
    dpi: int,
    worker_count: int,
) -> list[tuple[int, str, float, float, str | None]]:
    work_items = [(jid, str(path), config_short_name, dpi) for jid, path in jobs]
    with ProcessPoolExecutor(max_workers=worker_count) as executor:
        raw = list(executor.map(_ocr_job_wrapper, work_items))
    return [(job_id, ocr_text, conf, elapsed, error) for job_id, ocr_text, conf, elapsed, error in raw]


DISPATCHERS = {
    "sequential": _dispatch_sequential,
    "threads": _dispatch_threads,
    "futures_processes": _dispatch_futures_processes,
}

ALL_MODELS = list(DISPATCHERS.keys())
DEFAULT_LEVELS = [1, 2, 4, 8, 12, 14, 16]
DEFAULT_CONFIG = "tesserocr-default-200-3-pillow-0.15"


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------


def _validate_config(cfg: Config) -> None:
    """Check that the OCR library and preprocessing are available."""
    available_libs = set()
    if HAS_PYTESSERACT:
        available_libs.add("pytesseract")
    if HAS_TESSEROCR:
        available_libs.add("tesserocr")
    if cfg.library not in available_libs:
        console.print(f"[red]Error: OCR library '{rich_escape(cfg.library)}' is not installed[/]")
        console.print(f"  Available: {available_libs or 'none'}")
        sys.exit(1)

    if cfg.preprocess in ("clahe", "otsu") and not HAS_OPENCV:
        console.print(f"[red]Error: preprocessing '{rich_escape(cfg.preprocess)}' requires OpenCV (not installed)[/]")
        sys.exit(1)


def run_benchmark(
    corpus_path: Path,
    cfg: Config,
    concurrency_levels: list[int],
    concurrency_models: list[str],
) -> BenchmarkResult:
    pdf_paths = find_pdfs(corpus_path)
    if not pdf_paths:
        console.print(f"[red]No PDF files found in {corpus_path}[/]")
        sys.exit(1)

    _validate_config(cfg)

    # Set TESSDATA_PREFIX for worker processes
    system_tessdata = _detect_system_tessdata()
    if system_tessdata:
        os.environ["TESSDATA_PREFIX"] = system_tessdata

    # Pre-download tessdata_best if needed
    if cfg.tessdata == "tessdata_best":
        ensure_tessdata_best()

    config_short_name = cfg.short_name

    console.print(Panel(
        f"  Corpus:  {corpus_path} ({len(pdf_paths)} files)\n"
        f"  Config:  {rich_escape(cfg.name)}\n"
        f"  Models:  {', '.join(concurrency_models)}\n"
        f"  Levels:  {', '.join(map(str, concurrency_levels))}",
        title="OCR Concurrency Benchmark",
        title_align="left",
        expand=False,
    ))

    total_t0 = time.monotonic()

    # Warmup: one OCR pass per file
    warmup_t0 = time.monotonic()
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=True,
    ) as progress:
        warmup_task = progress.add_task("Warmup", total=len(pdf_paths))
        for pdf_path in pdf_paths:
            try:
                _ocr_job(str(pdf_path), config_short_name, cfg.dpi)
            except Exception as exc:
                err = exc
                console.print(f"[yellow]Warning: warmup failed for {pdf_path.name}: {err}[/]")
            progress.advance(warmup_task)
    warmup_time = time.monotonic() - warmup_t0
    console.print(f"  Warmup complete: {warmup_time:.1f}s\n")

    result = BenchmarkResult(
        corpus_path=corpus_path,
        config=cfg,
        num_files=len(pdf_paths),
        concurrency_levels=concurrency_levels,
        concurrency_models=concurrency_models,
        warmup_time_s=warmup_time,
    )

    # Count total scenarios for progress bar
    total_scenarios = 0
    for model in concurrency_models:
        for level in concurrency_levels:
            if model == "sequential" and level != 1:
                continue
            total_scenarios += 1

    # Compute fixed-width description for stable progress bar
    _MAX_LINE = 200
    _BAR_OVERHEAD = 40
    max_label_len = max(
        len(f"{model} @ {level}w")
        for model in concurrency_models
        for level in concurrency_levels
        if not (model == "sequential" and level != 1)
    )
    max_desc_len = min(max_label_len, _MAX_LINE - _BAR_OVERHEAD)

    def _bench_desc(model: str, level: int) -> str:
        label = f"{model} @ {level}w"
        if len(label) > max_desc_len:
            label = label[: max_desc_len - 3] + "..."
        return f"{label:<{max_desc_len}}"

    # Table overhead: header(1) + header separator(1) + top/bottom border(2) + progress bar(1) + blank(1)
    _TABLE_OVERHEAD = 6

    def _build_results_table(
        scenarios: list[ScenarioResult], *, max_rows: int | None = None,
    ) -> Table:
        """Build the results table.

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
            idx = scenarios.index(s) + 1
            sp = result.speedup(s)
            eff = result.efficiency(s)
            err_style = "red" if s.errors else "dim"
            table.add_row(
                str(idx),
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
        for model in concurrency_models:
            for level in concurrency_levels:
                # Sequential only runs at level=1
                if model == "sequential" and level != 1:
                    continue

                progress.update(
                    bench_task,
                    description=_bench_desc(model, level),
                )

                jobs = build_jobs(pdf_paths, level)
                dispatch_fn = DISPATCHERS[model]
                wall_t0 = time.monotonic()
                raw_results = dispatch_fn(jobs, config_short_name, cfg.dpi, level)
                wall_time = time.monotonic() - wall_t0

                job_times = [elapsed for _, _, _, elapsed, _ in raw_results]
                ocr_texts = [text for _, text, _, _, _ in raw_results]
                confidences = [conf for _, _, conf, _, _ in raw_results if conf >= 0]
                errors = sum(1 for _, _, _, _, err in raw_results if err is not None)

                scenario = ScenarioResult(
                    concurrency_model=model,
                    worker_count=level,
                    num_jobs=len(jobs),
                    wall_time_s=wall_time,
                    job_times=job_times,
                    ocr_texts=ocr_texts,
                    confidences=confidences,
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
                if pad_lines > 0:
                    padding = Text("\n" * (pad_lines - 1))
                    live.update(Group(table, padding, progress))
                else:
                    live.update(Group(table, progress))

        # Clear live display before exiting alternate screen
        live.update(progress)

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
details { margin: 1rem 0; }
details summary {
    cursor: pointer;
    font-size: 0.9rem;
    color: var(--accent);
}
details summary:hover { text-decoration: underline; }
.ocr-sample {
    font-family: var(--mono);
    font-size: 0.75rem;
    white-space: pre-wrap;
    word-break: break-word;
    max-height: 300px;
    overflow-y: auto;
    background: var(--bg-alt);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0.5rem;
    margin-top: 0.5rem;
}
"""

MODEL_COLORS = {
    "sequential": "#6b7280",
    "threads": "#3b82f6",
    "futures_processes": "#22c55e",
}


def _generate_report(result: BenchmarkResult) -> str:
    """Generate the full HTML report."""
    lines: list[str] = []

    # Header
    lines.append("<h1>OCR Concurrency Benchmark</h1>")
    lines.append("<div class='meta'>")
    lines.append(f"  <span>Corpus: <code>{html_escape(str(result.corpus_path))}</code></span>")
    lines.append(f"  <span>Files: {result.num_files}</span>")
    lines.append(f"  <span>Config: <code>{html_escape(result.config.short_name)}</code></span>")
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

    # Collect unique values for filter dropdowns
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

    # Filter toolbar
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

    scenarios = result.scenarios

    # Collect quartile values
    wall_values = [s.wall_time_s for s in scenarios]
    sp_values = [result.speedup(s) for s in scenarios]
    eff_values = [result.efficiency(s) for s in scenarios]
    tp_values = [s.throughput for s in scenarios]
    avg_values = [s.avg_job_time for s in scenarios]
    amdahl_values = [result.amdahl_max(s.worker_count) for s in scenarios]

    # Data table
    lines.append("<h2>Results</h2>")
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
        amdahl = result.amdahl_max(s.worker_count)

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
    lines.append("<h3>Speedup Scaling</h3>")
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

    # OCR results sample (collapsible)
    # Show first 5 unique OCR texts from the sequential baseline
    baseline = next(
        (s for s in scenarios if s.concurrency_model == "sequential" and s.worker_count == 1),
        scenarios[0] if scenarios else None,
    )
    if baseline and baseline.ocr_texts:
        lines.append("<h3>OCR Results Sample</h3>")
        sample_count = min(5, len(baseline.ocr_texts))
        for i in range(sample_count):
            text = baseline.ocr_texts[i]
            conf = baseline.confidences[i] if i < len(baseline.confidences) else -1.0
            conf_str = f"{conf:.1f}%" if conf >= 0 else "n/a"
            lines.append(
                f"<details><summary>Job {i + 1} (confidence: {conf_str})</summary>"
                f"<div class='ocr-sample'>{html_escape(text) if text.strip() else '[EMPTY]'}</div>"
                f"</details>"
            )

    return html_page("OCR Concurrency Benchmark", "\n".join(lines), EXTRA_CSS)


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------


def _write_csv(path: Path, result: BenchmarkResult) -> None:
    headers = [
        "concurrency_model", "workers", "num_jobs", "wall_time_s",
        "speedup", "efficiency_pct", "throughput_per_s", "avg_job_time_s",
        "amdahl_max", "errors",
    ]
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for s in result.scenarios:
            sp = result.speedup(s)
            eff = result.efficiency(s)
            amdahl = result.amdahl_max(s.worker_count)
            writer.writerow([
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

_FOLDER_NAME = "benchmark_ocr_concurrency"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="OCR Concurrency Benchmark — test concurrency models for OCR processing"
    )
    parser.add_argument("corpus", type=Path, help="Path to directory containing PDF files")
    parser.add_argument(
        "-o", "--output", type=Path, default=None,
        help="Output directory for reports (default: timestamped)",
    )
    parser.add_argument(
        "--config", type=str, default=DEFAULT_CONFIG,
        help=f"OCR config short-name (default: {DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "--levels", type=str, default=",".join(map(str, DEFAULT_LEVELS)),
        help=f"Comma-separated concurrency levels (default: {','.join(map(str, DEFAULT_LEVELS))})",
    )
    parser.add_argument(
        "--models", type=str, default=None,
        help=f"Comma-separated models to test (default: all — {','.join(ALL_MODELS)})",
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

    try:
        cfg = Config.from_short_name(args.config)
    except ValueError as exc:
        err = exc
        console.print(f"[red]Error: {err}[/]")
        sys.exit(1)

    levels = sorted(set(int(x) for x in args.levels.split(",")))
    models = [x.strip() for x in args.models.split(",")] if args.models else list(ALL_MODELS)

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

    result = run_benchmark(corpus_path, cfg, levels, models)

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
