"""Data models for sample card generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class FamilyMember:
    first_name: str
    role: str  # "parent", "child", "pet"
    age: int | None = None


@dataclass
class CardSpec:
    family_name: str
    family_members: list[FamilyMember]
    name_format: str  # subtitle / "from" line (LLM-generated)
    holiday: str
    greeting_text: str
    backstory_blurb: str
    visual_style: str
    color_scheme: list[str]  # 2-3 hex colors
    page_count: int  # 1 or 2
    back_page_type: str | None  # "blurb" or "photo" for 2-page, None for 1-page
    filename: str
    image_prompt: str
    back_greeting: str  # short greeting for photo-type back pages
    back_photo_mode: str  # "single" or "collage" for photo-type back pages
    back_image_prompt: str  # image prompt for photo-type back pages

    @staticmethod
    def from_dict(d: dict[str, Any]) -> CardSpec:
        members = [
            FamilyMember(
                first_name=str(m["first_name"]),
                role=str(m["role"]),
                age=int(m["age"]) if m.get("age") is not None else None,
            )
            for m in d["family_members"]
        ]
        return CardSpec(
            family_name=str(d["family_name"]),
            family_members=members,
            name_format=str(d["name_format"]),
            holiday=str(d["holiday"]),
            greeting_text=str(d["greeting_text"]),
            backstory_blurb=str(d.get("backstory_blurb", "")),
            visual_style=str(d["visual_style"]),
            color_scheme=[str(c) for c in d["color_scheme"]],
            page_count=int(d["page_count"]),
            back_page_type=d.get("back_page_type"),
            filename=str(d["filename"]),
            image_prompt=str(d["image_prompt"]),
            back_greeting=str(d.get("back_greeting", "")),
            back_photo_mode=str(d.get("back_photo_mode", "")),
            back_image_prompt=str(d.get("back_image_prompt", "")),
        )


@dataclass
class CardJob:
    """Tracks the status of one card being processed."""

    index: int  # 1-based display index
    family_name: str
    holiday: str
    style: str
    back_page: str  # "none", "blurb", "single", or "collage"
    status: str = "waiting"  # waiting, gen_front, gen_back, composing, done, error, rate_limited
    detail: str = ""  # extra info (e.g., "8.2s", error message)

    def set(self, status: str, detail: str = "") -> None:
        self.status = status
        self.detail = detail
