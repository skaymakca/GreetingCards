# Coverage: excluded (runtime profiler, instruments live app) — see [tool.coverage.run] omit in pyproject.toml
"""HTML report generation and data export for profiling results."""

from __future__ import annotations

import json
import multiprocessing
import platform
import socket
import subprocess
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


def _macos_version() -> str:
    """Get macOS marketing version (e.g. '15.4.1') or fall back to platform.release()."""
    try:
        result = subprocess.run(["sw_vers", "-productVersion"], capture_output=True, text=True, check=True)
        return f"macOS {result.stdout.strip()}"
    except OSError, subprocess.CalledProcessError:
        return f"{platform.system()} {platform.release()}"


def _ram_gb() -> float:
    """Get total physical RAM in GB via sysctl (macOS)."""
    try:
        result = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, check=True)
        return int(result.stdout.strip()) / (1024**3)
    except OSError, subprocess.CalledProcessError, ValueError:
        return 0


def _git_short_hash() -> str:
    """Get the current git short hash, or 'unknown' if not in a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _system_info(corpus_path: Path, pdf_count: int, invocation: str) -> dict:
    """Collect system information for reports."""
    now = datetime.now()
    info = {
        "date": now.isoformat(timespec="seconds"),
        "date_display": now.strftime("%Y-%m-%d %H:%M"),
        "git_hash": _git_short_hash(),
        "python": sys.version.split()[0],
        "platform": platform.machine(),
        "os": _macos_version(),
        "hostname": socket.gethostname(),
        "cpu_cores": multiprocessing.cpu_count(),
        "ram_gb": round(_ram_gb()),
        "corpus": str(corpus_path),
        "pdf_count": pdf_count,
        "invocation": invocation,
    }
    return info


# ---------------------------------------------------------------------------
# Data export
# ---------------------------------------------------------------------------

# Stages that represent individual pipeline components (not full-pipeline runs).
_FULL_STAGES = {"Full (sequential)", "Full (parallel)", "AI analysis"}


def _component_sum(results: list[StageResult]) -> float:
    """Sum of individual component stage times (excludes full-pipeline and AI stages)."""
    return sum(r.total_seconds for r in results if r.name not in _FULL_STAGES)


def _write_summary_json(sys_info: dict, results: list[StageResult], output_dir: Path) -> Path:
    """Write data/summary.json with full structured results."""
    seq_result = next((r for r in results if r.name == "Full (sequential)"), None)
    par_result = next((r for r in results if r.name == "Full (parallel)"), None)
    stage_sum = _component_sum(results)

    stages = []
    for r in results:
        throughput = r.card_count / r.total_seconds if r.total_seconds > 0 else 0
        pct = r.total_seconds / stage_sum * 100 if stage_sum > 0 and r.name not in _FULL_STAGES else None
        stage = {
            "name": r.name,
            "total_seconds": round(r.total_seconds, 6),
            "per_card_seconds": round(r.per_card_seconds, 6),
            "card_count": r.card_count,
            "throughput": round(throughput, 1),
            "pct_of_total": round(pct, 1) if pct is not None else None,
            "profile_file": f"profiles/{r.profile_filename}" if r.profile_filename else None,
        }
        if r.extra:
            stage["extra"] = r.extra  # type: ignore[assignment]
        stages.append(stage)

    data: dict = {
        "system": sys_info,
        "stages": stages,
    }

    if seq_result and par_result:
        speedup = par_result.extra.get("speedup", 0)
        workers = par_result.extra.get("workers", 0)
        data["parallelism"] = {
            "sequential_seconds": round(seq_result.total_seconds, 6),
            "parallel_seconds": round(par_result.total_seconds, 6),
            "speedup": round(speedup, 2),
            "workers": workers,
            "efficiency": round(speedup / workers, 3) if workers else 0,
        }

    path = output_dir / "data" / "summary.json"
    path.write_text(json.dumps(data, indent=2) + "\n")
    return path


def _write_summary_tsv(results: list[StageResult], output_dir: Path) -> Path:
    """Write data/summary.tsv with timing data."""
    stage_sum = _component_sum(results)

    lines = ["Stage\tTotal (s)\tPer Card (s)\tThroughput (/s)\t% of Total"]
    for r in results:
        throughput = r.card_count / r.total_seconds if r.total_seconds > 0 else 0
        pct = r.total_seconds / stage_sum * 100 if stage_sum > 0 and r.name not in _FULL_STAGES else None
        pct_str = f"{pct:.1f}" if pct is not None else ""
        lines.append(f"{r.name}\t{r.total_seconds:.6f}\t{r.per_card_seconds:.6f}\t{throughput:.1f}\t{pct_str}")

    path = output_dir / "data" / "summary.tsv"
    path.write_text("\n".join(lines) + "\n")
    return path


def _write_invocation(sys_info: dict, output_dir: Path) -> Path:
    """Write data/invocation.txt with full context."""
    lines = [
        f"Command: {sys_info['invocation']}",
        f"Date: {sys_info['date_display']}",
        f"Git: {sys_info['git_hash']}",
        f"Hostname: {sys_info['hostname']}",
        f"Python: {sys_info['python']}",
        f"Platform: {sys_info['platform']} ({sys_info['os']})",
        f"CPU cores: {sys_info['cpu_cores']}",
        f"RAM: {sys_info['ram_gb']} GB",
        f"Corpus: {sys_info['corpus']}",
        f"PDF count: {sys_info['pdf_count']}",
    ]
    path = output_dir / "data" / "invocation.txt"
    path.write_text("\n".join(lines) + "\n")
    return path


# ---------------------------------------------------------------------------
# HTML reports
# ---------------------------------------------------------------------------


def _generate_profiles_index(results: list[StageResult], output_dir: Path) -> Path:
    """Generate profiles/index.html listing all pyinstrument profile files."""
    rows = []
    for r in results:
        if r.profile_html and r.profile_filename:
            rows.append(
                f"<tr>"
                f"<td><a href='{r.profile_filename}'>{html_escape(r.name)}</a></td>"
                f"<td data-value='{r.total_seconds:.6f}'>{_fmt_time(r.total_seconds)}</td>"
                f"<td>{_fmt_throughput(r.card_count, r.total_seconds)}</td>"
                f"</tr>"
            )

    table = (
        "<table>\n"
        "<thead><tr>"
        f"{sortable_th('Stage')}"
        f"{sortable_th('Total Time', is_num=True)}"
        f"{sortable_th('Throughput', is_num=True)}"
        "</tr></thead>\n"
        "<tbody>\n" + "\n".join(rows) + "\n</tbody></table>"
    )

    body = f"<h1>pyinstrument Profiles</h1>\n<p><a href='../index.html'>\u2190 Back to summary</a></p>\n{table}\n"

    html = html_page("Profiles — Profiling Report", body)
    path = output_dir / "profiles" / "index.html"
    path.write_text(html)
    return path


def generate_report(
    results: list[StageResult],
    corpus_path: Path,
    pdf_count: int,
    output_dir: Path,
    invocation: str,
) -> Path:
    """Generate all reports and data files. Returns path to root index.html."""
    sys_info = _system_info(corpus_path, pdf_count, invocation)

    # Data exports
    _write_summary_json(sys_info, results, output_dir)
    _write_summary_tsv(results, output_dir)
    _write_invocation(sys_info, output_dir)

    # Profiles index
    _generate_profiles_index(results, output_dir)

    # Root index.html
    # Invocation info block
    info_rows = [
        f"<tr><td>Command</td><td><code>{html_escape(sys_info['invocation'])}</code></td></tr>",
        f"<tr><td>Date</td><td>{sys_info['date_display']}</td></tr>",
        f"<tr><td>Git</td><td><code>{html_escape(sys_info['git_hash'])}</code></td></tr>",
        f"<tr><td>Hostname</td><td>{html_escape(sys_info['hostname'])}</td></tr>",
        f"<tr><td>Python</td><td>{sys_info['python']}</td></tr>",
        f"<tr><td>Platform</td><td>{sys_info['platform']} ({html_escape(sys_info['os'])})</td></tr>",
        f"<tr><td>CPU cores</td><td>{sys_info['cpu_cores']}</td></tr>",
        f"<tr><td>RAM</td><td>{sys_info['ram_gb']} GB</td></tr>",
        f"<tr><td>Corpus</td><td>{html_escape(sys_info['corpus'])}</td></tr>",
        f"<tr><td>PDFs</td><td>{pdf_count}</td></tr>",
    ]
    info_html = "<table class='info-table'>\n" + "\n".join(info_rows) + "\n</table>"

    # Timing summary table
    seq_result = next((r for r in results if r.name == "Full (sequential)"), None)
    stage_sum = _component_sum(results)

    rows: list[str] = []
    for i, r in enumerate(results, 1):
        pct = ""
        if stage_sum > 0 and r.name not in _FULL_STAGES:
            pct = f"{r.total_seconds / stage_sum * 100:.1f}%"

        profile_link = ""
        if r.profile_html and r.profile_filename:
            profile_link = f"<a href='profiles/{r.profile_filename}'>view</a>"

        rows.append(
            f"<tr>"
            f"<td data-value='{i}'>{i}</td>"
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
        f"{sortable_th('#', is_num=True)}"
        f"{sortable_th('Stage')}"
        f"{sortable_th('Total Time', is_num=True)}"
        f"{sortable_th('Per Card', is_num=True)}"
        f"{sortable_th('Throughput', is_num=True)}"
        f"{sortable_th('% of Total', is_num=True)}"
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

    # Pipeline overview diagram
    pipeline_html = (
        "<h2>Pipeline Overview</h2>"
        "<pre class='pipeline-diagram'>"
        "Individual stages (each measured independently):\n"
        "\n"
        "  PDF file\n"
        "    │\n"
        "    ├─ 1. Hash ──────── SHA-256 file hash\n"
        "    ├─ 2. Database ──── save + reprocess + query\n"
        "    ├─ 3. Render ────── PDF → images (PyMuPDF)\n"
        "    ├─ 4. OCR ───────── images → text (Tesseract)\n"
        "    ├─ 5. Names ─────── text → family names (regex/dictionary)\n"
        "    └─ 6. AI (mock) ─── simulated 100ms API latency (async, concurrency=3)\n"
        "\n"
        "Full pipeline (uses fresh DB, independent of individual stage measurements):\n"
        "\n"
        "  7. Sequential ─── process_pdf_worker() per PDF, one at a time\n"
        "  8. Parallel ───── same worker, ProcessPoolExecutor across all CPU cores"
        "</pre>"
    )

    # Links to data files
    data_links = (
        "<h2>Data Files</h2>"
        "<ul>"
        "<li><a href='profiles/index.html'>All pyinstrument profiles</a></li>"
        "<li><a href='data/summary.json'>summary.json</a> — machine-readable results</li>"
        "<li><a href='data/summary.tsv'>summary.tsv</a> — spreadsheet-friendly timing data</li>"
        "<li><a href='data/invocation.txt'>invocation.txt</a> — run context</li>"
        "</ul>"
    )

    body = (
        "<h1>Profiling Report</h1>\n"
        f"{info_html}\n"
        f"{pipeline_html}\n"
        "<h2>Timing Summary</h2>\n"
        f"{table_html}\n"
        f"{parallel_html}\n"
        f"{data_links}\n"
    )

    extra_css = """
    .info-table { width: auto; margin-bottom: 1.5em; }
    .info-table td:first-child { font-weight: bold; color: #888; padding-right: 1.5em; }
    .info-table code { font-family: var(--mono); font-size: 0.85em; }
    .pipeline-diagram {
        font-family: var(--mono);
        font-size: 0.82rem;
        line-height: 1.5;
        background: var(--bg-alt);
        border: 1px solid var(--border);
        border-radius: 6px;
        padding: 1em 1.5em;
        overflow-x: auto;
        margin-bottom: 1.5em;
    }
    """

    html = html_page("Profiling Report", body, extra_css=extra_css)
    report_path = output_dir / "index.html"
    report_path.write_text(html)
    return report_path
