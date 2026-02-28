"""Phase 1c — generate card subtitles (\"from\" lines) in batched Claude calls."""

from __future__ import annotations

import asyncio
from typing import Any

import anthropic
from anthropic.types import MessageParam

from scripts.generate_sample_cards.spec_generators.utils import extract_json

SUBTITLE_PROMPT = """\
For each family below, generate a natural "from" line / subtitle for their \
holiday greeting card. Use a random sampling of ALL the styles below, plus \
your own creative riffs on them. Every style should appear at least once \
across a batch — don't over-index on any single pattern.

Base styles (use all of these, then riff):
- "The Garcias"
- "The Kim Family"
- "Bob & Sue Martinez"
- "Bob, Sue, Lily (8) & Max (5) Johnson"
- "From the Desk of Maria García"
- "Anderson"
- "The Nguyens — Dan, Lisa & Coco"

Families:
{families_text}

Return a JSON array of strings (one subtitle per family), in the same order.

Return ONLY the JSON array, no other text."""

BATCH_SIZE = 20


async def _generate_batch(
    client: anthropic.AsyncAnthropic,
    families: list[tuple[str, str, str]],
    model: str,
) -> list[str]:
    """One Claude call for a batch of (family_name, family_size_hint, holiday) tuples."""
    families_text = "\n".join(
        f"{i + 1}. {name} — {hint} — {holiday}" for i, (name, hint, holiday) in enumerate(families)
    )
    response = await client.messages.create(
        model=model,
        max_tokens=2048,
        messages=[
            MessageParam(
                role="user",
                content=SUBTITLE_PROMPT.format(families_text=families_text),
            )
        ],
    )
    text = response.content[0].text  # type: ignore[union-attr]
    return [str(s) for s in extract_json(text)]  # type: ignore[union-attr]


async def generate_subtitles_async(
    client: anthropic.AsyncAnthropic,
    cards: list[dict[str, Any]],
    model: str,
) -> list[str]:
    """Batched concurrent calls → one subtitle per card."""
    families = [(str(c["family_name"]), str(c["family_size_hint"]), str(c["holiday"])) for c in cards]

    # Split into batches
    batches: list[list[tuple[str, str, str]]] = [
        families[i : i + BATCH_SIZE] for i in range(0, len(families), BATCH_SIZE)
    ]

    # Fire batches concurrently
    results = await asyncio.gather(*(_generate_batch(client, batch, model) for batch in batches))

    # Flatten
    subtitles: list[str] = []
    for batch_result in results:
        subtitles.extend(batch_result)

    # Pad with fallback if Claude returned fewer than expected
    while len(subtitles) < len(cards):
        idx = len(subtitles)
        subtitles.append(f"The {cards[idx]['family_name']} Family")

    return subtitles[: len(cards)]
