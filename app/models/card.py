from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Final, Literal

from PIL import Image

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


class RenameOutcome(Enum):
    """Machine-readable outcome of a single rename operation.

    Used by business logic (rename_filter, rename_service) for control flow.
    Display text is derived from these values in the GUI layer.
    """

    RENAMED = "renamed"
    ALREADY_CORRECT = "already_correct"
    SKIP_NO_NAME = "skip_no_name"
    SKIP_ERROR = "skip_error"
    ERROR_TARGET_EXISTS = "error_target_exists"
    ERROR_OS = "error_os"


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
    candidates: list[CandidateInfo] = field(default_factory=list)
    remove_family: bool = False
    selected_candidate_id: int | None = None
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


class RenameStatus(Enum):
    """Status of a rename plan item."""

    OK = "ok"
    SKIP_NO_NAME = "skip_no_name"
    SKIP_SAME = "skip_same"
    SKIP_ERROR = "skip_error"
    DUPLICATE = "duplicate"


# Backward-compat aliases
STATUS_OK: Final[RenameStatus] = RenameStatus.OK
STATUS_SKIP_NO_NAME: Final[RenameStatus] = RenameStatus.SKIP_NO_NAME
STATUS_SKIP_SAME: Final[RenameStatus] = RenameStatus.SKIP_SAME
STATUS_SKIP_ERROR: Final[RenameStatus] = RenameStatus.SKIP_ERROR
STATUS_DUPLICATE: Final[RenameStatus] = RenameStatus.DUPLICATE


@dataclass
class RenamePlanItem:
    """Item in a rename plan."""

    old_path: Path
    new_path: Path
    status: RenameStatus
    card: CardResult | None = None  # Back-reference to source card


@dataclass
class RenameResult:
    """Result of executing a rename operation.

    ``outcome`` is the machine-readable result. Display text should be
    derived from ``outcome`` in the presentation layer; ``message`` is
    retained for backward compatibility during transition.
    """

    old_path: Path
    new_path: Path
    success: bool
    message: str
    outcome: RenameOutcome = RenameOutcome.RENAMED
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

    # ── Processing artifacts ──
    preview_image: Image.Image | None = None
    page_images: list[Image.Image] = field(default_factory=list)
    ai_analyzed: bool = False
    error: str = ""

    # ── Transient selection state (not persisted) ──
    # Saved when manual edit starts; restored when candidate re-selected.
    original_confidence: Confidence | None = None

    # ── Properties (model) ──

    @property
    def pdf_path(self) -> Path:
        """Backward compatibility - returns primary path."""
        return self.primary_path

    # ── Properties ──

    @property
    def display_name(self) -> str:
        if self.manual_override:
            return self.manual_override
        return self.family_name

    @property
    def best_preview_images(self) -> list[Image.Image]:
        """Return the best available preview images, or empty list.

        Priority: multi-page images > single preview image > empty.
        """
        if self.page_images:
            return self.page_images
        if self.preview_image:
            return [self.preview_image]
        return []

    @property
    def filename(self) -> str:
        return self.primary_path.name
