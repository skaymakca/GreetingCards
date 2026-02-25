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
    family_surname: str
    family_members: list[FamilyMember]
    name_format: str
    holiday: str
    greeting_text: str
    backstory_blurb: str
    visual_style: str
    color_scheme: list[str]  # 2-3 hex colors
    page_count: int  # 1 or 2
    filename: str
    image_prompt: str

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
            family_surname=str(d["family_surname"]),
            family_members=members,
            name_format=str(d["name_format"]),
            holiday=str(d["holiday"]),
            greeting_text=str(d["greeting_text"]),
            backstory_blurb=str(d["backstory_blurb"]),
            visual_style=str(d["visual_style"]),
            color_scheme=[str(c) for c in d["color_scheme"]],
            page_count=int(d["page_count"]),
            filename=str(d["filename"]),
            image_prompt=str(d["image_prompt"]),
        )


@dataclass
class CardJob:
    """Tracks the status of one card being processed."""

    index: int  # 1-based display index
    filename: str
    pages: int
    style: str
    status: str = "waiting"  # waiting, gen_front, gen_back, composing, done, error, rate_limited
    detail: str = ""  # extra info (e.g., "8.2s", error message)

    def set(self, status: str, detail: str = "") -> None:
        self.status = status
        self.detail = detail
