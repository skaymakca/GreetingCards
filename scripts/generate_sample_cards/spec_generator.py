"""Claude API — generate card specifications."""

from __future__ import annotations

import json
import random

import anthropic
from rich.console import Console

from scripts.generate_sample_cards.models import CardSpec

CARD_SPEC_PROMPT = """\
Generate exactly {count} unique greeting card specifications as a JSON array.

Each card must be a JSON object with these fields:
- "family_surname": string — diverse surnames (mix of Anglo, Hispanic, Asian, \
African, Eastern European, Middle Eastern, etc.)
- "family_members": array of {{"first_name": string, "role": string, "age": int|null}} \
where role is "parent", "child", or "pet"
- "name_format": string — the formatted display name for the card. Use these formats \
with the given approximate distribution:
  1. "The Smiths" (The + plural surname) — ~30%
  2. "The Smith Family" (The + surname + Family) — ~25%
  3. "Smith Family" (surname + Family) — ~15%
  4. "John & Jane Smith" (parents' first names + surname) — ~15%
  5. "John, Jane & Kids" (first names + & Kids) — ~5%
  6. "From the Desk of John Smith" (formal single-person) — ~5%
  7. "Smith" (just surname) — ~5%
- "holiday": string — one of: Christmas, Hanukkah, New Year, Thanksgiving, Easter, \
Diwali, Eid, Kwanzaa, Chinese New Year, Season's Greetings, Valentine's Day, Fourth of July
- "greeting_text": string — a short 1-2 sentence holiday greeting appropriate to the holiday
- "backstory_blurb": string — 2-3 sentences about the family's year (for inside of card)
- "visual_style": string — one of: photo_card, collage, typography, minimalist, ornate, playful, \
vintage, modern_grid, full_bleed, polaroid, border_frame
- "color_scheme": array of 2-3 hex color strings (e.g. ["#1a3c5e", "#c4a35a", "#f5f0e1"])
- "page_count": always set to 1 (the script will override this)
- "filename": string — realistic filename as if scanned/downloaded. Mix formats like: \
"IMG_3847.pdf", "Scan 2024-12-15 at 10.23 AM.pdf", "Christmas Card - Smith Family.pdf", \
"holiday_card_2024.pdf", "Photo Dec 20 2024, 3 45 22 PM.pdf", etc.
- "image_prompt": string — a detailed prompt for generating a photorealistic family photo. \
Describe the family composition (number of people, approximate ages, genders), setting \
(holiday-appropriate), clothing, poses, and mood. Be specific and vivid. Do NOT include \
any names in the prompt. IMPORTANT: Do NOT reference ethnicity, race, or culturally-specific \
clothing (e.g. kimono, cheongsam, sari). Just describe people naturally — image models \
frequently get cultural details wrong and produce offensive mismatches.

Requirements:
- All 11 visual_style values must appear at least once, distributed as evenly as possible
- All holiday types should appear (repeat as needed for counts > 12)
- Family sizes should vary: couples (2), small families (3-4), large families (5-6), \
some with pets
- Color schemes should be holiday-appropriate and visually distinct
- Filenames should be diverse and realistic

{seed_instruction}

Return ONLY the JSON array, no other text."""


def generate_card_specs(
    count: int,
    seed: int | None,
    model: str,
) -> list[CardSpec]:
    """Call Claude to generate card specifications.

    Shows a spinner during the API call.
    """
    seed_instruction = ""
    if seed is not None:
        seed_instruction = (
            f"Use seed value {seed} for soft reproducibility — "
            f"try to generate similar results when given the same seed and count."
        )

    prompt = CARD_SPEC_PROMPT.format(
        count=count,
        seed_instruction=seed_instruction,
    )

    client = anthropic.Anthropic()
    console = Console(highlight=False)

    with console.status(f"[bold cyan]Generating {count} card specs with {model}..."):
        response = client.messages.create(
            model=model,
            max_tokens=4096 * max(1, count // 5),
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text  # type: ignore[union-attr]

        # Extract JSON from response (handle markdown code blocks)
        text = text.strip()
        if text.startswith("```"):
            first_newline = text.index("\n")
            text = text[first_newline + 1 :]
            if text.endswith("```"):
                text = text[:-3].strip()

        try:
            raw_specs = json.loads(text)
        except json.JSONDecodeError:
            # Retry once asking Claude to fix the JSON
            console.print("  [yellow]JSON parse error, retrying with fix-up prompt...[/]")
            fix_response = client.messages.create(
                model=model,
                max_tokens=4096 * max(1, count // 5),
                messages=[
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": text},
                    {
                        "role": "user",
                        "content": "Your response was not valid JSON. "
                        "Return ONLY the corrected JSON array, no other text.",
                    },
                ],
            )
            fix_text = fix_response.content[0].text.strip()  # type: ignore[union-attr]
            if fix_text.startswith("```"):
                first_newline = fix_text.index("\n")
                fix_text = fix_text[first_newline + 1 :]
                if fix_text.endswith("```"):
                    fix_text = fix_text[:-3].strip()
            raw_specs = json.loads(fix_text)

    specs = [CardSpec.from_dict(d) for d in raw_specs]

    # Override page_count with weighted random: ~80% get 2 pages (front + back)
    rng = random.Random(seed)
    for spec in specs:
        spec.page_count = 2 if rng.random() < 0.80 else 1

    two_page = sum(1 for s in specs if s.page_count == 2)
    console.print(f"  Generated {len(specs)} card specs ({two_page} with back page)")
    return specs
