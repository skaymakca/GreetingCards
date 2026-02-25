#!/usr/bin/env python3
"""OCR Configuration Quality Benchmark.

Systematically tests Tesseract OCR configurations on a corpus of greeting card
PDFs and produces a self-contained HTML report comparing every configuration's
results side-by-side with card images.

Overview
--------
Greeting cards contain a mix of decorative text, handwriting-style fonts,
names, and holiday messages that are notoriously difficult for OCR.  This
benchmark exhaustively explores the Tesseract configuration space to find the
best settings for this domain.

The test matrix is a cartesian product of six axes:

    Library        pytesseract, tesserocr
    Tessdata       default (system), tessdata_best (downloaded automatically)
    DPI            200, 300
    PSM            3 (auto), 6 (single block), 11 (sparse text)
    Preprocess     pillow, clahe, otsu, sauvola
    Dict penalty   0.0, 0.15

This produces 192 configurations.  Each is run against every PDF in the
corpus, yielding one OCR result per (card × config) pair.

AI Scoring (optional)
---------------------
AI scoring is enabled by default.  The benchmark sends OCR results to a Claude
model for quality evaluation.  This supplements Tesseract's self-reported
confidence (which only measures the engine's certainty, not actual text quality)
with an LLM judgment of how well the extracted text reads as a greeting card.

Scoring uses a two-pass design:

  Pass 1 — Triage:  OCR texts for each card are split into chunks of 48 and
  sent to the LLM as separate API calls.  The LLM returns a JSON object keyed
  by config number (``{"1": score, "2": score, ...}``), which prevents the
  count-mismatch errors that flat arrays are prone to with large batches.
  Cards where ALL configs score below ``--dud-threshold`` (default 15) are
  classified as "duds" — image-heavy cards with no extractable text.  Duds are
  excluded from pass 2.

  Pass 2 — Refined:  Non-dud cards are re-scored with a detailed prompt that
  emphasizes names (most important), readability, structure, completeness, and
  noise.  Pass 2 scores replace pass 1 scores for these cards.

Each chunk is retried up to 4 times.  Scores are accumulated across retries:
if one attempt drops a key, the next attempt (at a slightly higher temperature)
may return it, filling the gap.  After all retries, any still-missing configs
are assigned a score of -1, which is excluded from aggregate statistics and
shown as "n/a" in the report.

Because the OCR texts are very short (avg ~28 tokens), all 192 texts for one
card fit comfortably in 4 API calls (~5K input tokens each).  With the default
concurrency of 5, scoring completes in under a minute for a typical 41-card
corpus.  Estimated cost: ~$0.11 with Sonnet (default), ~$0.04 with Haiku.

Output
------
The benchmark writes several outputs to the output directory:

  index.html         Summary page with configuration ranking table, sortable
                     and filterable by every axis.  Heatmap coloring highlights
                     quartile performance for confidence, AI score, and time.

  cards/<id>.html    Per-card detail pages showing all config results alongside
                     card thumbnails, sorted by AI score (or confidence).

  configs/<slug>.html  Per-config detail pages showing results across all cards.

  summary.csv        One row per config with aggregate statistics (mean/std for
                     confidence, words, unique words, AI score; total time).

  detail.csv         One row per (card × config) run with individual metrics.

When ``--no-ai-score`` is passed, the AI Score column is omitted entirely from
all outputs — the report is identical to the non-AI version.

Dependencies
------------
Always available:
    Pillow, PyMuPDF, anthropic

May need installing (``uv add --dev <package>``):
    pytesseract              Python wrapper for the Tesseract CLI.
    tesserocr                Alternative OCR library wrapping the Tesseract C++ API.
    opencv-python-headless   Enables clahe and otsu preprocessing pipelines.

    Which of these are already installed depends on the main app's current
    OCR library choice.  If any are missing, configs using those features
    are automatically skipped.

Usage
-----
Basic benchmark (AI scoring enabled by default):

    uv run python -m scripts.benchmark.ocr_configuration_quality ~/Desktop/cards

Without AI scoring:

    uv run python -m scripts.benchmark.ocr_configuration_quality ~/Desktop/cards --no-ai-score

Config filter:

    uv run python -m scripts.benchmark.ocr_configuration_quality ~/Desktop/cards \\
        --configs pytesseract/default/200/6/pillow/0.15

AI scoring with Haiku for lower cost:

    uv run python -m scripts.benchmark.ocr_configuration_quality ~/Desktop/cards \\
        --ai-model claude-haiku-4-5

Open the report:

    open _build/script_output/YYYYMMDD_HHMM-benchmark_ocr_configuration_quality/index.html

Environment Variables
---------------------
ANTHROPIC_API_KEY   Required for AI scoring (enabled by default).  The API key for
                    Claude model access.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import itertools
import json
import multiprocessing as mp
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import anthropic

from rich.console import Console
from rich.markup import escape as rich_escape
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)

from scripts.benchmark.common import (
    CSS,
    HAS_OPENCV,
    HAS_PYTESSERACT,
    HAS_TESSEROCR,
    OCR_FNS,
    REPORT_JS,
    Config,
    _detect_system_tessdata,
    ensure_tessdata_best,
    find_pdfs,
    fmt_mean_std,
    html_escape,
    image_to_base64,
    image_to_png_bytes,
    mean_std,
    png_bytes_to_image,
    preprocess_clahe,
    preprocess_otsu,
    preprocess_pillow,
    quartile_class,
    render_all_pages,
    sortable_th,
)

console = Console(stderr=True, highlight=False)

_HAS_PYTESSERACT = HAS_PYTESSERACT
_HAS_TESSEROCR = HAS_TESSEROCR
_HAS_OPENCV = HAS_OPENCV

OCR_LIBRARIES = ["pytesseract", "tesserocr"]
TESSDATA_OPTIONS = ["default", "tessdata_best"]
DPI_OPTIONS = [200, 300]
PSM_OPTIONS = [3, 6, 11]
PREPROCESS_OPTIONS = ["pillow", "clahe", "sauvola", "otsu"]
DICT_PENALTY_OPTIONS = [0.15, 0.0]


@dataclass
class OCRResult:
    config: Config
    text: str
    word_count: int
    unique_words: int
    confidence: float  # -1 if unavailable
    elapsed_s: float
    ai_score: float = -1.0  # -1 if unscored, 0-100 from LLM scoring


@dataclass
class CardResult:
    card_id: str
    pdf_path: Path
    page_images_b64: list[str] = field(default_factory=list)
    results: list[OCRResult] = field(default_factory=list)


def build_configs(filter_str: str | None = None) -> list[Config]:
    """Build the cartesian product of all config axes, optionally filtered."""
    all_configs = [
        Config(lib, td, dpi, psm, pp, dp)
        for lib, td, dpi, psm, pp, dp in itertools.product(
            OCR_LIBRARIES,
            TESSDATA_OPTIONS,
            DPI_OPTIONS,
            PSM_OPTIONS,
            PREPROCESS_OPTIONS,
            DICT_PENALTY_OPTIONS,
        )
    ]
    if not filter_str:
        return all_configs

    # Filter: "pytesseract/default/200/6/pillow/0.15" or partial like "pytesseract"
    filtered = []
    for pattern in filter_str.split(","):
        parts = pattern.strip().split("/")
        for cfg in all_configs:
            cfg_parts = [
                cfg.library,
                cfg.tessdata,
                str(cfg.dpi),
                str(cfg.psm),
                cfg.preprocess,
                str(cfg.dict_penalty),
            ]
            if all(p == c for p, c in zip(parts, cfg_parts, strict=False)) and cfg not in filtered:
                filtered.append(cfg)
    return filtered


# Sauvola uses identical preprocessing to pillow — the difference is a Tesseract
# config flag, not a preprocessing step.  Keep all 4 entries here because the
# quality benchmark needs to distinguish them at the Tesseract level.
PREPROCESS_FNS = {
    "pillow": preprocess_pillow,
    "clahe": preprocess_clahe,
    "otsu": preprocess_otsu,
    "sauvola": preprocess_pillow,  # same preprocessing; Tesseract flag differs
}


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

# Sentinel value to tell workers to exit
_SENTINEL = None


_image_to_png_bytes = image_to_png_bytes
_png_bytes_to_image = png_bytes_to_image


def _cfg_to_dict(cfg: Config) -> dict:
    """Convert a Config to a plain dict for pickling through multiprocessing queues."""
    return {
        "library": cfg.library,
        "tessdata": cfg.tessdata,
        "dpi": cfg.dpi,
        "psm": cfg.psm,
        "preprocess": cfg.preprocess,
        "dict_penalty": cfg.dict_penalty,
    }


# noinspection DuplicatedCode
def _worker(job_queue: mp.Queue, result_queue: mp.Queue) -> None:
    """Worker process: pull jobs from queue, run OCR, push results.

    Job format: (card_id, config_dict, list[png_bytes])
    Result format: (card_id, config_dict, text, word_count, unique_words, confidence, elapsed_s)

    Config is passed as a dict (not a dataclass) for pickling simplicity.
    """
    while True:
        job = job_queue.get()
        if job is _SENTINEL:
            break

        card_id, cfg_dict, page_png_list = job
        cfg = Config(**cfg_dict)

        preprocess_fn = PREPROCESS_FNS[cfg.preprocess]
        ocr_fn = OCR_FNS[cfg.library]

        all_text_parts = []
        all_confidences = []
        t0 = time.monotonic()

        for png_bytes in page_png_list:
            page_img = _png_bytes_to_image(png_bytes)
            processed = preprocess_fn(page_img)
            try:
                text, conf = ocr_fn(processed, cfg)
            except Exception as exc:
                err = exc
                text, conf = f"[ERROR: {err}]", -1.0
            all_text_parts.append(text)
            if conf >= 0:
                all_confidences.append(conf)

        elapsed = time.monotonic() - t0
        combined_text = "\n\n".join(all_text_parts)
        words = combined_text.split()

        result_queue.put(
            (
                card_id,
                cfg_dict,
                combined_text,
                len(words),
                len({w.lower() for w in words}),
                sum(all_confidences) / len(all_confidences) if all_confidences else -1.0,
                elapsed,
            )
        )


def _filter_configs(configs: list[Config]) -> list[Config]:
    """Remove configs whose libraries/preprocessing aren't available."""
    available_libs = set()
    if _HAS_PYTESSERACT:
        available_libs.add("pytesseract")
    if _HAS_TESSEROCR:
        available_libs.add("tesserocr")

    needed_libs = {c.library for c in configs}
    missing = needed_libs - available_libs
    if missing:
        console.print(f"[yellow]Warning: skipping configs for unavailable libraries: {missing}[/]")
        configs = [c for c in configs if c.library in available_libs]

    if not _HAS_OPENCV:
        opencv_preprocs = {"clahe", "otsu"}
        needed_opencv = {c.preprocess for c in configs} & opencv_preprocs
        if needed_opencv:
            console.print(
                f"[yellow]Warning: skipping configs with {needed_opencv} preprocessing (OpenCV not installed)[/]"
            )
            configs = [c for c in configs if c.preprocess not in opencv_preprocs]

    return configs


def _validate_configs(
    configs: list[Config],
    first_pdf: Path,
    page_cache: dict[tuple[str, int], list[bytes]],
) -> list[Config]:
    """Run all configs on the first card and exclude any that fail."""
    valid = []
    failed = []
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task(
            f"Validating configs on {first_pdf.stem}",
            total=len(configs),
        )
        for cfg in configs:
            page_data = page_cache[(str(first_pdf), cfg.dpi)]
            preprocess_fn = PREPROCESS_FNS[cfg.preprocess]
            ocr_fn = OCR_FNS[cfg.library]
            try:
                any_conf = False
                for png_bytes in page_data:
                    page_img = _png_bytes_to_image(png_bytes)
                    processed = preprocess_fn(page_img)
                    text, conf = ocr_fn(processed, cfg)
                    if text.startswith("[ERROR:"):
                        raise RuntimeError(text)
                    if conf >= 0:
                        any_conf = True
                if not any_conf:
                    raise RuntimeError("all pages returned confidence -1 (OCR likely failed silently)")
                valid.append(cfg)
            except Exception as exc:
                err = exc
                failed.append((cfg, str(err)))
            progress.advance(task)

    if failed:
        console.print(f"  [yellow]{len(failed)} configs failed validation:[/]")
        for cfg, err_msg in failed:
            console.print(f"    {cfg.name}: {err_msg}")
    console.print(f"  {len(valid)} configs passed validation")
    return valid


# noinspection PyUnusedLocal,DuplicatedCode
def run_benchmark(corpus_path: Path, configs: list[Config], output_dir: Path, num_workers: int = 1) -> list[CardResult]:
    pdfs = find_pdfs(corpus_path)
    if not pdfs:
        console.print(f"[red]No PDF files found in {corpus_path}[/]")
        sys.exit(1)

    configs = _filter_configs(configs)
    if not configs:
        console.print("[red]No valid configs to run![/]")
        sys.exit(1)

    # Set TESSDATA_PREFIX for worker processes
    system_tessdata = _detect_system_tessdata()
    if system_tessdata:
        os.environ["TESSDATA_PREFIX"] = system_tessdata

    total_runs = len(pdfs) * len(configs)
    console.print(f"Found {len(pdfs)} PDFs, {len(configs)} configs = {total_runs} OCR runs")
    console.print(f"Workers: {num_workers}")

    # Pre-download tessdata_best if needed
    if any(c.tessdata == "tessdata_best" for c in configs):
        ensure_tessdata_best()

    dpi_levels = sorted({c.dpi for c in configs})

    # --- Pre-render all pages (main process) ---
    # page_cache: (pdf_path_str, dpi) -> list[png_bytes]
    page_cache: dict[tuple[str, int], list[bytes]] = {}
    # thumbnails: pdf_path_str -> list[base64_str]
    thumbnails: dict[str, list[str]] = {}

    render_total = len(pdfs) * len(dpi_levels)
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=True,
    ) as progress:
        render_task = progress.add_task("Rendering pages", total=render_total)
        for pdf_path in pdfs:
            for dpi in dpi_levels:
                key = (str(pdf_path), dpi)
                images = render_all_pages(pdf_path, dpi)
                page_cache[key] = [_image_to_png_bytes(img) for img in images]
                progress.advance(render_task)
            # Thumbnails from highest DPI
            best_dpi = max(dpi_levels)
            best_images = [_png_bytes_to_image(b) for b in page_cache[(str(pdf_path), best_dpi)]]
            thumbnails[str(pdf_path)] = [image_to_base64(img) for img in best_images]

    console.print(f"  Rendered {len(pdfs)} cards at {len(dpi_levels)} DPI levels")

    # --- Validation pass ---
    configs = _validate_configs(configs, pdfs[0], page_cache)
    if not configs:
        console.print("[red]No configs passed validation![/]")
        sys.exit(1)

    # Recalculate total after validation may have excluded configs
    total_runs = len(pdfs) * len(configs)

    # --- Build jobs ---
    jobs: list[tuple[str, dict, list[bytes]]] = []
    for pdf_path in pdfs:
        card_id = pdf_path.stem
        for cfg in configs:
            page_data = page_cache[(str(pdf_path), cfg.dpi)]
            jobs.append((card_id, _cfg_to_dict(cfg), page_data))

    # Compute fixed-width description label so the progress bar doesn't jump.
    # The progress line looks like: "{label}  ━━━━━━━━━━  123/456  0:12"
    # We cap the total line at 200 chars; the bar/counter/time take ~40 chars.
    _MAX_LINE = 200
    _BAR_OVERHEAD = 40
    max_label_len = max(len(f"{card_id} / {Config(**cfg_dict).short_name}") for card_id, cfg_dict, _ in jobs)
    max_desc_len = min(max_label_len, _MAX_LINE - _BAR_OVERHEAD - len("Running OCR — "))

    # noinspection PyShadowingNames
    def _ocr_desc(card_id: str, cfg: Config) -> str:
        label = f"{card_id} / {cfg.short_name}"
        if len(label) > max_desc_len:
            label = label[: max_desc_len - 3] + "..."
        return f"Running OCR — {label:<{max_desc_len}}"

    if num_workers <= 1:
        # --- Sequential mode ---
        card_map: dict[str, CardResult] = {}

        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console,
            transient=True,
        ) as progress:
            ocr_task = progress.add_task("Running OCR", total=total_runs)
            for card_id, cfg_dict, page_png_list in jobs:
                cfg = Config(**cfg_dict)
                progress.update(ocr_task, description=_ocr_desc(card_id, cfg))

                preprocess_fn = PREPROCESS_FNS[cfg.preprocess]
                ocr_fn = OCR_FNS[cfg.library]
                all_text_parts = []
                all_confidences = []
                t0 = time.monotonic()

                for png_bytes in page_png_list:
                    page_img = _png_bytes_to_image(png_bytes)
                    processed = preprocess_fn(page_img)
                    try:
                        text, conf = ocr_fn(processed, cfg)
                    except Exception as exc:
                        err = exc
                        text, conf = f"[ERROR: {err}]", -1.0
                    all_text_parts.append(text)
                    if conf >= 0:
                        all_confidences.append(conf)

                elapsed = time.monotonic() - t0
                combined_text = "\n\n".join(all_text_parts)
                words = combined_text.split()

                if card_id not in card_map:
                    pdf_path = next(p for p in pdfs if p.stem == card_id)
                    card_map[card_id] = CardResult(
                        card_id=card_id,
                        pdf_path=pdf_path,
                        page_images_b64=thumbnails[str(pdf_path)],
                    )
                card_map[card_id].results.append(
                    OCRResult(
                        config=cfg,
                        text=combined_text,
                        word_count=len(words),
                        unique_words=len({w.lower() for w in words}),
                        confidence=sum(all_confidences) / len(all_confidences) if all_confidences else -1.0,
                        elapsed_s=elapsed,
                    )
                )
                progress.advance(ocr_task)

        return [card_map[p.stem] for p in pdfs]

    # --- Parallel mode ---
    console.print(f"Queuing {total_runs} jobs across {num_workers} workers...")
    job_queue: mp.Queue = mp.Queue()
    result_queue: mp.Queue = mp.Queue()

    # Spawn workers
    workers = []
    for _ in range(num_workers):
        p = mp.Process(target=_worker, args=(job_queue, result_queue))
        p.start()
        workers.append(p)

    # Enqueue all jobs
    for job in jobs:
        job_queue.put(job)

    # Send sentinel for each worker
    for _ in range(num_workers):
        job_queue.put(_SENTINEL)

    # Collect results with progress
    card_map = {}  # type: ignore[no-redef]  # sequential branch returns early

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=True,
    ) as progress:
        ocr_task = progress.add_task("Running OCR", total=total_runs)
        for _i in range(total_runs):
            card_id, cfg_dict, text, word_count, unique_words, confidence, elapsed = result_queue.get()
            cfg = Config(**cfg_dict)

            progress.update(ocr_task, description=_ocr_desc(card_id, cfg))

            if card_id not in card_map:
                pdf_path = next(p for p in pdfs if p.stem == card_id)
                card_map[card_id] = CardResult(
                    card_id=card_id,
                    pdf_path=pdf_path,
                    page_images_b64=thumbnails[str(pdf_path)],
                )

            card_map[card_id].results.append(
                OCRResult(
                    config=cfg,
                    text=text,
                    word_count=word_count,
                    unique_words=unique_words,
                    confidence=confidence,
                    elapsed_s=elapsed,
                )
            )
            progress.advance(ocr_task)

    # Wait for workers to finish
    for p in workers:
        p.join()

    # Return in original PDF order
    return [card_map[p.stem] for p in pdfs]


# ---------------------------------------------------------------------------
# Statistics helpers
# ---------------------------------------------------------------------------


_mean_std = mean_std
_fmt_mean_std = fmt_mean_std


def _compute_config_stats(card_results: list[CardResult], configs: list[Config]) -> dict[str, dict]:
    """Compute per-config aggregate statistics across all cards.

    Returns a dict keyed by config name with stats fields:
    config, word_counts, unique_counts, confidences, ai_scores, total_time,
    words_mean, words_std, unique_mean, unique_std, conf_mean, conf_std,
    ai_score_mean, ai_score_std.
    """
    config_data: dict[str, dict] = {}
    for cfg in configs:
        data: dict = {
            "config": cfg,
            "word_counts": [],
            "unique_counts": [],
            "confidences": [],
            "ai_scores": [],
            "total_time": 0.0,
        }
        for card in card_results:
            for r in card.results:
                if r.config.name == cfg.name:
                    data["word_counts"].append(float(r.word_count))
                    data["unique_counts"].append(float(r.unique_words))
                    if r.confidence >= 0:
                        data["confidences"].append(r.confidence)
                    if r.ai_score >= 0:
                        data["ai_scores"].append(r.ai_score)
                    data["total_time"] += r.elapsed_s
        data["words_mean"], data["words_std"] = _mean_std(data["word_counts"])
        data["unique_mean"], data["unique_std"] = _mean_std(data["unique_counts"])
        data["conf_mean"], data["conf_std"] = _mean_std(data["confidences"])
        data["ai_score_mean"], data["ai_score_std"] = _mean_std(data["ai_scores"])
        config_data[cfg.name] = data
    return config_data


# ---------------------------------------------------------------------------
# AI scoring
# ---------------------------------------------------------------------------


def _build_scoring_prompt(texts: list[str], pass_num: int) -> tuple[str, str]:
    """Build system prompt and user message for scoring a card.

    Returns (system_prompt, user_message).
    """
    n = len(texts)

    if pass_num == 1:
        system = (
            "You score OCR-extracted text from greeting cards. "
            "You ALWAYS respond with ONLY a JSON object mapping config number to score — no explanation, no commentary, no markdown. "
            f'The object must have exactly {n} keys ("1" through "{n}"), each value an integer 0-100.'
        )
        user = (
            f"Below are {n} text extractions from the same card using different OCR configurations.\n"
            "Score each text 0-100 based on how much readable greeting card content it contains.\n"
            "- 0: empty, pure gibberish, or completely unreadable\n"
            "- 1-30: mostly noise with a few recognizable words\n"
            "- 31-60: partially readable, some greeting card content visible\n"
            "- 61-80: mostly readable greeting card text\n"
            "- 81-100: clear, well-structured greeting card text\n\n"
            f'Reply with ONLY a JSON object {{"1": score, "2": score, ..., "{n}": score}}. No other text.\n\n'
        )
    else:
        system = (
            "You score OCR-extracted text from greeting cards. "
            "You ALWAYS respond with ONLY a JSON object mapping config number to score — no explanation, no commentary, no markdown. "
            f'The object must have exactly {n} keys ("1" through "{n}"), each value an integer 0-100.'
        )
        user = (
            f"Below are {n} text extractions from the same card using different OCR configurations.\n"
            "Score each text 0-100 based on overall quality as extracted greeting card text.\n\n"
            "Scoring criteria (most to least important):\n"
            '1. Names: People\'s names, family names ("The Smiths", "Love, Jason and Amanda") — most valuable\n'
            "2. Readability: Coherent sentences about holidays, wishes, family updates\n"
            "3. Structure: Preserved line breaks and paragraphs vs flat wall of text\n"
            "4. Completeness: More captured content is better than less\n"
            "5. Noise: Penalize OCR artifacts, random symbols, fragmented words\n\n"
            f'Reply with ONLY a JSON object {{"1": score, "2": score, ..., "{n}": score}}. No other text.\n\n'
        )

    # Build text blocks
    blocks = []
    for i, text in enumerate(texts, 1):
        display = text.strip() if text.strip() else "[EMPTY]"
        blocks.append(f"--- Config {i} ---\n{display}")

    return system, user + "\n".join(blocks)


_MAX_SCORING_RETRIES = 4
_SCORING_BATCH_SIZE = 48


# noinspection PyTypeChecker
async def _score_chunk(
    client: anthropic.AsyncAnthropic,  # pyright: ignore[reportUndefinedVariable]
    card_id: str,
    texts: list[str],
    chunk_idx: int,
    pass_num: int,
    model: str,
    semaphore: asyncio.Semaphore,
) -> list[int]:
    """Score a single chunk of texts with retries.

    Uses raw JSON (not structured output) because the Anthropic SDK's
    structured output transforms ``dict[str, int]`` into a schema with
    ``additionalProperties: false``, which blocks dynamic keys entirely.

    Accumulates scores across retries using dict-keyed responses so that
    different attempts may fill in keys the others missed.  Always returns
    a list of scores (with -1 for any configs that could not be scored).
    """
    system_prompt, user_message = _build_scoring_prompt(texts, pass_num)
    expected_keys = {str(i) for i in range(1, len(texts) + 1)}
    accumulated: dict[str, int] = {}

    async with semaphore:
        for attempt in range(1, _MAX_SCORING_RETRIES + 1):
            if set(accumulated.keys()) >= expected_keys:
                break  # all keys collected

            temperature = 0 if attempt == 1 else 0.1
            try:
                response = await client.messages.create(
                    model=model,
                    max_tokens=4096,
                    temperature=temperature,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_message}],
                )
                raw_text = response.content[0].text if response.content and response.content[0].type == "text" else ""

                # Strip Markdown fences the model sometimes wraps around JSON
                stripped = raw_text.strip()
                if stripped.startswith("```"):
                    # Remove opening ```json or ``` and closing ```
                    lines = stripped.split("\n")
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    stripped = "\n".join(lines)

                if response.stop_reason == "max_tokens":
                    console.print(
                        f"[yellow]Warning: {card_id} chunk {chunk_idx} "
                        f"(pass {pass_num}, attempt {attempt}/{_MAX_SCORING_RETRIES}): "
                        f"response truncated (max_tokens), skipping[/]",
                    )
                    continue

                raw_scores: dict[str, int] = json.loads(stripped)

                if not isinstance(raw_scores, dict):
                    console.print(
                        f"[yellow]Warning: {card_id} chunk {chunk_idx} "
                        f"(pass {pass_num}, attempt {attempt}/{_MAX_SCORING_RETRIES}): "
                        f"expected JSON object, got {type(raw_scores).__name__}: {raw_text[:200]!r}[/]",
                    )
                    continue

                # Merge new keys into accumulated (don't overwrite existing)
                for key, value in raw_scores.items():
                    if key in expected_keys and key not in accumulated and isinstance(value, (int, float)):
                        accumulated[key] = max(0, min(100, int(value)))

                missing = expected_keys - set(accumulated.keys())
                if missing:
                    console.print(
                        f"[yellow]Warning: {card_id} chunk {chunk_idx} "
                        f"(pass {pass_num}, attempt {attempt}/{_MAX_SCORING_RETRIES}): "
                        f"missing keys {sorted(missing, key=int)} "
                        f"(got {len(raw_scores)}, accumulated {len(accumulated)}/{len(expected_keys)})[/]",
                    )

            except json.JSONDecodeError as exc:
                json_err = exc
                # raw_text is always defined before json.loads can raise
                raw_preview = raw_text[:300] if raw_text else "<empty>"  # pyright: ignore[reportPossiblyUnboundVariable]
                console.print(
                    f"[yellow]Warning: JSON parse error for {card_id} chunk {chunk_idx} "
                    f"(pass {pass_num}, attempt {attempt}/{_MAX_SCORING_RETRIES}): "
                    f"{json_err}\n    Raw text: {raw_preview!r}[/]",
                )
            except Exception as exc:
                err = exc
                console.print(
                    f"[yellow]Warning: API error for {card_id} chunk {chunk_idx} "
                    f"(pass {pass_num}, attempt {attempt}/{_MAX_SCORING_RETRIES}): "
                    f"{type(err).__name__}: {err}[/]",
                )

    # Fill missing keys with -1
    missing = expected_keys - set(accumulated.keys())
    if missing:
        console.print(
            f"[yellow]Warning: {card_id} chunk {chunk_idx} (pass {pass_num}): "
            f"filling {len(missing)} missing configs with -1: {sorted(missing, key=int)}[/]",
        )
        for key in missing:
            accumulated[key] = -1

    return [accumulated[str(i)] for i in range(1, len(texts) + 1)]


async def _score_card(
    client: anthropic.AsyncAnthropic,  # pyright: ignore[reportUndefinedVariable]
    card_id: str,
    texts: list[str],
    pass_num: int,
    model: str,
    semaphore: asyncio.Semaphore,
) -> tuple[str, list[int], float]:
    """Score one card's OCR texts, chunking into batches for reliability.

    Splits texts into chunks of _SCORING_BATCH_SIZE, scores each chunk
    independently with retries, then concatenates results.  Chunks always
    return scores (with -1 for unresolvable configs), so this never fails.

    Returns (card_id, scores, elapsed_seconds).
    """
    t0 = time.monotonic()

    # Split into chunks
    chunks = [texts[i : i + _SCORING_BATCH_SIZE] for i in range(0, len(texts), _SCORING_BATCH_SIZE)]

    # Score all chunks concurrently
    chunk_tasks = [
        _score_chunk(client, card_id, chunk, idx, pass_num, model, semaphore) for idx, chunk in enumerate(chunks)
    ]
    chunk_results = await asyncio.gather(*chunk_tasks)

    all_scores: list[int] = []
    for result in chunk_results:
        all_scores.extend(result)

    elapsed = time.monotonic() - t0
    return card_id, all_scores, elapsed


async def score_all_cards(
    card_results: list[CardResult],
    model: str,
    concurrency: int,
    dud_threshold: int,
) -> None:
    """Orchestrate two-pass AI scoring across all cards.

    Modifies OCRResult.ai_score in-place on each card's results.
    """
    import anthropic

    client = anthropic.AsyncAnthropic()
    semaphore = asyncio.Semaphore(concurrency)

    # Build ordered list of texts per card (preserving config order)
    # Each card has the same configs in the same order
    card_texts: dict[str, list[str]] = {}
    for card in card_results:
        card_texts[card.card_id] = [r.text for r in card.results]

    total_cards = len(card_results)

    # --- Pass 1: Triage ---
    console.print(f"\nAI Scoring — Pass 1 (triage): {total_cards} cards, model={rich_escape(model)}")

    tasks = [_score_card(client, card_id, texts, 1, model, semaphore) for card_id, texts in card_texts.items()]

    pass1_scores: dict[str, list[int]] = {}
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=True,
    ) as progress:
        p1_task = progress.add_task("AI Pass 1 (triage)", total=total_cards)
        for coro in asyncio.as_completed(tasks):
            card_id, scores, elapsed = await coro
            pass1_scores[card_id] = scores
            progress.update(
                p1_task,
                description=f"AI Pass 1 — {card_id} ({elapsed:.1f}s)",
            )
            progress.advance(p1_task)

    # Identify dud cards (all valid scores <= dud_threshold)
    dud_cards = set()
    for card_id, scores in pass1_scores.items():
        valid_scores = [s for s in scores if s >= 0]
        if not valid_scores or max(valid_scores) <= dud_threshold:
            dud_cards.add(card_id)

    non_dud_cards = [c for c in card_results if c.card_id not in dud_cards and c.card_id in pass1_scores]
    console.print(
        f"  Pass 1 complete: {len(dud_cards)} dud cards excluded, {len(non_dud_cards)} cards advancing to pass 2",
    )
    if dud_cards:
        console.print(f"  Dud cards: {', '.join(sorted(dud_cards))}")

    # Apply pass 1 scores to dud cards (they won't be re-scored)
    for card in card_results:
        if card.card_id in dud_cards and card.card_id in pass1_scores:
            scores = pass1_scores[card.card_id]
            for r, score in zip(card.results, scores, strict=False):
                r.ai_score = float(score)

    # --- Pass 2: Refined scoring for non-dud cards ---
    if non_dud_cards:
        console.print(f"\nAI Scoring — Pass 2 (refined): {len(non_dud_cards)} cards")

        tasks = [
            _score_card(client, card.card_id, card_texts[card.card_id], 2, model, semaphore) for card in non_dud_cards
        ]

        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console,
            transient=True,
        ) as progress:
            p2_task = progress.add_task("AI Pass 2 (refined)", total=len(non_dud_cards))
            for coro in asyncio.as_completed(tasks):
                card_id, scores, elapsed = await coro

                # Apply pass 2 scores
                for card in card_results:
                    if card.card_id == card_id:
                        for r, score in zip(card.results, scores, strict=False):
                            r.ai_score = float(score)
                        break

                progress.update(
                    p2_task,
                    description=f"AI Pass 2 — {card_id} ({elapsed:.1f}s)",
                )
                progress.advance(p2_task)

    # Report scoring results
    scored = sum(1 for c in card_results if any(r.ai_score >= 0 for r in c.results))
    console.print(f"  AI scoring complete: {scored}/{total_cards} cards scored")

    # Count configs with -1 (unscored) across all cards
    total_neg1 = sum(1 for c in card_results for r in c.results if r.ai_score < 0)
    if total_neg1:
        total_scores = sum(len(c.results) for c in card_results)
        console.print(
            f"  [yellow]Warning: {total_neg1}/{total_scores} config scores could not be resolved "
            f"(marked as -1, excluded from stats)[/]",
        )


# ---------------------------------------------------------------------------
# HTML report generation
# ---------------------------------------------------------------------------

_quartile_class = quartile_class
_html_escape = html_escape
_sortable_th = sortable_th


def _has_ai_scores(card_results: list[CardResult]) -> bool:
    """Check if any result has an AI score."""
    return any(r.ai_score >= 0 for card in card_results for r in card.results)


# noinspection DuplicatedCode
def generate_summary_html(
    card_results: list[CardResult],
    configs: list[Config],
    corpus_path: Path,
    elapsed_total: float,
    config_stats: dict[str, dict],
) -> str:
    """Generate the index.html summary page."""
    has_ai = _has_ai_scores(card_results)

    # Sort by AI score if available, otherwise by avg confidence
    if has_ai:
        ranked = sorted(config_stats.values(), key=lambda d: d["ai_score_mean"], reverse=True)
    else:
        ranked = sorted(config_stats.values(), key=lambda d: d["conf_mean"], reverse=True)

    # Quartile values for confidence and time
    conf_values = [d["conf_mean"] for d in ranked if d["confidences"]]
    time_values = [d["total_time"] for d in ranked]

    # Card list for links
    card_ids = [c.card_id for c in card_results]

    # Collect unique values for filter dropdowns
    axis_values = {
        "library": sorted({d["config"].library for d in ranked}),
        "tessdata": sorted({d["config"].tessdata for d in ranked}),
        "dpi": sorted({str(d["config"].dpi) for d in ranked}),
        "psm": sorted({str(d["config"].psm) for d in ranked}),
        "preprocess": sorted({d["config"].preprocess for d in ranked}),
        "penalty": sorted({str(d["config"].dict_penalty) for d in ranked}),
    }

    # Build HTML
    lines = [
        "<!DOCTYPE html>",
        "<html lang='en'>",
        "<head>",
        "<meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        "<title>OCR Configuration Quality Benchmark</title>",
        f"<style>{CSS}</style>",
        REPORT_JS,
        "</head>",
        "<body>",
        "<h1>OCR Configuration Quality Benchmark</h1>",
        "<div class='meta'>",
        f"  <span>Corpus: <code>{_html_escape(str(corpus_path))}</code></span>",
        f"  <span>Cards: {len(card_results)}</span>",
        f"  <span>Configs: {len(configs)}</span>",
        f"  <span>Total runs: {len(card_results) * len(configs)}</span>",
        f"  <span>Total time: {elapsed_total:.1f}s</span>",
        "</div>",
    ]

    # AI score quartile values
    ai_values = [d["ai_score_mean"] for d in ranked if d["ai_scores"]] if has_ai else []

    # Filter toolbar
    ranking_label = "by avg AI score" if has_ai else "by avg confidence"
    lines.append(f"<h2>Configuration Ranking ({ranking_label})</h2>")
    lines.append("<div class='filter-toolbar'>")
    axis_labels = {
        "library": "Library",
        "tessdata": "Tessdata",
        "dpi": "DPI",
        "psm": "PSM",
        "preprocess": "Preprocess",
        "penalty": "Dict Penalty",
    }
    for axis, label in axis_labels.items():
        options = "".join(f"<option value='{v}'>{v}</option>" for v in axis_values[axis])
        lines.append(
            f"<label>{label}: <select class='filter-select' data-axis='{axis}' "
            f"onchange='applyFilters()'><option value=''>All</option>{options}</select></label>"
        )
    lines.append("<button onclick='resetFilters()'>Reset</button>")
    lines.append("</div>")
    # Quartile filters — second row
    lines.append("<div class='filter-toolbar'>")
    q_options = "".join(f"<option value='{q}'>{q}</option>" for q in ["Q4 (best)", "Q3", "Q2", "Q1 (worst)"])
    lines.append(
        f"<label>Confidence: <select class='filter-select' data-axis='confq' "
        f"onchange='applyFilters()'><option value=''>All</option>{q_options}</select></label>"
    )
    if has_ai:
        lines.append(
            f"<label>AI Score: <select class='filter-select' data-axis='aiq' "
            f"onchange='applyFilters()'><option value=''>All</option>{q_options}</select></label>"
        )
    q_time_options = "".join(f"<option value='{q}'>{q}</option>" for q in ["Q4 (fastest)", "Q3", "Q2", "Q1 (slowest)"])
    lines.append(
        f"<label>Time: <select class='filter-select' data-axis='timeq' "
        f"onchange='applyFilters()'><option value=''>All</option>{q_time_options}</select></label>"
    )
    lines.append("</div>")

    # Config ranking table
    lines.append("<table id='ranking-table' class='filterable-table'>")
    lines.append("<thead><tr>")
    lines.append(_sortable_th("#", is_num=True))
    lines.append(_sortable_th("Library"))
    lines.append(_sortable_th("Tessdata"))
    lines.append(_sortable_th("DPI", is_num=True))
    lines.append(_sortable_th("PSM", is_num=True))
    lines.append(_sortable_th("Preprocess"))
    lines.append(_sortable_th("Dict Penalty", is_num=True))
    if has_ai:
        lines.append(_sortable_th("Avg AI Score", is_num=True))
    lines.append(_sortable_th("Avg Confidence", is_num=True))
    lines.append(_sortable_th("Avg Words", is_num=True))
    lines.append(_sortable_th("Avg Unique", is_num=True))
    lines.append(_sortable_th("Total Time", is_num=True))
    lines.append("</tr></thead>")
    lines.append("<tbody>")

    # Map heatmap class to filter label
    _q_label = {
        "heatmap-q4": "Q4 (best)",
        "heatmap-q3": "Q3",
        "heatmap-q2": "Q2",
        "heatmap-q1": "Q1 (worst)",
    }
    _qt_label = {
        "heatmap-q4": "Q4 (fastest)",
        "heatmap-q3": "Q3",
        "heatmap-q2": "Q2",
        "heatmap-q1": "Q1 (slowest)",
    }

    for rank, d in enumerate(ranked, 1):
        cfg = d["config"]
        conf_hm = _quartile_class(d["conf_mean"], conf_values) if d["confidences"] else "heatmap-q1"
        time_hm = _quartile_class(d["total_time"], time_values, reverse=True)
        conf_str = _fmt_mean_std(d["conf_mean"], d["conf_std"]) if d["confidences"] else "n/a"
        words_str = _fmt_mean_std(d["words_mean"], d["words_std"])
        unique_str = _fmt_mean_std(d["unique_mean"], d["unique_std"])
        best_cls = " class='best'" if rank == 1 else ""

        # AI score data attributes
        ai_data_attr = ""
        if has_ai:
            ai_hm = _quartile_class(d["ai_score_mean"], ai_values) if d["ai_scores"] else "heatmap-q1"
            ai_data_attr = f" data-aiq='{_q_label[ai_hm]}'"

        lines.append(
            f"<tr{best_cls} data-library='{_html_escape(cfg.library)}' "
            f"data-tessdata='{_html_escape(cfg.tessdata)}' "
            f"data-dpi='{cfg.dpi}' data-psm='{cfg.psm}' "
            f"data-preprocess='{_html_escape(cfg.preprocess)}' "
            f"data-penalty='{cfg.dict_penalty}' "
            f"data-confq='{_q_label[conf_hm]}' "
            f"data-timeq='{_qt_label[time_hm]}'"
            f"{ai_data_attr}>"
        )
        lines.append(f"  <td data-value='{rank}'><a href='configs/{_html_escape(cfg.slug)}.html'>{rank}</a></td>")
        lines.append(f"  <td>{_html_escape(cfg.library)}</td>")
        lines.append(f"  <td>{_html_escape(cfg.tessdata)}</td>")
        lines.append(f"  <td class='num' data-value='{cfg.dpi}'>{cfg.dpi}</td>")
        lines.append(f"  <td class='num' data-value='{cfg.psm}'>{cfg.psm}</td>")
        lines.append(f"  <td>{_html_escape(cfg.preprocess)}</td>")
        lines.append(f"  <td class='num' data-value='{cfg.dict_penalty}'>{cfg.dict_penalty}</td>")
        if has_ai:
            ai_hm = _quartile_class(d["ai_score_mean"], ai_values) if d["ai_scores"] else "heatmap-q1"
            ai_str = _fmt_mean_std(d["ai_score_mean"], d["ai_score_std"]) if d["ai_scores"] else "n/a"
            ai_data_val = f"{d['ai_score_mean']:.2f}" if d["ai_scores"] else "-1"
            lines.append(f"  <td class='num {ai_hm}' data-value='{ai_data_val}'>{ai_str}</td>")
        conf_data_val = f"{d['conf_mean']:.2f}" if d["confidences"] else "-1"
        lines.append(f"  <td class='num {conf_hm}' data-value='{conf_data_val}'>{conf_str}</td>")
        lines.append(f"  <td class='num' data-value='{d['words_mean']:.2f}'>{words_str}</td>")
        lines.append(f"  <td class='num' data-value='{d['unique_mean']:.2f}'>{unique_str}</td>")
        lines.append(f"  <td class='num {time_hm}' data-value='{d['total_time']:.2f}'>{d['total_time']:.1f}s</td>")
        lines.append("</tr>")

    lines.append("</tbody></table>")

    # Card index as 3-column table
    lines.append("<h2>Per-Card Results</h2>")
    lines.append("<table class='card-grid'>")
    lines.append("<tbody>")
    for i in range(0, len(card_ids), 3):
        lines.append("<tr>")
        for j in range(3):
            if i + j < len(card_ids):
                cid = card_ids[i + j]
                lines.append(f'  <td><a href="cards/{_html_escape(cid)}.html">{_html_escape(cid)}</a></td>')
            else:
                lines.append("  <td></td>")
        lines.append("</tr>")
    lines.append("</tbody></table>")

    lines.append("</body></html>")
    return "\n".join(lines)


# noinspection DuplicatedCode
def generate_card_html(
    card: CardResult,
    card_idx: int,
    all_card_ids: list[str],
) -> str:
    """Generate a per-card HTML page."""
    has_ai = any(r.ai_score >= 0 for r in card.results)
    prev_id = all_card_ids[card_idx - 1] if card_idx > 0 else None
    next_id = all_card_ids[card_idx + 1] if card_idx < len(all_card_ids) - 1 else None

    # Sort results by AI score if available, otherwise by confidence
    if has_ai:
        sorted_results = sorted(card.results, key=lambda r: r.ai_score, reverse=True)
    else:
        sorted_results = sorted(card.results, key=lambda r: r.confidence, reverse=True)

    conf_values = [r.confidence for r in sorted_results if r.confidence >= 0]
    ai_values = [r.ai_score for r in sorted_results if r.ai_score >= 0] if has_ai else []
    time_values = [r.elapsed_s for r in sorted_results]
    best_conf = conf_values[0] if conf_values else -1

    lines = [
        "<!DOCTYPE html>",
        "<html lang='en'>",
        "<head>",
        "<meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        f"<title>Card: {_html_escape(card.card_id)}</title>",
        f"<style>{CSS}</style>",
        REPORT_JS,
        "</head>",
        "<body>",
        f"<h1>Card: {_html_escape(card.card_id)}</h1>",
        "<nav>",
        '  <a href="../index.html">Summary</a>',
    ]

    if prev_id:
        lines.append(f'  <a href="{_html_escape(prev_id)}.html">&larr; {_html_escape(prev_id)}</a>')
    if next_id:
        lines.append(f'  <a href="{_html_escape(next_id)}.html">{_html_escape(next_id)} &rarr;</a>')

    lines.append("</nav>")

    # Card images
    lines.append("<div class='card-images'>")
    for i, b64 in enumerate(card.page_images_b64):
        lines.append(f'  <img src="{b64}" alt="Page {i + 1}">')
    lines.append("</div>")

    # Results table
    sort_label = "sorted by AI score" if has_ai else "sorted by confidence"
    lines.append(f"<h2>OCR Results ({sort_label})</h2>")
    lines.append("<table>")
    lines.append("<thead><tr>")
    lines.append(_sortable_th("#", is_num=True))
    lines.append(_sortable_th("Library"))
    lines.append(_sortable_th("Tessdata"))
    lines.append(_sortable_th("DPI", is_num=True))
    lines.append(_sortable_th("PSM", is_num=True))
    lines.append(_sortable_th("Preprocess"))
    lines.append(_sortable_th("Dict Penalty", is_num=True))
    if has_ai:
        lines.append(_sortable_th("AI", is_num=True))
    lines.append(_sortable_th("Conf", is_num=True))
    lines.append(_sortable_th("Words", is_num=True))
    lines.append(_sortable_th("Unique", is_num=True))
    lines.append(_sortable_th("Time", is_num=True))
    lines.append("<th>Text</th>")
    lines.append("</tr></thead>")
    lines.append("<tbody>")

    for rank, r in enumerate(sorted_results, 1):
        cfg = r.config
        conf_hm = _quartile_class(r.confidence, conf_values) if r.confidence >= 0 else "heatmap-q1"
        time_hm = _quartile_class(r.elapsed_s, time_values, reverse=True)
        conf_str = f"{r.confidence:.1f}%" if r.confidence >= 0 else "n/a"
        best_marker = ""
        if has_ai:
            if r.ai_score >= 0 and rank == 1:
                best_marker = " class='best'"
        elif r.confidence >= 0 and r.confidence == best_conf:
            best_marker = " class='best'"
        text_escaped = _html_escape(r.text)

        lines.append(f"<tr{best_marker}>")
        lines.append(f"  <td data-value='{rank}'><a href='../configs/{_html_escape(cfg.slug)}.html'>{rank}</a></td>")
        lines.append(f"  <td>{_html_escape(cfg.library)}</td>")
        lines.append(f"  <td>{_html_escape(cfg.tessdata)}</td>")
        lines.append(f"  <td class='num' data-value='{cfg.dpi}'>{cfg.dpi}</td>")
        lines.append(f"  <td class='num' data-value='{cfg.psm}'>{cfg.psm}</td>")
        lines.append(f"  <td>{_html_escape(cfg.preprocess)}</td>")
        lines.append(f"  <td class='num' data-value='{cfg.dict_penalty}'>{cfg.dict_penalty}</td>")
        if has_ai:
            ai_hm = _quartile_class(r.ai_score, ai_values) if r.ai_score >= 0 else "heatmap-q1"
            ai_str = f"{r.ai_score:.0f}" if r.ai_score >= 0 else "n/a"
            ai_data_val = f"{r.ai_score:.2f}" if r.ai_score >= 0 else "-1"
            lines.append(f"  <td class='num {ai_hm}' data-value='{ai_data_val}'>{ai_str}</td>")
        conf_data_val = f"{r.confidence:.2f}" if r.confidence >= 0 else "-1"
        lines.append(f"  <td class='num {conf_hm}' data-value='{conf_data_val}'>{conf_str}</td>")
        lines.append(f"  <td class='num' data-value='{r.word_count}'>{r.word_count}</td>")
        lines.append(f"  <td class='num' data-value='{r.unique_words}'>{r.unique_words}</td>")
        lines.append(f"  <td class='num {time_hm}' data-value='{r.elapsed_s:.4f}'>{r.elapsed_s:.2f}s</td>")
        lines.append(f"  <td><div class='text-cell'>{text_escaped}</div>")
        lines.append("    <button class='toggle-btn' onclick='toggleText(this)'>expand</button></td>")
        lines.append("</tr>")

    lines.append("</tbody></table>")
    lines.append("</body></html>")
    return "\n".join(lines)


# noinspection DuplicatedCode
def generate_config_html(
    cfg: Config,
    card_results: list[CardResult],
    config_idx: int,
    ranked_configs: list[Config],
    config_stats: dict[str, dict],
) -> str:
    """Generate a per-config HTML detail page."""
    prev_cfg = ranked_configs[config_idx - 1] if config_idx > 0 else None
    next_cfg = ranked_configs[config_idx + 1] if config_idx < len(ranked_configs) - 1 else None

    has_ai = _has_ai_scores(card_results)

    # Collect results for this config across all cards
    config_results: list[tuple[str, OCRResult]] = []
    for card in card_results:
        for r in card.results:
            if r.config.name == cfg.name:
                config_results.append((card.card_id, r))

    # Sort by AI score if available, otherwise by confidence
    if has_ai:
        config_results.sort(key=lambda x: x[1].ai_score, reverse=True)
    else:
        config_results.sort(key=lambda x: x[1].confidence, reverse=True)

    conf_values = [r.confidence for _, r in config_results if r.confidence >= 0]
    ai_values = [r.ai_score for _, r in config_results if r.ai_score >= 0] if has_ai else []
    time_values = [r.elapsed_s for _, r in config_results]

    stats = config_stats.get(cfg.name, {})

    lines = [
        "<!DOCTYPE html>",
        "<html lang='en'>",
        "<head>",
        "<meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        f"<title>Config: {_html_escape(cfg.name)}</title>",
        f"<style>{CSS}</style>",
        REPORT_JS,
        "</head>",
        "<body>",
        f"<h1>Config #{config_idx + 1} &mdash; {_html_escape(cfg.short_name)}</h1>",
        "<nav>",
        '  <a href="../index.html">Summary</a>',
    ]

    if prev_cfg:
        lines.append(f'  <a href="{_html_escape(prev_cfg.slug)}.html">&larr; #{config_idx}</a>')
    if next_cfg:
        lines.append(f'  <a href="{_html_escape(next_cfg.slug)}.html">#{config_idx + 2} &rarr;</a>')

    lines.append("</nav>")

    # Config parameters
    lines.append("<dl class='config-params'>")
    params = [
        ("Library", cfg.library),
        ("Tessdata", cfg.tessdata),
        ("DPI", str(cfg.dpi)),
        ("PSM", str(cfg.psm)),
        ("Preprocess", cfg.preprocess),
        ("Dict Penalty", str(cfg.dict_penalty)),
    ]
    for label, value in params:
        lines.append(f"  <dt>{label}</dt><dd>{_html_escape(value)}</dd>")
    lines.append("</dl>")

    # Aggregate stats
    if stats:
        conf_str = _fmt_mean_std(stats["conf_mean"], stats["conf_std"]) if stats.get("confidences") else "n/a"
        lines.append("<div class='meta'>")
        if has_ai and stats.get("ai_scores"):
            ai_str = _fmt_mean_std(stats["ai_score_mean"], stats["ai_score_std"])
            lines.append(f"  <span>Avg AI Score: {ai_str}</span>")
        lines.append(f"  <span>Avg Confidence: {conf_str}</span>")
        lines.append(f"  <span>Avg Words: {_fmt_mean_std(stats['words_mean'], stats['words_std'])}</span>")
        lines.append(f"  <span>Total Time: {stats['total_time']:.1f}s</span>")
        lines.append("</div>")

    # Results table
    lines.append(f"<h2>Results across {len(config_results)} cards</h2>")
    lines.append("<table>")
    lines.append("<thead><tr>")
    lines.append(_sortable_th("#", is_num=True))
    lines.append(_sortable_th("Card", is_num=False))
    if has_ai:
        lines.append(_sortable_th("AI", is_num=True))
    lines.append(_sortable_th("Conf", is_num=True))
    lines.append(_sortable_th("Words", is_num=True))
    lines.append(_sortable_th("Unique", is_num=True))
    lines.append(_sortable_th("Time", is_num=True))
    lines.append("<th>Text</th>")
    lines.append("</tr></thead>")
    lines.append("<tbody>")

    for rank, (card_id, r) in enumerate(config_results, 1):
        conf_hm = _quartile_class(r.confidence, conf_values) if r.confidence >= 0 else "heatmap-q1"
        time_hm = _quartile_class(r.elapsed_s, time_values, reverse=True)
        conf_str = f"{r.confidence:.1f}%" if r.confidence >= 0 else "n/a"
        text_escaped = _html_escape(r.text)
        conf_data_val = f"{r.confidence:.2f}" if r.confidence >= 0 else "-1"

        lines.append("<tr>")
        lines.append(f"  <td data-value='{rank}'>{rank}</td>")
        lines.append(f"  <td><a href='../cards/{_html_escape(card_id)}.html'>{_html_escape(card_id)}</a></td>")
        if has_ai:
            ai_hm = _quartile_class(r.ai_score, ai_values) if r.ai_score >= 0 else "heatmap-q1"
            ai_str = f"{r.ai_score:.0f}" if r.ai_score >= 0 else "n/a"
            ai_data_val = f"{r.ai_score:.2f}" if r.ai_score >= 0 else "-1"
            lines.append(f"  <td class='num {ai_hm}' data-value='{ai_data_val}'>{ai_str}</td>")
        lines.append(f"  <td class='num {conf_hm}' data-value='{conf_data_val}'>{conf_str}</td>")
        lines.append(f"  <td class='num' data-value='{r.word_count}'>{r.word_count}</td>")
        lines.append(f"  <td class='num' data-value='{r.unique_words}'>{r.unique_words}</td>")
        lines.append(f"  <td class='num {time_hm}' data-value='{r.elapsed_s:.4f}'>{r.elapsed_s:.2f}s</td>")
        lines.append(f"  <td><div class='text-cell'>{text_escaped}</div>")
        lines.append("    <button class='toggle-btn' onclick='toggleText(this)'>expand</button></td>")
        lines.append("</tr>")

    lines.append("</tbody></table>")
    lines.append("</body></html>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CSV exports
# ---------------------------------------------------------------------------


# noinspection PyShadowingNames
def write_summary_csv(
    path: Path,
    config_stats: dict[str, dict],
    has_ai: bool,
) -> None:
    """Write summary.csv — one row per config with aggregate stats."""
    # Sort by AI score if available, otherwise by confidence
    if has_ai:
        ranked = sorted(config_stats.values(), key=lambda d: d["ai_score_mean"], reverse=True)
    else:
        ranked = sorted(config_stats.values(), key=lambda d: d["conf_mean"], reverse=True)

    headers = [
        "library",
        "tessdata",
        "dpi",
        "psm",
        "preprocess",
        "dict_penalty",
        "conf_mean",
        "conf_std",
        "words_mean",
        "words_std",
        "unique_mean",
        "unique_std",
        "total_time_s",
    ]
    if has_ai:
        headers.extend(["ai_score_mean", "ai_score_std"])

    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for d in ranked:
            cfg = d["config"]
            row = [
                cfg.library,
                cfg.tessdata,
                cfg.dpi,
                cfg.psm,
                cfg.preprocess,
                cfg.dict_penalty,
                f"{d['conf_mean']:.2f}",
                f"{d['conf_std']:.2f}",
                f"{d['words_mean']:.2f}",
                f"{d['words_std']:.2f}",
                f"{d['unique_mean']:.2f}",
                f"{d['unique_std']:.2f}",
                f"{d['total_time']:.2f}",
            ]
            if has_ai:
                row.extend(
                    [
                        f"{d['ai_score_mean']:.2f}" if d["ai_scores"] else "",
                        f"{d['ai_score_std']:.2f}" if d["ai_scores"] else "",
                    ]
                )
            writer.writerow(row)


def write_detail_csv(
    path: Path,
    card_results: list[CardResult],
    has_ai: bool,
) -> None:
    """Write detail.csv — one row per (card x config) run."""
    headers = [
        "card_id",
        "library",
        "tessdata",
        "dpi",
        "psm",
        "preprocess",
        "dict_penalty",
        "word_count",
        "unique_words",
        "confidence",
        "elapsed_s",
    ]
    if has_ai:
        headers.append("ai_score")

    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for card in card_results:
            for r in card.results:
                cfg = r.config
                row = [
                    card.card_id,
                    cfg.library,
                    cfg.tessdata,
                    cfg.dpi,
                    cfg.psm,
                    cfg.preprocess,
                    cfg.dict_penalty,
                    r.word_count,
                    r.unique_words,
                    f"{r.confidence:.2f}",
                    f"{r.elapsed_s:.4f}",
                ]
                if has_ai:
                    row.append(f"{r.ai_score:.0f}" if r.ai_score >= 0 else "-1")
                writer.writerow(row)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

from scripts.helpers import script_output_dir

_FOLDER_NAME = "benchmark_ocr_configuration_quality"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="OCR Configuration Quality Benchmark — test Tesseract configurations on greeting card PDFs"
    )
    parser.add_argument("corpus", type=Path, help="Path to directory containing PDF files")
    parser.add_argument(
        "--configs",
        type=str,
        default=None,
        help="Comma-separated config filters (e.g. 'pytesseract/default/200/6/pillow/0.15,tesserocr')",
    )
    parser.add_argument(
        "-j",
        "--workers",
        type=int,
        default=mp.cpu_count(),
        help=f"Number of parallel workers (default: {mp.cpu_count()}, use 1 for sequential)",
    )
    parser.add_argument(
        "--no-ai-score",
        action="store_true",
        help="Disable AI scoring of OCR results (enabled by default)",
    )
    parser.add_argument(
        "--ai-model",
        type=str,
        default="claude-sonnet-4-5",
        help="Model for AI scoring (default: claude-sonnet-4-5)",
    )
    parser.add_argument(
        "--ai-concurrency",
        type=int,
        default=5,
        help="Max concurrent API calls for AI scoring (default: 5)",
    )
    parser.add_argument(
        "--dud-threshold",
        type=int,
        default=15,
        help="Max score for a card to be considered a dud in pass 1 (default: 15)",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Don't open the report in a browser when done",
    )
    args = parser.parse_args()

    corpus_path = args.corpus.expanduser().resolve()
    if not corpus_path.is_dir():
        console.print(f"[red]Error: {corpus_path} is not a directory[/]")
        sys.exit(1)

    configs = build_configs(args.configs)
    if not configs:
        console.print("[red]No configs match the filter![/]")
        sys.exit(1)

    num_workers = max(1, args.workers)
    ai_line = (
        f"  AI Scoring: [green]enabled[/] (model={rich_escape(args.ai_model)}, concurrency={args.ai_concurrency})"
        if not args.no_ai_score
        else "  AI Scoring: [dim]disabled[/]"
    )
    console.print(
        Panel(
            f"  Corpus:  {corpus_path}\n  Configs: {len(configs)}\n  Workers: {num_workers}\n{ai_line}",
            title="OCR Configuration Quality Benchmark",
            title_align="left",
            expand=False,
        )
    )

    with script_output_dir(_FOLDER_NAME) as output_dir:
        cards_dir = output_dir / "cards"
        cards_dir.mkdir(exist_ok=True)
        configs_dir = output_dir / "configs"
        configs_dir.mkdir(exist_ok=True)

        t0 = time.monotonic()
        card_results = run_benchmark(corpus_path, configs, output_dir, num_workers)
        elapsed_total = time.monotonic() - t0

        # AI scoring (after benchmark, before report generation)
        if not args.no_ai_score:
            ai_t0 = time.monotonic()
            asyncio.run(
                score_all_cards(
                    card_results,
                    model=args.ai_model,
                    concurrency=args.ai_concurrency,
                    dud_threshold=args.dud_threshold,
                )
            )
            ai_elapsed = time.monotonic() - ai_t0
            console.print(f"  AI scoring time: {ai_elapsed:.1f}s")

        console.print()

        # Filter configs to only those that actually ran (after availability checks)
        actual_configs = []
        seen_names = set()
        for card in card_results:
            for r in card.results:
                if r.config.name not in seen_names:
                    actual_configs.append(r.config)
                    seen_names.add(r.config.name)

        all_card_ids = [c.card_id for c in card_results]
        has_ai = _has_ai_scores(card_results)

        with console.status("Generating reports..."):
            # Compute config stats (shared by summary + config pages)
            config_stats = _compute_config_stats(card_results, actual_configs)

            # Ranked configs for config page navigation
            if has_ai:
                ranked_configs = [
                    d["config"] for d in sorted(config_stats.values(), key=lambda d: d["ai_score_mean"], reverse=True)
                ]
            else:
                ranked_configs = [
                    d["config"] for d in sorted(config_stats.values(), key=lambda d: d["conf_mean"], reverse=True)
                ]

            # Summary page
            summary_html = generate_summary_html(
                card_results,
                actual_configs,
                corpus_path,
                elapsed_total,
                config_stats,
            )
            (output_dir / "index.html").write_text(summary_html)

            # Per-card pages
            for idx, card in enumerate(card_results):
                card_html = generate_card_html(card, idx, all_card_ids)
                (cards_dir / f"{card.card_id}.html").write_text(card_html)

            # Per-config pages
            for idx, cfg in enumerate(ranked_configs):
                config_html = generate_config_html(
                    cfg,
                    card_results,
                    idx,
                    ranked_configs,
                    config_stats,
                )
                (configs_dir / f"{cfg.slug}.html").write_text(config_html)

            # CSV exports
            write_summary_csv(output_dir / "summary.csv", config_stats, has_ai)
            write_detail_csv(output_dir / "detail.csv", card_results, has_ai)

        index_path = output_dir / "index.html"
        console.print(
            f"  Summary:  {index_path}\n"
            f"  Cards:    {len(card_results)} pages in {cards_dir}/\n"
            f"  Configs:  {len(ranked_configs)} pages in {configs_dir}/\n"
            f"  CSV:      summary.csv, detail.csv\n"
            f"  Total time: {elapsed_total:.1f}s\n"
            f"\nOpen {index_path} in a browser to view results.",
        )

        if not args.no_open:
            subprocess.Popen(["open", str(index_path)])


if __name__ == "__main__":
    main()
