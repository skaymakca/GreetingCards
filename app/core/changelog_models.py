"""Data models for changelog parsing and generation."""

from dataclasses import dataclass, field


@dataclass
class ChangelogVersion:
    """A parsed version entry from the changelog."""
    version: str        # e.g. "0.8.0"
    title: str          # e.g. "0.8.0 — Native macOS Interface"
    date: str           # e.g. "2026-02-19" or "in progress"
    body_html: str      # rendered HTML for the content area


@dataclass
class ChangelogGroup:
    """Versions grouped by MAJOR.MINOR for a single HTML page."""
    label: str                              # e.g. "0.9.x"
    slug: str                               # e.g. "0.9" (used for filename)
    versions: list[ChangelogVersion] = field(default_factory=list)
