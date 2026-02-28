"""Phase 2 — generate per-card creative content via concurrent Claude calls."""

from __future__ import annotations

import asyncio
from typing import Any

import anthropic
from anthropic.types import MessageParam
from rich.console import Console

from scripts.generate_sample_cards.image_generator import (
    RateLimitGate,
    _parse_retry_after,
)
from scripts.generate_sample_cards.spec_generators.constants import MAX_RETRIES
from scripts.generate_sample_cards.spec_generators.utils import extract_json

DUAL_CARD_BLURB_CONTENT_PROMPT = """\
Generate content for a {holiday} greeting card for the {family_name} family.

The card's subtitle / "from" line is already decided: "{subtitle}"

Constraints:
- Family composition: {family_size_hint}
- Visual style: {visual_style}
- This is a 2-page card with a text-focused back page.

Return a JSON object with these fields:
- "family_members": [{{"first_name": str, "role": str, "age": int|null}}]
  roles: "parent", "child", or "pet". Match the family composition above.
  Names must be consistent with the subtitle above.
- "greeting_text": a warm 1-2 sentence {holiday} greeting
- "image_prompt": a detailed prompt for a photorealistic family photo card front page. \
Describe the people (ages, appearance), setting, clothing, poses, mood. \
Do NOT include names, ethnicity, race, or cultural clothing.
- "backstory_blurb": 3-6 sentences about the family's year (fills the back page)

Return ONLY valid JSON, no other text."""

DUAL_CARD_PHOTO_CONTENT_PROMPT = """\
Generate content for a {holiday} greeting card for the {family_name} family.

The card's subtitle / "from" line is already decided: "{subtitle}"

Constraints:
- Family composition: {family_size_hint}
- Visual style: {visual_style}
- This is a 2-page card. The back page is a {back_photo_mode} photo page.

Return a JSON object with these fields:
- "family_members": [{{"first_name": str, "role": str, "age": int|null}}]
  roles: "parent", "child", or "pet". Match the family composition above.
  Names must be consistent with the subtitle above.
- "greeting_text": a warm 1-2 sentence {holiday} greeting
- "back_greeting": a short 1-2 sentence holiday greeting for the back page \
(different from the front greeting — warmer, more personal)
- "image_prompt": a detailed prompt for a photorealistic family photo card front page. \
Describe the people (ages, appearance), setting, clothing, poses, mood. \
Do NOT include names, ethnicity, race, or cultural clothing.
- "back_image_prompt": describe the layout concept for a typical premium \
holiday card back page in a {back_photo_mode} photo layout. Focus on \
composition, framing, and arrangement — not the people or what they're \
doing (that comes from the front image and the image generator).

Return ONLY valid JSON, no other text."""

SINGLE_CARD_FRONT_CONTENT_PROMPT = """\
Generate content for a {holiday} greeting card for the {family_name} family.

The card's subtitle / "from" line is already decided: "{subtitle}"

Constraints:
- Family composition: {family_size_hint}
- Visual style: {visual_style}
- This is a single-page card (front only).

Return a JSON object with these fields:
- "family_members": [{{"first_name": str, "role": str, "age": int|null}}]
  roles: "parent", "child", or "pet". Match the family composition above.
  Names must be consistent with the subtitle above.
- "greeting_text": a warm 1-2 sentence {holiday} greeting
- "image_prompt": a detailed prompt for a photorealistic family photo card. \
Describe the people (ages, appearance), setting, clothing, poses, mood. \
Do NOT include names, ethnicity, race, or cultural clothing.

Return ONLY valid JSON, no other text."""


async def generate_card_content_async(
    client: anthropic.AsyncAnthropic,
    semaphore: asyncio.Semaphore,
    gate: RateLimitGate,
    family_name: str,
    constraints: dict[str, Any],
    model: str,
    console: Console,
    card_index: int,
) -> dict[str, Any] | None:
    """One Claude call for a single card's creative content.

    Returns the parsed dict on success, None on failure after retries.
    """
    back_page_type = constraints.get("back_page_type")
    if back_page_type == "blurb":
        template = DUAL_CARD_BLURB_CONTENT_PROMPT
    elif back_page_type == "photo":
        template = DUAL_CARD_PHOTO_CONTENT_PROMPT
    else:
        template = SINGLE_CARD_FRONT_CONTENT_PROMPT

    format_kwargs: dict[str, str] = {
        "holiday": str(constraints["holiday"]),
        "family_name": family_name,
        "subtitle": str(constraints["subtitle"]),
        "family_size_hint": str(constraints["family_size_hint"]),
        "visual_style": str(constraints["visual_style"]),
    }
    if back_page_type == "photo":
        format_kwargs["back_photo_mode"] = str(constraints.get("back_photo_mode", "collage"))

    prompt = template.format(**format_kwargs)

    # Minimal stand-in so RateLimitGate.wait_if_paused can call .set()
    class _Stub:
        def set(self, _status: str, _detail: str = "") -> None:
            pass

    stub = _Stub()

    for attempt in range(MAX_RETRIES):
        await gate.wait_if_paused(stub)  # type: ignore[arg-type]
        async with semaphore:
            try:
                response = await client.messages.create(
                    model=model,
                    max_tokens=1024,
                    messages=[MessageParam(role="user", content=prompt)],
                )
                text = response.content[0].text  # type: ignore[union-attr]
                return dict(extract_json(text))  # type: ignore[arg-type]

            except anthropic.RateLimitError as e:
                wait = _parse_retry_after(e)
                gate.pause(wait)
                await asyncio.sleep(wait)
                continue

            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    wait = 2 ** (attempt + 1)
                    await asyncio.sleep(wait)
                else:
                    console.print(f"  [red]Card {card_index + 1} ({family_name}) failed: {e!s:.60}[/]")
                    return None
    return None
