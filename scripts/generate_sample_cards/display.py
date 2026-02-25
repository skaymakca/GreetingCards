"""Rich display helpers for live status table."""

from __future__ import annotations

from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from scripts.generate_sample_cards.models import CardJob


def build_status_table(jobs: list[CardJob], image_src: str) -> Table:
    """Build a rich Table showing the current status of all card jobs."""
    table = Table(show_header=True, header_style="bold", pad_edge=False)
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Filename", no_wrap=True, max_width=40)
    table.add_column("Pages", width=5, justify="center")
    table.add_column("Style", width=13)
    table.add_column("Status", no_wrap=True)

    status_styles: dict[str, tuple[str, str]] = {
        "waiting": ("dim", "..."),
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
            status_cell: Spinner | Text = Spinner("dots", text=Text(f" {label}{detail_text}", style=style))
        else:
            status_cell = Text(label, style=style)
            if job.detail:
                status_cell.append(f" ({job.detail})", style=style)

        table.add_row(
            str(job.index),
            job.filename,
            str(job.pages),
            job.style,
            status_cell,
        )

    # Summary line
    done = sum(1 for j in jobs if j.status == "done")
    errors = sum(1 for j in jobs if j.status == "error")
    active = sum(1 for j in jobs if j.status in ("gen_front", "gen_back", "composing"))
    rate_limited = sum(1 for j in jobs if j.status == "rate_limited")
    caption_parts = [f"[green]{done}[/] done"]
    if active:
        caption_parts.append(f"[yellow]{active}[/] active")
    if rate_limited:
        caption_parts.append(f"[magenta]{rate_limited}[/] rate-limited")
    if errors:
        caption_parts.append(f"[red]{errors}[/] errors")
    table.caption = f"  [{image_src}]  " + " | ".join(caption_parts)

    return table
