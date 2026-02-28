"""Phase 1b — generate color schemes in batched concurrent Claude calls."""

from __future__ import annotations

import asyncio
from typing import Any

import anthropic
from anthropic.types import MessageParam

from scripts.generate_sample_cards.spec_generators.utils import extract_json

COLOR_SCHEME_PROMPT = """\
For each holiday + visual style pair below, generate a color palette of 2-3 \
hex color strings that are holiday-appropriate and visually appealing.

Pairs:
{pairs_text}

Return a JSON array of arrays (one palette per pair), in the same order.
Example: [["#1a3c5e", "#c4a35a", "#f5f0e1"], ["#d4373c", "#2d5a27"]]

Return ONLY the JSON array, no other text."""

BATCH_SIZE = 20


async def _generate_batch(
    client: anthropic.AsyncAnthropic,
    pairs: list[tuple[str, str]],
    model: str,
) -> list[list[str]]:
    """One Claude call for a batch of (holiday, visual_style) pairs."""
    pairs_text = "\n".join(f"{i + 1}. {holiday} / {style}" for i, (holiday, style) in enumerate(pairs))
    response = await client.messages.create(
        model=model,
        max_tokens=2048,
        messages=[
            MessageParam(
                role="user",
                content=COLOR_SCHEME_PROMPT.format(pairs_text=pairs_text),
            )
        ],
    )
    text = response.content[0].text  # type: ignore[union-attr]
    return list(extract_json(text))  # type: ignore[return-value]


async def generate_color_schemes_async(
    client: anthropic.AsyncAnthropic,
    cards: list[dict[str, Any]],
    model: str,
) -> list[list[str]]:
    """Batched concurrent calls → one color scheme per card."""
    pairs = [(str(c["holiday"]), str(c["visual_style"])) for c in cards]

    # Split into batches
    batches: list[list[tuple[str, str]]] = [pairs[i : i + BATCH_SIZE] for i in range(0, len(pairs), BATCH_SIZE)]

    # Fire batches concurrently
    results = await asyncio.gather(*(_generate_batch(client, batch, model) for batch in batches))

    # Flatten
    schemes: list[list[str]] = []
    for batch_result in results:
        schemes.extend(batch_result)

    # Pad with fallback if Claude returned fewer than expected
    while len(schemes) < len(cards):
        schemes.append(["#333333", "#666666", "#999999"])

    return schemes[: len(cards)]
