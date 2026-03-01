from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Final, Literal

from PIL import Image

from app.core.naming.filename_safety import sanitize_for_filename

# Constrained value types for database-layer fields
MethodStr = Literal["ocr", "ai", "manual", "missing"]
ConfidenceStr = Literal["high", "medium", "low", "manual", "none"]
CandidateMethodStr = Literal["ocr", "ai"]
CandidateConfidenceStr = Literal["high", "medium", "low"]


class Confidence(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    MANUAL = "manual"
    NONE = "none"


@dataclass
class PdfWorkerResult:
    """Result from PDF processing worker (subprocess → main process).

    This dataclass is pickled across process boundaries by ProcessPoolExecutor.
    If pickling overhead becomes a bottleneck, consider using a shared memory
    approach or a more compact serialization format.
    """

    pdf_path: str
    file_hash: str | None = None
    family_name: str = ""
    confidence: ConfidenceStr = "none"
    method: MethodStr = "missing"
    alternates: list[str] = field(default_factory=list)
    candidates: list[CandidateInfo] = field(default_factory=list)
    remove_family: bool = False
    selected_candidate_id: int | None = None
    ocr_text: str = ""
    error: str = ""
    preview_image_bytes: bytes | None = None
    page_images_bytes: list[bytes] = field(default_factory=list)


@dataclass
class CandidateInfo:
    """Represents a candidate family name from database."""

    id: int
    family_name: str
    method: CandidateMethodStr
    confidence: CandidateConfidenceStr


@dataclass
class CardState:
    """Complete card state from database for display."""

    display_name: str
    method: MethodStr
    confidence: ConfidenceStr
    candidates: list[CandidateInfo]
    remove_family: bool
    selected_candidate_id: int | None


@dataclass
class NameMatch:
    """Represents a family name extracted from OCR."""

    name: str
    confidence: Confidence


# Rename plan status
RenameStatusStr = Literal["ok", "skip_no_name", "skip_same", "skip_error", "duplicate"]
STATUS_OK: Final[RenameStatusStr] = "ok"
STATUS_SKIP_NO_NAME: Final[RenameStatusStr] = "skip_no_name"
STATUS_SKIP_SAME: Final[RenameStatusStr] = "skip_same"
STATUS_SKIP_ERROR: Final[RenameStatusStr] = "skip_error"
STATUS_DUPLICATE: Final[RenameStatusStr] = "duplicate"


@dataclass
class RenamePlanItem:
    """Item in a rename plan."""

    old_path: Path
    new_path: Path
    status: RenameStatusStr
    card: CardResult | None = None  # Back-reference to source card


@dataclass
class RenameResult:
    """Result of executing a rename operation."""

    old_path: Path
    new_path: Path
    success: bool
    message: str
    card: CardResult | None = None  # Back-reference to source card


@dataclass
class CardResult:
    # ── Identity ──
    id: int
    file_paths: list[Path] = field(default_factory=list)
    primary_path: Path = field(default_factory=Path)
    file_hash: str = ""

    # ── Name resolution (persisted to DB) ──
    family_name: str = ""
    confidence: Confidence = Confidence.NONE
    method: MethodStr = "missing"
    candidates: list[CandidateInfo] = field(default_factory=list)
    selected_candidate_id: int | None = None
    manual_override: str = ""
    remove_family: bool = False
    alternates: list[str] = field(default_factory=list)

    # ── Processing artifacts ──
    ocr_text: str = ""
    preview_image: Image.Image | None = None
    page_images: list[Image.Image] = field(default_factory=list)
    ai_analyzed: bool = False
    error: str = ""

    # ── UI state (not persisted, GUI bookkeeping) ──
    ui_original_confidence: Confidence | None = None

    # ── Properties (model) ──

    @property
    def pdf_path(self) -> Path:
        """Backward compatibility - returns primary path."""
        return self.primary_path

    def target_filename(self, year: str) -> str:
        year = year.strip()
        if not year:
            return ""
        name = self.display_name.strip() if self.display_name else ""
        if not name:
            return ""
        # Sanitize filesystem-invalid characters (safety net)
        name = sanitize_for_filename(name)
        # Only append "Family" if checkbox is not checked and name doesn't already end with it
        if not self.remove_family and not name.lower().endswith("family"):
            name = f"{name} Family"
        return f"Holiday Cards {year} - {name}.pdf"

    # ── Properties (view convenience) ──

    @property
    def display_name(self) -> str:
        if self.manual_override:
            return self.manual_override
        return self.family_name

    @property
    def filename(self) -> str:
        return self.primary_path.name
