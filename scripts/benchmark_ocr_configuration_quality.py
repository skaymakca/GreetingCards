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
With ``--ai-score``, the benchmark sends OCR results to a Claude model for
quality evaluation.  This supplements Tesseract's self-reported confidence
(which only measures the engine's certainty, not actual text quality) with an
LLM judgment of how well the extracted text reads as a greeting card.

Scoring uses a two-pass design:

  Pass 1 — Triage:  All 192 OCR texts for each card are sent in a single API
  call.  The LLM assigns quick 0-100 scores.  Cards where ALL configs score
  below ``--dud-threshold`` (default 15) are classified as "duds" — image-heavy
  cards with no extractable text.  Duds are excluded from pass 2.

  Pass 2 — Refined:  Non-dud cards are re-scored with a detailed prompt that
  emphasises names (most important), readability, structure, completeness, and
  noise.  Pass 2 scores replace pass 1 scores for these cards.

Because the OCR texts are very short (avg ~28 tokens), all 192 texts for one
card fit comfortably in a single API call (~5K input tokens).  With the default
concurrency of 5, scoring completes in under a minute for a typical 41-card
corpus.  Estimated cost: ~$2.40 with Opus, ~$0.11 with Haiku.

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

When ``--ai-score`` is not used, the AI Score column is omitted entirely from
all outputs — the report is identical to the non-AI version.

Dependencies
------------
Required (already in project deps):
    pytesseract, Pillow, PyMuPDF, anthropic

Optional (dev):
    uv add --dev opencv-python-headless tesserocr

    - opencv-python-headless: enables clahe and otsu preprocessing pipelines
    - tesserocr: enables the tesserocr OCR library (alternative to pytesseract)

    If unavailable, configs using those features are automatically skipped.

Usage
-----
Basic benchmark (no AI scoring):

    uv run python scripts/benchmark_ocr_configuration_quality.py ~/Desktop/cards

With AI scoring:

    uv run python scripts/benchmark_ocr_configuration_quality.py ~/Desktop/cards --ai-score

Custom output directory and config filter:

    uv run python scripts/benchmark_ocr_configuration_quality.py ~/Desktop/cards \\
        -o results/ --configs pytesseract/default/200/6/pillow/0.15

AI scoring with Haiku for lower cost:

    uv run python scripts/benchmark_ocr_configuration_quality.py ~/Desktop/cards \\
        --ai-score --ai-model claude-haiku-4-5-20251001

Open the report:

    open _script_output/benchmark_ocr_configuration_quality/index.html

Environment Variables
---------------------
ANTHROPIC_API_KEY   Required when using ``--ai-score``.  The API key for
                    Claude model access.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import csv
import io
import itertools
import json
import math
import multiprocessing as mp
import os
import shutil
import statistics
import sys
import time
import urllib.request
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image, ImageChops, ImageFilter, ImageOps

# Optional imports — fail gracefully if not installed
try:
    import cv2
    import numpy as np

    _HAS_OPENCV = True
except ImportError:
    _HAS_OPENCV = False

try:
    import pytesseract

    _HAS_PYTESSERACT = True
except ImportError:
    _HAS_PYTESSERACT = False

try:
    import tesserocr

    _HAS_TESSEROCR = True
except ImportError:
    _HAS_TESSEROCR = False


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TESSDATA_BEST_URL = (
    "https://github.com/tesseract-ocr/tessdata_best/raw/main/eng.traineddata"
)
TESSDATA_BEST_DIR = Path(__file__).parent / "tessdata_best"

OCR_LIBRARIES = ["pytesseract", "tesserocr"]
TESSDATA_OPTIONS = ["default", "tessdata_best"]
DPI_OPTIONS = [200, 300]
PSM_OPTIONS = [3, 6, 11]
PREPROCESS_OPTIONS = ["pillow", "clahe", "sauvola", "otsu"]
DICT_PENALTY_OPTIONS = [0.15, 0.0]

# Map integer PSM values to tesserocr enum members (tesserocr.PSM can't be
# constructed from an int).
_TESSEROCR_PSM_MAP: dict[int, object] = {}
if _HAS_TESSEROCR:
    _TESSEROCR_PSM_MAP = {
        0: tesserocr.PSM.OSD_ONLY,
        1: tesserocr.PSM.AUTO_OSD,
        2: tesserocr.PSM.AUTO_ONLY,
        3: tesserocr.PSM.AUTO,
        4: tesserocr.PSM.SINGLE_COLUMN,
        5: tesserocr.PSM.SINGLE_BLOCK_VERT_TEXT,
        6: tesserocr.PSM.SINGLE_BLOCK,
        7: tesserocr.PSM.SINGLE_LINE,
        8: tesserocr.PSM.SINGLE_WORD,
        9: tesserocr.PSM.CIRCLE_WORD,
        10: tesserocr.PSM.SINGLE_CHAR,
        11: tesserocr.PSM.SPARSE_TEXT,
        12: tesserocr.PSM.SPARSE_TEXT_OSD,
        13: tesserocr.PSM.RAW_LINE,
    }


@dataclass
class Config:
    library: str
    tessdata: str
    dpi: int
    psm: int
    preprocess: str
    dict_penalty: float

    @property
    def name(self) -> str:
        return f"{self.library}/{self.tessdata}/{self.dpi}/{self.psm}/{self.preprocess}/{self.dict_penalty}"

    @property
    def short_name(self) -> str:
        return f"{self.library[:4]}/{self.tessdata[:4]}/{self.dpi}/{self.psm}/{self.preprocess}/{self.dict_penalty}"

    @property
    def slug(self) -> str:
        return self.name.replace("/", "_")


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
            OCR_LIBRARIES, TESSDATA_OPTIONS, DPI_OPTIONS, PSM_OPTIONS,
            PREPROCESS_OPTIONS, DICT_PENALTY_OPTIONS,
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
                cfg.library, cfg.tessdata, str(cfg.dpi), str(cfg.psm),
                cfg.preprocess, str(cfg.dict_penalty),
            ]
            if all(p == c for p, c in zip(parts, cfg_parts)):
                if cfg not in filtered:
                    filtered.append(cfg)
    return filtered


# ---------------------------------------------------------------------------
# tessdata management
# ---------------------------------------------------------------------------


def _detect_system_tessdata() -> str | None:
    """Find system tessdata directory (Homebrew or default locations)."""
    candidates = [
        "/opt/homebrew/share/tessdata",
        "/usr/local/share/tessdata",
    ]
    for path in candidates:
        if os.path.isdir(path):
            return path
    return None


def ensure_tessdata_best() -> Path:
    """Download tessdata_best/eng.traineddata if not already cached."""
    TESSDATA_BEST_DIR.mkdir(parents=True, exist_ok=True)
    eng_path = TESSDATA_BEST_DIR / "eng.traineddata"
    if eng_path.exists():
        return TESSDATA_BEST_DIR
    print(f"Downloading tessdata_best eng.traineddata...")
    urllib.request.urlretrieve(TESSDATA_BEST_URL, eng_path)
    size_mb = eng_path.stat().st_size / 1024 / 1024
    print(f"  Downloaded {size_mb:.1f} MB to {eng_path}")
    return TESSDATA_BEST_DIR


def get_tessdata_path(tessdata: str) -> str | None:
    """Return --tessdata-dir path for the given tessdata option.

    For 'default', returns the detected system tessdata path (if found).
    This ensures worker processes can locate tessdata even without the
    TESSDATA_PREFIX environment variable.
    """
    if tessdata == "default":
        return _detect_system_tessdata()
    return str(ensure_tessdata_best())


# ---------------------------------------------------------------------------
# PDF rendering (self-contained, copied from app/core/pdf_renderer.py)
# ---------------------------------------------------------------------------


def _capped_zoom(page: fitz.Page, dpi: int) -> fitz.Matrix:
    target_zoom = dpi / 72
    image_infos = page.get_image_info()
    if image_infos:
        max_native_dpi = max(
            max(info.get("xres", 72), info.get("yres", 72)) for info in image_infos
        )
        target_zoom = min(target_zoom, max_native_dpi / 72)
    return fitz.Matrix(target_zoom, target_zoom)


def autocrop_whitespace(
    image: Image.Image, threshold: int = 245, padding: int = 10
) -> Image.Image:
    gray = image.convert("L")
    blurred = gray.filter(ImageFilter.GaussianBlur(radius=5))
    bg = Image.new("L", blurred.size, threshold)
    diff = ImageChops.subtract(bg, blurred)
    bbox = diff.getbbox()
    if not bbox:
        return image
    left = max(0, bbox[0] - padding)
    top = max(0, bbox[1] - padding)
    right = min(image.width, bbox[2] + padding)
    bottom = min(image.height, bbox[3] + padding)
    return image.crop((left, top, right, bottom))


def render_all_pages(pdf_path: Path, dpi: int = 200) -> list[Image.Image]:
    doc = fitz.open(str(pdf_path))
    images = []
    try:
        for page in doc:
            pix = page.get_pixmap(matrix=_capped_zoom(page, dpi))
            img_data = pix.tobytes("png")
            images.append(autocrop_whitespace(Image.open(io.BytesIO(img_data))))
    finally:
        doc.close()
    return images


def image_to_base64(img: Image.Image, max_width: int = 300) -> str:
    """Resize image to thumbnail and encode as base64 data URI."""
    if img.width > max_width:
        ratio = max_width / img.width
        new_size = (max_width, int(img.height * ratio))
        img = img.resize(new_size, Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


# ---------------------------------------------------------------------------
# Preprocessing pipelines
# ---------------------------------------------------------------------------


def preprocess_pillow(img: Image.Image) -> Image.Image:
    """Current production pipeline: grayscale -> autocontrast -> sharpen."""
    img = ImageOps.grayscale(img)
    img = ImageOps.autocontrast(img, cutoff=2)
    img = img.filter(ImageFilter.SHARPEN)
    return img


def preprocess_clahe(img: Image.Image) -> Image.Image:
    """CLAHE + denoising + adaptive threshold (OpenCV)."""
    if not _HAS_OPENCV:
        raise RuntimeError("opencv-python-headless required for clahe preprocessing")
    gray = np.array(ImageOps.grayscale(img))
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    denoised = cv2.fastNlMeansDenoising(enhanced, h=10)
    binary = cv2.adaptiveThreshold(
        denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )
    return Image.fromarray(binary)


def preprocess_otsu(img: Image.Image) -> Image.Image:
    """Otsu threshold + sharpen (OpenCV)."""
    if not _HAS_OPENCV:
        raise RuntimeError("opencv-python-headless required for otsu preprocessing")
    gray = np.array(ImageOps.grayscale(img))
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    result = Image.fromarray(binary)
    return result.filter(ImageFilter.SHARPEN)


def preprocess_sauvola(img: Image.Image) -> Image.Image:
    """Pillow preprocessing (same as pillow) -- Sauvola thresholding is done by Tesseract."""
    img = ImageOps.grayscale(img)
    img = ImageOps.autocontrast(img, cutoff=2)
    img = img.filter(ImageFilter.SHARPEN)
    return img


PREPROCESS_FNS = {
    "pillow": preprocess_pillow,
    "clahe": preprocess_clahe,
    "otsu": preprocess_otsu,
    "sauvola": preprocess_sauvola,
}


# ---------------------------------------------------------------------------
# OCR engines
# ---------------------------------------------------------------------------


def _build_tesseract_config(cfg: Config) -> str:
    """Build Tesseract config string from a Config."""
    parts = [f"--psm {cfg.psm}"]
    if cfg.preprocess == "sauvola":
        parts.append("-c thresholding_method=2")
    tessdata_path = get_tessdata_path(cfg.tessdata)
    if tessdata_path:
        parts.append(f"--tessdata-dir {tessdata_path}")
    parts.append(f"-c language_model_penalty_non_dict_word={cfg.dict_penalty}")
    return " ".join(parts)


def ocr_pytesseract(img: Image.Image, cfg: Config) -> tuple[str, float]:
    """Run OCR with pytesseract. Returns (text, confidence).

    Uses image_to_data (single Tesseract call) to get both text and confidence.
    Reconstructs text structure using block_num, par_num, line_num from TSV output.
    """
    config_str = _build_tesseract_config(cfg)
    try:
        data = pytesseract.image_to_data(img, config=config_str, output_type=pytesseract.Output.DICT)
        # Group words by (block_num, par_num, line_num) to preserve structure
        lines_map: dict[tuple[int, int, int], list[str]] = defaultdict(list)
        confidences: list[int] = []
        for i, word in enumerate(data["text"]):
            conf = int(data["conf"][i])
            if conf > 0:
                confidences.append(conf)
            if word.strip():
                key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
                lines_map[key].append(word)

        # Reconstruct with paragraph structure
        paragraphs: dict[tuple[int, int], list[str]] = defaultdict(list)
        for (block, par, line), words in sorted(lines_map.items()):
            paragraphs[(block, par)].append(" ".join(words))

        text = "\n\n".join(
            "\n".join(lines)
            for _, lines in sorted(paragraphs.items())
        )
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    except Exception:
        text = ""
        avg_conf = -1.0
    return text.strip(), avg_conf


def ocr_tesserocr(img: Image.Image, cfg: Config) -> tuple[str, float]:
    """Run OCR with tesserocr. Returns (text, confidence)."""
    tessdata_path = get_tessdata_path(cfg.tessdata)
    kwargs: dict = {}
    if tessdata_path:
        kwargs["path"] = tessdata_path
    kwargs["lang"] = "eng"

    psm_enum = _TESSEROCR_PSM_MAP.get(cfg.psm)
    if psm_enum is None:
        raise ValueError(f"Unknown PSM value: {cfg.psm}")

    with tesserocr.PyTessBaseAPI(**kwargs) as api:
        api.SetPageSegMode(psm_enum)
        if cfg.preprocess == "sauvola":
            api.SetVariable("thresholding_method", "2")
        api.SetVariable("language_model_penalty_non_dict_word", str(cfg.dict_penalty))
        api.SetImage(img)
        text = api.GetUTF8Text().strip()
        confidence = api.MeanTextConf()
    return text, float(confidence)


OCR_FNS = {
    "pytesseract": ocr_pytesseract,
    "tesserocr": ocr_tesserocr,
}


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

# Sentinel value to tell workers to exit
_SENTINEL = None


def find_pdfs(corpus_path: Path) -> list[Path]:
    """Find all PDF files in the corpus directory."""
    pdfs = sorted(corpus_path.glob("*.pdf"))
    if not pdfs:
        pdfs = sorted(corpus_path.rglob("*.pdf"))
    return pdfs


def _image_to_png_bytes(img: Image.Image) -> bytes:
    """Serialize a PIL Image to PNG bytes for passing through multiprocessing queues."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _png_bytes_to_image(data: bytes) -> Image.Image:
    """Deserialize PNG bytes back to a PIL Image."""
    return Image.open(io.BytesIO(data))


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

        result_queue.put((
            card_id,
            cfg_dict,
            combined_text,
            len(words),
            len(set(w.lower() for w in words)),
            sum(all_confidences) / len(all_confidences) if all_confidences else -1.0,
            elapsed,
        ))


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
        print(f"Warning: skipping configs for unavailable libraries: {missing}")
        configs = [c for c in configs if c.library in available_libs]

    if not _HAS_OPENCV:
        opencv_preprocs = {"clahe", "otsu"}
        needed_opencv = {c.preprocess for c in configs} & opencv_preprocs
        if needed_opencv:
            print(f"Warning: skipping configs with {needed_opencv} preprocessing (OpenCV not installed)")
            configs = [c for c in configs if c.preprocess not in opencv_preprocs]

    return configs


def _validate_configs(
    configs: list[Config],
    first_pdf: Path,
    page_cache: dict[tuple[str, int], list[bytes]],
) -> list[Config]:
    """Run all configs on the first card and exclude any that fail."""
    print(f"Validating {len(configs)} configs on {first_pdf.stem}...")
    valid = []
    failed = []
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

    if failed:
        print(f"  {len(failed)} configs failed validation:")
        for cfg, err in failed:
            print(f"    {cfg.name}: {err}")
    print(f"  {len(valid)} configs passed validation")
    return valid


def run_benchmark(
    corpus_path: Path, configs: list[Config], output_dir: Path, num_workers: int = 1
) -> list[CardResult]:
    pdfs = find_pdfs(corpus_path)
    if not pdfs:
        print(f"No PDF files found in {corpus_path}")
        sys.exit(1)

    configs = _filter_configs(configs)
    if not configs:
        print("No valid configs to run!")
        sys.exit(1)

    # Set TESSDATA_PREFIX for worker processes
    system_tessdata = _detect_system_tessdata()
    if system_tessdata:
        os.environ["TESSDATA_PREFIX"] = system_tessdata

    total_runs = len(pdfs) * len(configs)
    print(f"Found {len(pdfs)} PDFs, {len(configs)} configs = {total_runs} OCR runs")
    print(f"Workers: {num_workers}")

    # Pre-download tessdata_best if needed
    if any(c.tessdata == "tessdata_best" for c in configs):
        ensure_tessdata_best()

    dpi_levels = sorted({c.dpi for c in configs})

    # --- Pre-render all pages (main process) ---
    print("Rendering pages...")
    # page_cache: (pdf_path_str, dpi) -> list[png_bytes]
    page_cache: dict[tuple[str, int], list[bytes]] = {}
    # thumbnails: pdf_path_str -> list[base64_str]
    thumbnails: dict[str, list[str]] = {}

    for pdf_path in pdfs:
        for dpi in dpi_levels:
            key = (str(pdf_path), dpi)
            images = render_all_pages(pdf_path, dpi)
            page_cache[key] = [_image_to_png_bytes(img) for img in images]
        # Thumbnails from highest DPI
        best_dpi = max(dpi_levels)
        best_images = [_png_bytes_to_image(b) for b in page_cache[(str(pdf_path), best_dpi)]]
        thumbnails[str(pdf_path)] = [image_to_base64(img) for img in best_images]

    print(f"  Rendered {len(pdfs)} cards at {len(dpi_levels)} DPI levels")

    # --- Validation pass ---
    configs = _validate_configs(configs, pdfs[0], page_cache)
    if not configs:
        print("No configs passed validation!")
        sys.exit(1)

    # Recalculate total after validation may have excluded configs
    total_runs = len(pdfs) * len(configs)
    print(f"Running {total_runs} OCR jobs ({len(configs)} configs x {len(pdfs)} cards)...")

    is_tty = sys.stderr.isatty()

    # --- Build jobs ---
    jobs: list[tuple[str, dict, list[bytes]]] = []
    for pdf_path in pdfs:
        card_id = pdf_path.stem
        for cfg in configs:
            page_data = page_cache[(str(pdf_path), cfg.dpi)]
            jobs.append((card_id, _cfg_to_dict(cfg), page_data))

    if num_workers <= 1:
        # --- Sequential mode ---
        card_map: dict[str, CardResult] = {}
        current_card: str | None = None
        card_start_time = 0.0
        cards_done = 0

        for i, (card_id, cfg_dict, page_png_list) in enumerate(jobs, 1):
            cfg = Config(**cfg_dict)

            # Track card transitions for non-TTY progress
            if card_id != current_card:
                if current_card is not None:
                    cards_done += 1
                    if not is_tty:
                        card_elapsed = time.monotonic() - card_start_time
                        print(
                            f"  [{cards_done}/{len(pdfs)}] {current_card} "
                            f"({len(configs)} configs, {card_elapsed:.1f}s)",
                            file=sys.stderr,
                        )
                current_card = card_id
                card_start_time = time.monotonic()

            if is_tty:
                pct = i / total_runs * 100
                print(
                    f"\r  [{i}/{total_runs}] ({pct:.0f}%) {card_id} — {cfg.short_name}",
                    end="",
                    flush=True,
                    file=sys.stderr,
                )

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
            card_map[card_id].results.append(OCRResult(
                config=cfg,
                text=combined_text,
                word_count=len(words),
                unique_words=len(set(w.lower() for w in words)),
                confidence=sum(all_confidences) / len(all_confidences) if all_confidences else -1.0,
                elapsed_s=elapsed,
            ))

        # Final card summary
        if current_card is not None:
            cards_done += 1
            if not is_tty:
                card_elapsed = time.monotonic() - card_start_time
                print(
                    f"  [{cards_done}/{len(pdfs)}] {current_card} "
                    f"({len(configs)} configs, {card_elapsed:.1f}s)",
                    file=sys.stderr,
                )

        if is_tty:
            print(file=sys.stderr)
        return [card_map[p.stem] for p in pdfs]

    # --- Parallel mode ---
    print(f"Queuing {total_runs} jobs across {num_workers} workers...")
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
    card_map: dict[str, CardResult] = {}
    card_done_count: dict[str, int] = defaultdict(int)
    card_first_seen: dict[str, float] = {}
    cards_completed = 0

    for i in range(total_runs):
        card_id, cfg_dict, text, word_count, unique_words, confidence, elapsed = result_queue.get()
        cfg = Config(**cfg_dict)

        if card_id not in card_first_seen:
            card_first_seen[card_id] = time.monotonic()

        card_done_count[card_id] += 1

        if is_tty:
            pct = (i + 1) / total_runs * 100
            print(
                f"\r  [{i + 1}/{total_runs}] ({pct:.0f}%) {card_id} — {cfg.short_name}    ",
                end="",
                flush=True,
                file=sys.stderr,
            )

        if card_done_count[card_id] == len(configs):
            cards_completed += 1
            if not is_tty:
                card_elapsed = time.monotonic() - card_first_seen[card_id]
                print(
                    f"  [{cards_completed}/{len(pdfs)}] {card_id} "
                    f"({len(configs)} configs, {card_elapsed:.1f}s)",
                    file=sys.stderr,
                )

        if card_id not in card_map:
            pdf_path = next(p for p in pdfs if p.stem == card_id)
            card_map[card_id] = CardResult(
                card_id=card_id,
                pdf_path=pdf_path,
                page_images_b64=thumbnails[str(pdf_path)],
            )

        card_map[card_id].results.append(OCRResult(
            config=cfg,
            text=text,
            word_count=word_count,
            unique_words=unique_words,
            confidence=confidence,
            elapsed_s=elapsed,
        ))

    # Wait for workers to finish
    for p in workers:
        p.join()

    if is_tty:
        print(file=sys.stderr)

    # Return in original PDF order
    return [card_map[p.stem] for p in pdfs]


# ---------------------------------------------------------------------------
# Statistics helpers
# ---------------------------------------------------------------------------


def _mean_std(values: list[float]) -> tuple[float, float]:
    """Return (mean, stdev) for a list of values. Returns (0, 0) if empty."""
    if not values:
        return 0.0, 0.0
    m = statistics.mean(values)
    sd = statistics.pstdev(values) if len(values) > 1 else 0.0
    return m, sd


def _fmt_mean_std(mean: float, std: float, fmt: str = ".1f") -> str:
    """Format mean +/- std as a string."""
    return f"{mean:{fmt}} &plusmn; {std:{fmt}}"


def _compute_config_stats(
    card_results: list[CardResult], configs: list[Config]
) -> dict[str, dict]:
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
            "You ALWAYS respond with ONLY a JSON array of integers — no explanation, no commentary, no markdown. "
            f"The array must have exactly {n} elements, each 0-100."
        )
        user = (
            f"Below are {n} text extractions from the same card using different OCR configurations.\n"
            "Score each text 0-100 based on how much readable greeting card content it contains.\n"
            "- 0: empty, pure gibberish, or completely unreadable\n"
            "- 1-30: mostly noise with a few recognizable words\n"
            "- 31-60: partially readable, some greeting card content visible\n"
            "- 61-80: mostly readable greeting card text\n"
            "- 81-100: clear, well-structured greeting card text\n\n"
            f"Reply with ONLY a JSON array of {n} integers. No other text.\n\n"
        )
    else:
        system = (
            "You score OCR-extracted text from greeting cards. "
            "You ALWAYS respond with ONLY a JSON array of integers — no explanation, no commentary, no markdown. "
            f"The array must have exactly {n} elements, each 0-100."
        )
        user = (
            f"Below are {n} text extractions from the same card using different OCR configurations.\n"
            "Score each text 0-100 based on overall quality as extracted greeting card text.\n\n"
            "Scoring criteria (most to least important):\n"
            "1. Names: People's names, family names (\"The Smiths\", \"Love, Jason and Amanda\") — most valuable\n"
            "2. Readability: Coherent sentences about holidays, wishes, family updates\n"
            "3. Structure: Preserved line breaks and paragraphs vs flat wall of text\n"
            "4. Completeness: More captured content is better than less\n"
            "5. Noise: Penalize OCR artifacts, random symbols, fragmented words\n\n"
            f"Reply with ONLY a JSON array of {n} integers. No other text.\n\n"
        )

    # Build text blocks
    blocks = []
    for i, text in enumerate(texts, 1):
        display = text.strip() if text.strip() else "[EMPTY]"
        blocks.append(f"--- Config {i} ---\n{display}")

    return system, user + "\n".join(blocks)


def _parse_scores(response_text: str, expected_n: int) -> list[int] | None:
    """Parse JSON array of scores from LLM response. Returns None on failure."""
    # Strip markdown code fences if present
    text = response_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json or ```) and last line (```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        scores = json.loads(text)
    except json.JSONDecodeError:
        return None

    if not isinstance(scores, list) or len(scores) != expected_n:
        return None

    # Validate and clamp
    result = []
    for s in scores:
        if not isinstance(s, (int, float)):
            return None
        result.append(max(0, min(100, int(round(s)))))
    return result


async def _score_card(
    client: "anthropic.AsyncAnthropic",
    card_id: str,
    texts: list[str],
    pass_num: int,
    model: str,
    semaphore: asyncio.Semaphore,
) -> tuple[str, list[int] | None, float]:
    """Score one card's OCR texts via a single API call.

    Returns (card_id, scores_or_None, elapsed_seconds).
    """
    system_prompt, user_message = _build_scoring_prompt(texts, pass_num)

    async with semaphore:
        t0 = time.monotonic()
        try:
            response = await client.messages.create(
                model=model,
                max_tokens=4096,
                temperature=0,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            response_text = response.content[0].text
            scores = _parse_scores(response_text, len(texts))
            if scores is None:
                # Show truncated response for debugging
                preview = response_text[:200] + "..." if len(response_text) > 200 else response_text
                print(
                    f"\n  Warning: parse failure for {card_id} (pass {pass_num}), "
                    f"stop={response.stop_reason}, response preview: {preview}",
                    file=sys.stderr,
                )
        except Exception as exc:
            err = exc
            print(f"\n  Warning: API error for {card_id} (pass {pass_num}): {err}", file=sys.stderr)
            scores = None
        elapsed = time.monotonic() - t0

    return card_id, scores, elapsed


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
    is_tty = sys.stderr.isatty()

    # Build ordered list of texts per card (preserving config order)
    # Each card has the same configs in the same order
    card_texts: dict[str, list[str]] = {}
    for card in card_results:
        card_texts[card.card_id] = [r.text for r in card.results]

    total_cards = len(card_results)

    # --- Pass 1: Triage ---
    print(f"\nAI Scoring — Pass 1 (triage): {total_cards} cards, model={model}", file=sys.stderr)

    tasks = [
        _score_card(client, card_id, texts, 1, model, semaphore)
        for card_id, texts in card_texts.items()
    ]

    pass1_scores: dict[str, list[int]] = {}
    completed = 0
    for coro in asyncio.as_completed(tasks):
        card_id, scores, elapsed = await coro
        completed += 1
        if scores is not None:
            pass1_scores[card_id] = scores
        else:
            print(f"\n  Warning: failed to parse scores for {card_id} (pass 1)", file=sys.stderr)

        if is_tty:
            print(
                f"\r  [{completed}/{total_cards}] Scored {card_id} (pass 1, {elapsed:.1f}s)   ",
                end="", flush=True, file=sys.stderr,
            )
        else:
            print(
                f"  [{completed}/{total_cards}] {card_id} scored (pass 1, {elapsed:.1f}s)",
                file=sys.stderr,
            )

    if is_tty:
        print(file=sys.stderr)

    # Identify dud cards (all scores <= dud_threshold)
    dud_cards = set()
    for card_id, scores in pass1_scores.items():
        if max(scores) <= dud_threshold:
            dud_cards.add(card_id)

    non_dud_cards = [c for c in card_results if c.card_id not in dud_cards and c.card_id in pass1_scores]
    print(
        f"  Pass 1 complete: {len(dud_cards)} dud cards excluded, "
        f"{len(non_dud_cards)} cards advancing to pass 2",
        file=sys.stderr,
    )
    if dud_cards:
        print(f"  Dud cards: {', '.join(sorted(dud_cards))}", file=sys.stderr)

    # Apply pass 1 scores to dud cards (they won't be re-scored)
    for card in card_results:
        if card.card_id in dud_cards and card.card_id in pass1_scores:
            scores = pass1_scores[card.card_id]
            for r, score in zip(card.results, scores):
                r.ai_score = float(score)

    # --- Pass 2: Refined scoring for non-dud cards ---
    if non_dud_cards:
        print(f"\nAI Scoring — Pass 2 (refined): {len(non_dud_cards)} cards", file=sys.stderr)

        tasks = [
            _score_card(client, card.card_id, card_texts[card.card_id], 2, model, semaphore)
            for card in non_dud_cards
        ]

        completed = 0
        for coro in asyncio.as_completed(tasks):
            card_id, scores, elapsed = await coro
            completed += 1

            if scores is not None:
                # Find the card and apply scores
                for card in card_results:
                    if card.card_id == card_id:
                        for r, score in zip(card.results, scores):
                            r.ai_score = float(score)
                        break
            else:
                # Fall back to pass 1 scores
                print(f"\n  Warning: failed to parse scores for {card_id} (pass 2), using pass 1", file=sys.stderr)
                if card_id in pass1_scores:
                    for card in card_results:
                        if card.card_id == card_id:
                            for r, score in zip(card.results, pass1_scores[card_id]):
                                r.ai_score = float(score)
                            break

            if is_tty:
                print(
                    f"\r  [{completed}/{len(non_dud_cards)}] Scored {card_id} (pass 2, {elapsed:.1f}s)   ",
                    end="", flush=True, file=sys.stderr,
                )
            else:
                print(
                    f"  [{completed}/{len(non_dud_cards)}] {card_id} scored (pass 2, {elapsed:.1f}s)",
                    file=sys.stderr,
                )

        if is_tty:
            print(file=sys.stderr)

    # Cards that failed both passes keep ai_score = -1
    scored = sum(1 for c in card_results if any(r.ai_score >= 0 for r in c.results))
    print(f"  AI scoring complete: {scored}/{total_cards} cards scored", file=sys.stderr)


# ---------------------------------------------------------------------------
# HTML report generation
# ---------------------------------------------------------------------------

CSS = """
:root {
    --bg: #ffffff;
    --fg: #1a1a1a;
    --bg-alt: #f5f5f5;
    --border: #ddd;
    --accent: #2563eb;
    --green: #22c55e;
    --red: #ef4444;
    --yellow: #eab308;
    --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    --mono: "SF Mono", "Fira Code", "Fira Mono", Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: dark) {
    :root {
        --bg: #1a1a1a;
        --fg: #e5e5e5;
        --bg-alt: #2a2a2a;
        --border: #444;
        --accent: #60a5fa;
    }
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: var(--font);
    background: var(--bg);
    color: var(--fg);
    line-height: 1.6;
    padding: 2rem;
    max-width: 1400px;
    margin: 0 auto;
}
h1 { font-size: 1.5rem; margin-bottom: 0.5rem; }
h2 { font-size: 1.2rem; margin: 1.5rem 0 0.5rem; }
.meta { color: #888; font-size: 0.85rem; margin-bottom: 1.5rem; }
.meta span { margin-right: 1.5rem; }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
    margin-bottom: 2rem;
}
th, td {
    padding: 0.4rem 0.6rem;
    border: 1px solid var(--border);
    text-align: left;
    white-space: nowrap;
}
th {
    background: var(--bg-alt);
    position: sticky;
    top: 0;
    z-index: 1;
}
tr:hover { background: var(--bg-alt); }
.num { text-align: right; font-variant-numeric: tabular-nums; }
.best { font-weight: bold; }
.card-images {
    display: flex;
    gap: 1rem;
    margin-bottom: 1.5rem;
    flex-wrap: wrap;
}
.card-images img {
    max-width: 300px;
    border: 1px solid var(--border);
    border-radius: 4px;
}
.text-cell {
    white-space: pre-wrap;
    word-break: break-word;
    max-width: 500px;
    max-height: 150px;
    overflow-y: auto;
    font-family: var(--mono);
    font-size: 0.75rem;
    line-height: 1.4;
}
.text-cell.expanded { max-height: none; }
.toggle-btn {
    background: none;
    border: 1px solid var(--border);
    border-radius: 3px;
    padding: 0.1rem 0.4rem;
    cursor: pointer;
    font-size: 0.7rem;
    color: var(--accent);
    margin-top: 0.2rem;
}
nav {
    display: flex;
    gap: 1rem;
    margin-bottom: 1.5rem;
    font-size: 0.9rem;
}
.heatmap-q4 { background-color: rgba(22, 163, 74, 0.20); }
.heatmap-q3 { background-color: rgba(34, 197, 94, 0.12); }
.heatmap-q2 { background-color: rgba(234, 179, 8, 0.12); }
.heatmap-q1 { background-color: rgba(239, 68, 68, 0.15); }
th.sortable {
    cursor: pointer;
    user-select: none;
}
th.sortable:hover {
    filter: brightness(0.95);
}
.filter-toolbar {
    display: flex;
    gap: 1rem;
    align-items: center;
    flex-wrap: wrap;
    margin-bottom: 1rem;
    font-size: 0.85rem;
}
.filter-toolbar label {
    display: flex;
    align-items: center;
    gap: 0.3rem;
}
.filter-toolbar select {
    padding: 0.2rem 0.4rem;
    border: 1px solid var(--border);
    border-radius: 3px;
    background: var(--bg);
    color: var(--fg);
    font-size: 0.85rem;
}
.filter-toolbar button {
    padding: 0.2rem 0.6rem;
    border: 1px solid var(--border);
    border-radius: 3px;
    background: var(--bg-alt);
    color: var(--fg);
    cursor: pointer;
    font-size: 0.85rem;
}
.card-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0;
    font-size: 0.85rem;
    margin-bottom: 2rem;
}
.card-grid td, .card-grid th {
    padding: 0.3rem 0.6rem;
}
.config-params {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 0.5rem;
    margin-bottom: 1.5rem;
    font-size: 0.85rem;
}
.config-params dt { font-weight: bold; color: #888; }
.config-params dd { margin: 0; }
"""

REPORT_JS = """
<script>
function toggleText(btn) {
    const cell = btn.previousElementSibling;
    cell.classList.toggle('expanded');
    btn.textContent = cell.classList.contains('expanded') ? 'collapse' : 'expand';
}

function sortTable(th) {
    const table = th.closest('table');
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    const colIdx = Array.from(th.parentElement.children).indexOf(th);
    const asc = th.dataset.sortDir !== 'asc';

    // Clear all sort indicators in this table
    th.parentElement.querySelectorAll('th').forEach(h => {
        h.textContent = h.textContent.replace(/ [\\u25B2\\u25BC]/g, '');
        delete h.dataset.sortDir;
    });
    th.dataset.sortDir = asc ? 'asc' : 'desc';
    th.textContent += asc ? ' \\u25B2' : ' \\u25BC';

    rows.sort((a, b) => {
        const aCell = a.cells[colIdx];
        const bCell = b.cells[colIdx];
        if (aCell.hasAttribute('data-value')) {
            const aVal = parseFloat(aCell.dataset.value);
            const bVal = parseFloat(bCell.dataset.value);
            return asc ? aVal - bVal : bVal - aVal;
        }
        return asc
            ? aCell.textContent.localeCompare(bCell.textContent)
            : bCell.textContent.localeCompare(aCell.textContent);
    });
    rows.forEach(row => tbody.appendChild(row));
}

function applyFilters() {
    const selects = document.querySelectorAll('.filter-select');
    const rows = document.querySelectorAll('#ranking-table tbody tr');
    rows.forEach(row => {
        let show = true;
        selects.forEach(sel => {
            if (sel.value && row.dataset[sel.dataset.axis] !== sel.value) {
                show = false;
            }
        });
        row.style.display = show ? '' : 'none';
    });
}

function resetFilters() {
    document.querySelectorAll('.filter-select').forEach(sel => sel.value = '');
    applyFilters();
}
</script>
"""


def _quartile_class(value: float, all_values: list[float], reverse: bool = False) -> str:
    """Return a CSS class based on which quartile *value* falls into.

    reverse=False: higher value = better (confidence) — top quartile = heatmap-q4
    reverse=True:  lower value = better (time) — bottom quartile = heatmap-q4
    """
    if len(all_values) < 4:
        return "heatmap-q3"
    q1, q2, q3 = statistics.quantiles(all_values, n=4)
    if reverse:
        # Lower is better
        if value <= q1:
            return "heatmap-q4"
        elif value <= q2:
            return "heatmap-q3"
        elif value <= q3:
            return "heatmap-q2"
        return "heatmap-q1"
    else:
        # Higher is better
        if value >= q3:
            return "heatmap-q4"
        elif value >= q2:
            return "heatmap-q3"
        elif value >= q1:
            return "heatmap-q2"
        return "heatmap-q1"


def _html_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _sortable_th(label: str, is_num: bool = False) -> str:
    """Generate a sortable <th> element."""
    cls = "num sortable" if is_num else "sortable"
    return f"<th class='{cls}' onclick='sortTable(this)'>{label}</th>"


def _has_ai_scores(card_results: list[CardResult]) -> bool:
    """Check if any result has an AI score."""
    return any(r.ai_score >= 0 for card in card_results for r in card.results)


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
    lines.append("<table id='ranking-table'>")
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
        "heatmap-q4": "Q4 (best)", "heatmap-q3": "Q3",
        "heatmap-q2": "Q2", "heatmap-q1": "Q1 (worst)",
    }
    _qt_label = {
        "heatmap-q4": "Q4 (fastest)", "heatmap-q3": "Q3",
        "heatmap-q2": "Q2", "heatmap-q1": "Q1 (slowest)",
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
        lines.append(f"    <button class='toggle-btn' onclick='toggleText(this)'>expand</button></td>")
        lines.append("</tr>")

    lines.append("</tbody></table>")
    lines.append("</body></html>")
    return "\n".join(lines)


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
        f"<h1>Config #{config_idx + 1}</h1>",
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
        lines.append(f"    <button class='toggle-btn' onclick='toggleText(this)'>expand</button></td>")
        lines.append("</tr>")

    lines.append("</tbody></table>")
    lines.append("</body></html>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CSV exports
# ---------------------------------------------------------------------------


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
        "library", "tessdata", "dpi", "psm", "preprocess", "dict_penalty",
        "conf_mean", "conf_std", "words_mean", "words_std",
        "unique_mean", "unique_std", "total_time_s",
    ]
    if has_ai:
        headers.extend(["ai_score_mean", "ai_score_std"])

    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for d in ranked:
            cfg = d["config"]
            row = [
                cfg.library, cfg.tessdata, cfg.dpi, cfg.psm, cfg.preprocess,
                cfg.dict_penalty,
                f"{d['conf_mean']:.2f}", f"{d['conf_std']:.2f}",
                f"{d['words_mean']:.2f}", f"{d['words_std']:.2f}",
                f"{d['unique_mean']:.2f}", f"{d['unique_std']:.2f}",
                f"{d['total_time']:.2f}",
            ]
            if has_ai:
                row.extend([
                    f"{d['ai_score_mean']:.2f}" if d["ai_scores"] else "",
                    f"{d['ai_score_std']:.2f}" if d["ai_scores"] else "",
                ])
            writer.writerow(row)


def write_detail_csv(
    path: Path,
    card_results: list[CardResult],
    has_ai: bool,
) -> None:
    """Write detail.csv — one row per (card x config) run."""
    headers = [
        "card_id", "library", "tessdata", "dpi", "psm", "preprocess",
        "dict_penalty", "word_count", "unique_words", "confidence", "elapsed_s",
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
                    card.card_id, cfg.library, cfg.tessdata, cfg.dpi, cfg.psm,
                    cfg.preprocess, cfg.dict_penalty,
                    r.word_count, r.unique_words,
                    f"{r.confidence:.2f}", f"{r.elapsed_s:.4f}",
                ]
                if has_ai:
                    row.append(f"{r.ai_score:.0f}" if r.ai_score >= 0 else "-1")
                writer.writerow(row)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

DEFAULT_OUTPUT = Path("_script_output") / "benchmark_ocr_configuration_quality"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="OCR Configuration Quality Benchmark — test Tesseract configurations on greeting card PDFs"
    )
    parser.add_argument("corpus", type=Path, help="Path to directory containing PDF files")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output directory for HTML reports (default: {DEFAULT_OUTPUT})",
    )
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
        "--ai-score",
        action="store_true",
        help="Enable AI scoring of OCR results using Claude API",
    )
    parser.add_argument(
        "--ai-model",
        type=str,
        default="claude-opus-4-6",
        help="Model for AI scoring (default: claude-opus-4-6)",
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
    args = parser.parse_args()

    corpus_path = args.corpus.expanduser().resolve()
    if not corpus_path.is_dir():
        print(f"Error: {corpus_path} is not a directory")
        sys.exit(1)

    configs = build_configs(args.configs)
    if not configs:
        print("No configs match the filter!")
        sys.exit(1)

    num_workers = max(1, args.workers)
    print(f"OCR Configuration Quality Benchmark")
    print(f"  Corpus: {corpus_path}")
    print(f"  Configs: {len(configs)}")
    print(f"  Workers: {num_workers}")
    if args.ai_score:
        print(f"  AI Scoring: enabled (model={args.ai_model}, concurrency={args.ai_concurrency})")
    print()

    output_dir = args.output
    output_dir.mkdir(parents=True, exist_ok=True)
    cards_dir = output_dir / "cards"
    cards_dir.mkdir(exist_ok=True)
    configs_dir = output_dir / "configs"
    configs_dir.mkdir(exist_ok=True)

    t0 = time.monotonic()
    card_results = run_benchmark(corpus_path, configs, output_dir, num_workers)
    elapsed_total = time.monotonic() - t0

    # AI scoring (after benchmark, before report generation)
    if args.ai_score:
        ai_t0 = time.monotonic()
        asyncio.run(score_all_cards(
            card_results,
            model=args.ai_model,
            concurrency=args.ai_concurrency,
            dud_threshold=args.dud_threshold,
        ))
        ai_elapsed = time.monotonic() - ai_t0
        print(f"  AI scoring time: {ai_elapsed:.1f}s", file=sys.stderr)

    print(f"\nGenerating reports...")

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

    # Compute config stats (shared by summary + config pages)
    config_stats = _compute_config_stats(card_results, actual_configs)

    # Ranked configs for config page navigation
    if has_ai:
        ranked_configs = [
            d["config"]
            for d in sorted(config_stats.values(), key=lambda d: d["ai_score_mean"], reverse=True)
        ]
    else:
        ranked_configs = [
            d["config"]
            for d in sorted(config_stats.values(), key=lambda d: d["conf_mean"], reverse=True)
        ]

    # Summary page
    summary_html = generate_summary_html(
        card_results, actual_configs, corpus_path, elapsed_total, config_stats,
    )
    (output_dir / "index.html").write_text(summary_html)

    # Per-card pages
    for idx, card in enumerate(card_results):
        card_html = generate_card_html(card, idx, all_card_ids)
        (cards_dir / f"{card.card_id}.html").write_text(card_html)

    # Per-config pages
    for idx, cfg in enumerate(ranked_configs):
        config_html = generate_config_html(
            cfg, card_results, idx, ranked_configs, config_stats,
        )
        (configs_dir / f"{cfg.slug}.html").write_text(config_html)

    # CSV exports
    write_summary_csv(output_dir / "summary.csv", config_stats, has_ai)
    write_detail_csv(output_dir / "detail.csv", card_results, has_ai)

    print(f"  Summary:  {output_dir / 'index.html'}")
    print(f"  Cards:    {len(card_results)} pages in {cards_dir}/")
    print(f"  Configs:  {len(ranked_configs)} pages in {configs_dir}/")
    print(f"  CSV:      summary.csv, detail.csv")
    print(f"  Total time: {elapsed_total:.1f}s")
    print(f"\nOpen {output_dir / 'index.html'} in a browser to view results.")


if __name__ == "__main__":
    main()
