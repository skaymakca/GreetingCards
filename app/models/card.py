from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional
from PIL import Image


class Confidence(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


@dataclass
class CardResult:
    pdf_path: Path
    family_name: str = ""
    confidence: Confidence = Confidence.NONE
    alternates: list[str] = field(default_factory=list)
    ocr_text: str = ""
    preview_image: Optional[Image.Image] = None
    manual_override: str = ""
    ai_analyzed: bool = False

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
        if not name.lower().endswith("family"):
            name = f"{name} Family"
        return f"Holiday Cards {year} - {name}.pdf"
