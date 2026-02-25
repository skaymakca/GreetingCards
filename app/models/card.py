from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Final, Literal

from PIL import Image

from app.core.name_formatting import sanitize_for_filename

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

    _COLOR_MAP: dict[Confidence, str]
    _TOOLTIP_MAP: dict[Confidence, str]

    def color(self) -> str:
        """Return the color for this confidence level."""
        return self._COLOR_MAP[self]

    def tooltip(self) -> str:
        """Return the tooltip description for this confidence level."""
        return self._TOOLTIP_MAP[self]


# Class-level lookup tables (avoid dict recreation on every call)
Confidence._COLOR_MAP = {
    Confidence.HIGH: "#34C759",  # SUCCESS green
    Confidence.MEDIUM: "#FF9500",  # WARNING orange
    Confidence.LOW: "#FF3B30",  # ERROR red
    Confidence.MANUAL: "#1E90FF",  # MANUAL_BLUE
    Confidence.NONE: "#6E6E73",  # TEXT_SECONDARY gray
}
Confidence._TOOLTIP_MAP = {
    Confidence.HIGH: "High confidence — strong pattern match or AI result",
    Confidence.MEDIUM: "Medium confidence — partial pattern match",
    Confidence.LOW: "Low confidence — weak/fallback match",
    Confidence.MANUAL: "Manually entered name",
    Confidence.NONE: "No name extracted",
}


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
    id: int  # Unique, monotonically increasing identifier
    file_paths: list[Path] = field(default_factory=list)  # All paths with same content
    primary_path: Path = field(default_factory=Path)  # First path found
    family_name: str = ""
    confidence: Confidence = Confidence.NONE
    alternates: list[str] = field(default_factory=list)  # Just names for backward compat
    candidates: list[CandidateInfo] = field(default_factory=list)
    ocr_text: str = ""
    preview_image: Image.Image | None = None  # first page (for AI analysis)
    page_images: list[Image.Image] = field(default_factory=list)  # all pages
    manual_override: str = ""
    ai_analyzed: bool = False
    file_hash: str = ""
    original_confidence: Confidence | None = None  # Confidence before manual override
    remove_family: bool = False  # If True, omit "Family" suffix from filename
    selected_candidate_id: int | None = None  # ID of selected candidate from DB (None if manual or missing)
    method: MethodStr = "missing"
    error: str = ""  # Non-empty when PDF processing failed (corrupt, encrypted, etc.)

    @property
    def pdf_path(self) -> Path:
        """Backward compatibility - returns primary path."""
        return self.primary_path

    @property
    def display_name(self) -> str:
        if self.manual_override:
            return self.manual_override
        return self.family_name

    @property
    def filename(self) -> str:
        return self.primary_path.name

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
