"""Rich display helpers for live status table."""

from __future__ import annotations

from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from scripts.generate_sample_cards.models import CardJob


def build_status_table(jobs: list[CardJob], image_src: str) -> Table:
    """Build a rich Table showing the current status of all card jobs."""
    # Dynamic column widths based on actual data
    family_w = max((len(j.family_name) for j in jobs), default=6) + 1
    holiday_w = max((len(j.holiday) for j in jobs), default=7) + 1
    style_w = max((len(j.style) for j in jobs), default=5) + 1

    table = Table(show_header=True, header_style="bold", pad_edge=False)
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Family", no_wrap=True, width=family_w)
    table.add_column("Holiday", no_wrap=True, width=holiday_w)
    table.add_column("Style", no_wrap=True, width=style_w)
    table.add_column("Back", width=8)
    table.add_column("   Status", no_wrap=True, min_width=22)

    # Spinner renders as [frame_char][text], offsetting text by ~3 chars
    # (1 for spinner + 2 spaces in text). Pad non-spinner cells to match.
    _spinner_pad = "   "

    status_styles: dict[str, tuple[str, str]] = {
        "waiting": ("dim", "Waiting"),
        "gen_front": ("yellow", "Generating front"),
        "gen_back": ("yellow", "Generating back"),
        "composing": ("cyan", "Composing PDF"),
        "done": ("green", "Done"),
        "error": ("red", "Error"),
        "rate_limited": ("magenta", "Rate limited"),
    }

    for job in jobs:
        style, label = status_styles.get(job.status, ("white", job.status))

        # Active/rate-limited jobs get a spinner in the Status cell
        if job.status in ("gen_front", "gen_back", "composing", "rate_limited"):
            detail_text = f" ({job.detail})" if job.detail else ""
            status_cell: Spinner | Text = Spinner("dots", text=Text(f"  {label}{detail_text}", style=style))
        else:
            status_cell = Text(f"{_spinner_pad}{label}", style=style)
            if job.detail:
                status_cell.append(f" ({job.detail})", style=style)

        table.add_row(
            str(job.index),
            job.family_name,
            job.holiday,
            job.style,
            job.back_page,
            status_cell,
        )

    # Summary line
    done = sum(1 for j in jobs if j.status == "done")
    errors = sum(1 for j in jobs if j.status == "error")
    active = sum(1 for j in jobs if j.status in ("gen_front", "gen_back", "composing"))
    rate_limited = sum(1 for j in jobs if j.status == "rate_limited")
    waiting = sum(1 for j in jobs if j.status == "waiting")
    caption_parts: list[str] = []
    if done:
        caption_parts.append(f"[green]{done}[/] done")
    if active:
        caption_parts.append(f"[yellow]{active}[/] active")
    if waiting:
        caption_parts.append(f"[dim]{waiting}[/] waiting")
    if rate_limited:
        caption_parts.append(f"[magenta]{rate_limited}[/] rate-limited")
    if errors:
        caption_parts.append(f"[red]{errors}[/] errors")
    table.caption = f"  [{image_src}]  " + " | ".join(caption_parts)

    return table
