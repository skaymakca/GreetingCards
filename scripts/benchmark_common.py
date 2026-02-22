"""Shared utilities for benchmark scripts.

Provides PDF rendering, image preprocessing pipelines, image serialization,
file discovery, HTML report scaffolding, statistics helpers, OCR configuration,
tessdata management, OCR engine wrappers, and job generation used across
the OCR configuration quality benchmark, preprocessing concurrency benchmark,
and OCR concurrency benchmark.
"""

from __future__ import annotations

import base64
import io
import itertools
import os
import statistics
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import fitz  # type: ignore[import-untyped]
from PIL import Image, ImageChops, ImageFilter, ImageOps

# Optional imports — fail gracefully if not installed
try:
    import cv2
    import numpy as np

    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False

try:
    import pytesseract  # type: ignore[import-untyped]

    HAS_PYTESSERACT = True
except ImportError:
    HAS_PYTESSERACT = False

try:
    import tesserocr  # type: ignore[import-untyped]

    HAS_TESSEROCR = True
except ImportError:
    HAS_TESSEROCR = False


# ---------------------------------------------------------------------------
# OCR Configuration
# ---------------------------------------------------------------------------


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
        return f"{self.library}-{self.tessdata}-{self.dpi}-{self.psm}-{self.preprocess}-{self.dict_penalty}"

    @property
    def slug(self) -> str:
        return self.name.replace("/", "_")

    @classmethod
    def from_short_name(cls, s: str) -> Config:
        """Parse a short-name string like 'tesserocr-default-200-3-pillow-0.15'."""
        parts = s.split("-")
        if len(parts) != 6:
            raise ValueError(
                f"Expected 6 dash-separated parts in '{s}', got {len(parts)}. "
                f"Format: library-tessdata-dpi-psm-preprocess-penalty"
            )
        return cls(
            library=parts[0],
            tessdata=parts[1],
            dpi=int(parts[2]),
            psm=int(parts[3]),
            preprocess=parts[4],
            dict_penalty=float(parts[5]),
        )


# ---------------------------------------------------------------------------
# tessdata management
# ---------------------------------------------------------------------------

TESSDATA_BEST_URL = (
    "https://github.com/tesseract-ocr/tessdata_best/raw/main/eng.traineddata"
)
TESSDATA_BEST_DIR = Path(__file__).parent / "tessdata_best"


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
# PDF rendering
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
        img = img.resize(new_size, Image.LANCZOS)  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


# ---------------------------------------------------------------------------
# Image serialization (for multiprocessing)
# ---------------------------------------------------------------------------


def image_to_png_bytes(img: Image.Image) -> bytes:
    """Serialize a PIL Image to PNG bytes for passing through multiprocessing queues."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def png_bytes_to_image(data: bytes) -> Image.Image:
    """Deserialize PNG bytes back to a PIL Image."""
    return Image.open(io.BytesIO(data))


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
    if not HAS_OPENCV:
        raise RuntimeError("opencv-python-headless required for clahe preprocessing")
    gray = np.array(ImageOps.grayscale(img))  # pyright: ignore[reportPossiblyUnboundVariable]
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))  # pyright: ignore[reportPossiblyUnboundVariable]
    enhanced = clahe.apply(gray)
    denoised = cv2.fastNlMeansDenoising(enhanced, h=10)  # pyright: ignore[reportPossiblyUnboundVariable]
    thresh_type = cv2.ADAPTIVE_THRESH_GAUSSIAN_C  # pyright: ignore[reportPossiblyUnboundVariable]
    binary = cv2.adaptiveThreshold(denoised, 255, thresh_type, cv2.THRESH_BINARY, 11, 2)  # pyright: ignore[reportPossiblyUnboundVariable]
    return Image.fromarray(binary)


def preprocess_otsu(img: Image.Image) -> Image.Image:
    """Otsu threshold + sharpen (OpenCV)."""
    if not HAS_OPENCV:
        raise RuntimeError("opencv-python-headless required for otsu preprocessing")
    gray = np.array(ImageOps.grayscale(img))  # pyright: ignore[reportPossiblyUnboundVariable]
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)  # pyright: ignore[reportPossiblyUnboundVariable]
    result = Image.fromarray(binary)
    return result.filter(ImageFilter.SHARPEN)


# 3 distinct preprocessing pipelines.  Sauvola thresholding is a Tesseract-side
# parameter (not a preprocessing step), so it uses the same code as pillow.
PREPROCESS_FNS: dict[str, Callable[..., Image.Image]] = {
    "pillow": preprocess_pillow,
    "clahe": preprocess_clahe,
    "otsu": preprocess_otsu,
}


# ---------------------------------------------------------------------------
# OCR engines
# ---------------------------------------------------------------------------

# Map integer PSM values to tesserocr enum members (tesserocr.PSM can't be
# constructed from an int).
TESSEROCR_PSM_MAP: dict[int, object] = {}
if HAS_TESSEROCR:
    _psm = tesserocr.PSM  # pyright: ignore[reportPossiblyUnboundVariable]
    TESSEROCR_PSM_MAP = {
        0: _psm.OSD_ONLY,
        1: _psm.AUTO_OSD,
        2: _psm.AUTO_ONLY,
        3: _psm.AUTO,
        4: _psm.SINGLE_COLUMN,
        5: _psm.SINGLE_BLOCK_VERT_TEXT,
        6: _psm.SINGLE_BLOCK,
        7: _psm.SINGLE_LINE,
        8: _psm.SINGLE_WORD,
        9: _psm.CIRCLE_WORD,
        10: _psm.SINGLE_CHAR,
        11: _psm.SPARSE_TEXT,
        12: _psm.SPARSE_TEXT_OSD,
        13: _psm.RAW_LINE,
    }
    del _psm


def build_tesseract_config(cfg: Config) -> str:
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
    config_str = build_tesseract_config(cfg)
    try:
        data = pytesseract.image_to_data(img, config=config_str, output_type=pytesseract.Output.DICT)  # pyright: ignore[reportPossiblyUnboundVariable]
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

    psm_enum = TESSEROCR_PSM_MAP.get(cfg.psm)
    if psm_enum is None:
        raise ValueError(f"Unknown PSM value: {cfg.psm}")

    with tesserocr.PyTessBaseAPI(**kwargs) as api:  # pyright: ignore[reportPossiblyUnboundVariable]
        api.SetPageSegMode(psm_enum)  # pyright: ignore[reportArgumentType]
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
# File discovery
# ---------------------------------------------------------------------------


def find_pdfs(corpus_path: Path) -> list[Path]:
    """Find all PDF files in the corpus directory."""
    pdfs = sorted(corpus_path.glob("*.pdf"))
    if not pdfs:
        pdfs = sorted(corpus_path.rglob("*.pdf"))
    return pdfs


# ---------------------------------------------------------------------------
# Job generation
# ---------------------------------------------------------------------------


def build_jobs(
    pdf_paths: list[Path],
    concurrency_level: int,
    min_repeats: int = 3,
) -> list[tuple[int, Path]]:
    """Build a job list ensuring sufficient work for the concurrency level.

    Each file is processed at least `min_repeats` times.
    Total jobs >= 2 * concurrency_level.
    Files are repeated round-robin to meet both constraints.
    """
    n_files = len(pdf_paths)
    min_from_repeats = n_files * min_repeats
    min_from_concurrency = 2 * concurrency_level
    total_needed = max(min_from_repeats, min_from_concurrency)

    jobs = []
    cycle = itertools.cycle(pdf_paths)
    for i in range(total_needed):
        jobs.append((i, next(cycle)))
    return jobs


# ---------------------------------------------------------------------------
# Statistics helpers
# ---------------------------------------------------------------------------


def mean_std(values: list[float]) -> tuple[float, float]:
    """Return (mean, stdev) for a list of values. Returns (0, 0) if empty."""
    if not values:
        return 0.0, 0.0
    m = statistics.mean(values)
    sd = statistics.pstdev(values) if len(values) > 1 else 0.0
    return m, sd


def fmt_mean_std(mean: float, std: float, fmt: str = ".1f") -> str:
    """Format mean +/- std as a string."""
    return f"{mean:{fmt}} &plusmn; {std:{fmt}}"


# ---------------------------------------------------------------------------
# HTML report scaffolding
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
    const rows = document.querySelectorAll('.filterable-table tbody tr');
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


def html_page(title: str, body: str, extra_css: str = "") -> str:
    """Wrap body content in a full HTML document with CSS and JS."""
    css = CSS
    if extra_css:
        css += "\n" + extra_css
    return (
        "<!DOCTYPE html>\n"
        "<html lang='en'>\n"
        "<head>\n"
        "<meta charset='utf-8'>\n"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>\n"
        f"<title>{html_escape(title)}</title>\n"
        f"<style>{css}</style>\n"
        f"{REPORT_JS}\n"
        "</head>\n"
        f"<body>\n{body}\n</body>\n"
        "</html>"
    )


def html_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def sortable_th(label: str, is_num: bool = False) -> str:
    """Generate a sortable <th> element."""
    cls = "num sortable" if is_num else "sortable"
    return f"<th class='{cls}' onclick='sortTable(this)'>{label}</th>"


def quartile_class(value: float, all_values: list[float], reverse: bool = False) -> str:
    """Return a CSS class based on which quartile *value* falls into.

    reverse=False: higher value = better — top quartile = heatmap-q4
    reverse=True:  lower value = better — bottom quartile = heatmap-q4
    """
    if len(all_values) < 4:
        return "heatmap-q3"
    q1, q2, q3 = statistics.quantiles(all_values, n=4)
    if reverse:
        if value <= q1:
            return "heatmap-q4"
        elif value <= q2:
            return "heatmap-q3"
        elif value <= q3:
            return "heatmap-q2"
        return "heatmap-q1"
    else:
        if value >= q3:
            return "heatmap-q4"
        elif value >= q2:
            return "heatmap-q3"
        elif value >= q1:
            return "heatmap-q2"
        return "heatmap-q1"
