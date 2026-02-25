"""Claude API — generate card specifications with async concurrent calls.

Orchestrates the multiphase spec generation pipeline:
  Phase 1a: Unique family names (one call)
  Phase 1b: Color schemes (batched calls)
  Phase 1c: Subtitles / "from" lines (batched calls)
  Phase 2:  Per-card creative content (N concurrent calls)
"""

from __future__ import annotations

import asyncio
import random
from typing import Any

import anthropic
from rich.console import Console

from scripts.generate_sample_cards.image_generator import RateLimitGate
from scripts.generate_sample_cards.models import CardSpec
from scripts.generate_sample_cards.spec_generators import (
    assign_deterministic_fields,
    build_family_members,
    fill_filename,
    generate_card_content_async,
    generate_color_schemes_async,
    generate_family_names_async,
    generate_subtitles_async,
)


# noinspection PyTypeChecker
async def generate_card_specs_async(
    count: int,
    model: str,
    concurrency: int = 10,
) -> list[CardSpec]:
    """Generate card specifications using async concurrent Claude calls."""
    console = Console(highlight=False)
    client = anthropic.AsyncAnthropic()
    rng = random.Random()

    try:
        # Step 1: Deterministic field assignment
        cards = assign_deterministic_fields(count)

        # Phase 1a: Family names
        with console.status("[bold cyan]Generating family names..."):
            family_names = await generate_family_names_async(client, count, model)

        # Pad if we didn't get enough
        while len(family_names) < count:
            family_names.append(f"Family{len(family_names) + 1}")

        console.print(f"  Generated {len(family_names)} unique family names")

        # Assign family names and filenames
        for i, card in enumerate(cards):
            card["family_name"] = family_names[i]
            card["filename"] = fill_filename(
                str(card["filename_template"]),
                family_names[i],
                str(card["holiday"]),
                rng,
            )

        # Phase 1b: Color schemes
        with console.status("[bold cyan]Generating color schemes..."):
            color_schemes = await generate_color_schemes_async(client, cards, model)

        console.print(f"  Generated {len(color_schemes)} color palettes")

        for i, card in enumerate(cards):
            card["color_scheme"] = color_schemes[i]

        # Phase 1c: Subtitles / "from" lines
        with console.status("[bold cyan]Generating subtitles..."):
            subtitles = await generate_subtitles_async(client, cards, model)

        console.print(f"  Generated {len(subtitles)} subtitles")

        for i, card in enumerate(cards):
            card["subtitle"] = subtitles[i]

        # Phase 2: Per-card creative content (concurrent, semaphore-gated)
        semaphore = asyncio.Semaphore(concurrency)
        gate = RateLimitGate()

        with console.status(f"[bold cyan]Generating {count} card specs (concurrency={concurrency})..."):
            tasks = [
                generate_card_content_async(
                    client,
                    semaphore,
                    gate,
                    str(card["family_name"]),
                    card,
                    model,
                    console,
                    i,
                )
                for i, card in enumerate(cards)
            ]
            results = await asyncio.gather(*tasks)

        # Build CardSpec objects from successful results
        specs: list[CardSpec] = []
        for i, content in enumerate(results):
            if content is None:
                console.print(f"  [yellow]Skipping card {i + 1} ({family_names[i]}) — failed[/]")
                continue

            card = cards[i]
            raw_members: list[dict[str, Any]] = content.get("family_members", [])

            specs.append(
                CardSpec(
                    family_name=str(card["family_name"]),
                    family_members=build_family_members(raw_members),
                    name_format=str(card["subtitle"]),
                    holiday=str(card["holiday"]),
                    greeting_text=str(content.get("greeting_text", "")),
                    backstory_blurb=str(content.get("backstory_blurb", "")),
                    visual_style=str(card["visual_style"]),
                    color_scheme=card["color_scheme"],
                    page_count=int(card["page_count"]),
                    back_page_type=card.get("back_page_type"),
                    filename=str(card["filename"]),
                    image_prompt=str(content.get("image_prompt", "")),
                    back_greeting=str(content.get("back_greeting", "")),
                    back_photo_mode=str(card.get("back_photo_mode") or ""),
                    back_image_prompt=str(content.get("back_image_prompt", "")),
                )
            )

        two_page = sum(1 for s in specs if s.page_count == 2)
        one_page = sum(1 for s in specs if s.page_count == 1)
        console.print(f"  Generated {len(specs)}/{count} card specs ({one_page} 1-page, {two_page} 2-page)")
        return specs

    finally:
        await client.close()
