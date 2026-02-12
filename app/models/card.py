from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional
from PIL import Image


class Confidence(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    MANUAL = "manual"
    NONE = "none"


@dataclass
class CardResult:
    id: int  # Unique, monotonically increasing identifier
    pdf_path: Path
    family_name: str = ""
    confidence: Confidence = Confidence.NONE
    alternates: list[str] = field(default_factory=list)  # Just names for backward compat
    candidates: list[tuple[int, str, str, str]] = field(default_factory=list)  # (id, name, method, confidence)
    ocr_text: str = ""
    preview_image: Optional[Image.Image] = None  # first page (for AI analysis)
    page_images: list[Image.Image] = field(default_factory=list)  # all pages
    manual_override: str = ""
    ai_analyzed: bool = False
    file_hash: str = ""
    original_confidence: Optional[Confidence] = None  # Confidence before manual override
    remove_family: bool = False  # If True, omit "Family" suffix from filename
    selected_candidate_id: Optional[int] = None  # ID of selected candidate from DB (None if manual or missing)
    method: str = "missing"  # 'ocr' | 'ai' | 'manual' | 'missing'

    @property
    def display_name(self) -> str:
        if self.manual_override:
            return self.manual_override
        return self.family_name

    @property
    def filename(self) -> str:
        return self.pdf_path.name

    def target_filename(self, year: str) -> str:
        name = self.display_name
        if not name:
            return ""
        # Only append "Family" if checkbox is not checked and name doesn't already end with it
        if not self.remove_family and not name.lower().endswith("family"):
            name = f"{name} Family"
        return f"Holiday Cards {year} - {name}.pdf"
