"""HTML report generation for profiling results."""

from __future__ import annotations

import multiprocessing
import platform
import sys
from datetime import datetime
from pathlib import Path

from scripts.benchmark.common import html_escape, html_page, sortable_th
from scripts.profiling.stages import StageResult


def _fmt_time(seconds: float) -> str:
    """Format seconds to a human-readable string."""
    if seconds < 0.001:
        return f"{seconds * 1_000_000:.0f}\u00b5s"
    if seconds < 1:
        return f"{seconds * 1000:.1f}ms"
    if seconds < 60:
        return f"{seconds:.2f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}m {secs:.1f}s"


def _fmt_throughput(count: int, seconds: float) -> str:
    """Format throughput as cards/s."""
    if seconds <= 0:
        return "\u2014"
    rate = count / seconds
    return f"{rate:.1f}/s"


def generate_report(
    results: list[StageResult],
    corpus_path: Path,
    pdf_count: int,
    output_dir: Path,
    with_ai: bool,
) -> Path:
    """Generate index.html summary report. Returns path to the report."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # System info
    meta_items = [
        f"Date: {now}",
        f"Python: {sys.version.split()[0]}",
        f"Platform: {platform.machine()}",
        f"CPU cores: {multiprocessing.cpu_count()}",
        f"Corpus: {html_escape(str(corpus_path))}",
        f"PDFs: {pdf_count}",
    ]
    if with_ai:
        meta_items.append("AI: enabled")

    meta_html = " &middot; ".join(f"<span>{m}</span>" for m in meta_items)

    # Timing summary table
    # Find full sequential time for % calculation
    seq_result = next((r for r in results if r.name == "Full (sequential)"), None)
    seq_time = seq_result.total_seconds if seq_result else None

    rows: list[str] = []
    for r in results:
        pct = ""
        if seq_time and seq_time > 0 and r.name not in ("Full (sequential)", "Full (parallel)"):
            pct = f"{r.total_seconds / seq_time * 100:.1f}%"

        profile_link = ""
        if r.profile_html and r.profile_filename:
            profile_link = f"<a href='{r.profile_filename}'>view</a>"

        rows.append(
            f"<tr>"
            f"<td>{html_escape(r.name)}</td>"
            f"<td data-value='{r.total_seconds:.6f}'>{_fmt_time(r.total_seconds)}</td>"
            f"<td data-value='{r.per_card_seconds:.6f}'>{_fmt_time(r.per_card_seconds)}</td>"
            f"<td>{_fmt_throughput(r.card_count, r.total_seconds)}</td>"
            f"<td>{pct}</td>"
            f"<td>{profile_link}</td>"
            f"</tr>"
        )

    table_html = (
        "<table class='filterable-table'>\n"
        "<thead><tr>"
        f"{sortable_th('Stage')}"
        f"{sortable_th('Total Time', is_num=True)}"
        f"{sortable_th('Per Card', is_num=True)}"
        f"{sortable_th('Throughput', is_num=True)}"
        f"{sortable_th('% of Sequential', is_num=True)}"
        "<th>Profile</th>"
        "</tr></thead>\n"
        "<tbody>\n" + "\n".join(rows) + "\n</tbody></table>"
    )

    # Parallelism section
    parallel_html = ""
    par_result = next((r for r in results if r.name == "Full (parallel)"), None)
    if seq_result and par_result:
        speedup = par_result.extra.get("speedup", 0)
        workers = par_result.extra.get("workers", "?")
        parallel_html = (
            "<h2>Parallelism</h2>"
            "<table>"
            "<tr><th>Metric</th><th>Value</th></tr>"
            f"<tr><td>Sequential time</td><td>{_fmt_time(seq_result.total_seconds)}</td></tr>"
            f"<tr><td>Parallel time</td><td>{_fmt_time(par_result.total_seconds)}</td></tr>"
            f"<tr><td>Speedup</td><td>{speedup:.1f}x</td></tr>"
            f"<tr><td>Workers</td><td>{workers}</td></tr>"
            f"<tr><td>Efficiency</td><td>{speedup / int(workers) * 100:.0f}%</td></tr>"
            "</table>"
        )

    body = (
        "<h1>Profiling Report</h1>\n"
        f"<p class='meta'>{meta_html}</p>\n"
        "<h2>Timing Summary</h2>\n"
        f"{table_html}\n"
        f"{parallel_html}\n"
    )

    extra_css = """
    .meta { color: #888; font-size: 0.9em; margin-bottom: 1.5em; }
    .meta span { white-space: nowrap; }
    """

    html = html_page("Profiling Report", body, extra_css=extra_css)
    report_path = output_dir / "index.html"
    report_path.write_text(html)
    return report_path
