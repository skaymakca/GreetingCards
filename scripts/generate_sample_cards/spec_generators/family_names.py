"""Phase 1a — generate unique diverse family names via a single Claude call."""

from __future__ import annotations

import anthropic
from anthropic.types import MessageParam

from scripts.generate_sample_cards.spec_generators.utils import extract_json

FAMILY_NAME_PROMPT = """\
Generate exactly {count} unique, diverse family names as a JSON array of strings.

Requirements:
- Mix of Anglo, Hispanic, East Asian, South Asian/Desi, African, Eastern European, \
Western European (French, German, Italian, etc.), Middle Eastern, and other origins
- Every name must be unique
- Return ONLY the JSON array, no other text.

Example: ["Kim", "Okonkwo", "Petrov", "García", "Anderson"]"""


async def generate_family_names_async(
    client: anthropic.AsyncAnthropic,
    count: int,
    model: str,
) -> list[str]:
    """One Claude call → list of N unique family names."""
    response = await client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[MessageParam(role="user", content=FAMILY_NAME_PROMPT.format(count=count))],
    )
    text = response.content[0].text  # type: ignore[union-attr]
    names: list[str] = list(extract_json(text))
    # Ensure uniqueness (trim or pad if Claude misbehaved)
    seen: set[str] = set()
    unique: list[str] = []
    for s in names:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    return unique[:count]
