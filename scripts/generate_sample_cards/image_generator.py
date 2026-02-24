"""OpenAI image generation with shared rate limit gating."""

from __future__ import annotations

import asyncio
import base64
import time
from pathlib import Path

import anthropic
import openai

from scripts.generate_sample_cards.models import CardJob, CardSpec

# Portrait card size for full-card mode
FULL_CARD_SIZE = "1024x1536"


class RateLimitGate:
    """Shared gate that pauses all tasks when any one hits a rate limit.

    When a rate limit response arrives, the gate records a resume timestamp.
    All tasks call ``wait_if_paused()`` before acquiring the semaphore, so
    queued tasks won't immediately fire into another rate limit.

    Safe without locks because asyncio is single-threaded — only one
    coroutine runs at a time between await points.
    """

    def __init__(self) -> None:
        self._resume_at: float = 0

    async def wait_if_paused(self, job: CardJob) -> None:
        """Wait until any active rate limit pause expires."""
        now = time.monotonic()
        remaining = self._resume_at - now
        if remaining > 0:
            job.set("rate_limited", f"{remaining:.0f}s")
            await asyncio.sleep(remaining)

    def pause(self, seconds: float) -> None:
        """Signal all tasks to pause for at least *seconds* from now."""
        resume_at = time.monotonic() + seconds
        self._resume_at = max(self._resume_at, resume_at)


def _parse_retry_after(exc: openai.RateLimitError | anthropic.RateLimitError) -> float:
    """Extract retry-after delay (seconds) from a rate limit exception.

    Checks retry-after-ms first (more precise), then retry-after header.
    Falls back to 10 seconds if neither is present.
    """
    headers = exc.response.headers
    ms = headers.get("retry-after-ms")
    if ms:
        try:
            return float(ms) / 1000
        except ValueError:
            pass
    secs = headers.get("retry-after")
    if secs:
        try:
            return float(secs)
        except ValueError:
            pass
    return 10.0


async def generate_image_openai_async(
    client: openai.AsyncOpenAI,
    semaphore: asyncio.Semaphore,
    gate: RateLimitGate,
    job: CardJob,
    prompt: str,
    output_path: Path,
    quality: str = "high",
    size: str = "1024x1024",
    model: str = "gpt-image-1.5",
    status_label: str = "gen_front",
) -> bool:
    """Generate an image with OpenAI and save as PNG.

    Uses the shared semaphore for concurrency control and the shared gate
    to pause when any task hits a rate limit. Returns True on success.
    """
    for attempt in range(5):
        # Wait for any global rate limit pause before competing for a slot
        await gate.wait_if_paused(job)
        job.set(status_label)
        async with semaphore:
            try:
                result = await client.images.generate(  # type: ignore[call-overload]
                    model=model,
                    prompt=prompt,
                    n=1,
                    size=size,
                    quality=quality,
                )

                if not result.data:
                    return False
                image_data = result.data[0]
                if image_data.b64_json:
                    img_bytes = base64.b64decode(image_data.b64_json)
                    output_path.write_bytes(img_bytes)
                    return True
                elif image_data.url:
                    import urllib.request

                    urllib.request.urlretrieve(image_data.url, output_path)
                    return True

                return False

            except openai.RateLimitError as e:
                wait = _parse_retry_after(e)
                gate.pause(wait)
                job.set("rate_limited", f"{wait:.0f}s")
                await asyncio.sleep(wait)
                continue

            except Exception as e:
                wait = 2 ** (attempt + 1)
                if attempt < 4:
                    job.set("rate_limited", f"retry {attempt + 1}/5")
                    await asyncio.sleep(wait)
                else:
                    job.set("error", str(e)[:40])

    return False


def _spell_out(text: str) -> str:
    """Spell out text letter-by-letter for accurate AI text rendering.

    Example: "Smith" -> "S-M-I-T-H"
    """
    return "-".join(text.upper())


def build_full_card_prompt(spec: CardSpec, side: str) -> str:
    """Build an OpenAI image prompt for a complete greeting card image.

    Follows gpt-image-1.5 best practices for text rendering:
    - Literal text in quotes and ALL CAPS
    - Letter-by-letter spelling for names
    - Explicit typography constraints (font style, size, placement)

    Args:
        spec: The card specification with family info, text, and style details.
        side: "front" or "back".
    """
    colors = ", ".join(spec.color_scheme)
    name_spelled = _spell_out(spec.name_format)

    if side == "front":
        return (
            f"A premium commercial holiday greeting card front, in the style of "
            f"Shutterfly, Snapfish, or Minted. Full-bleed photorealistic family "
            f"photo with decorative holiday ornamentation and elegant typography.\n"
            f"\n"
            f"IMPORTANT — render this EXACT text on the card:\n"
            f"\n"
            f"Primary text (large, elegant serif or script font, prominently "
            f"placed at the top or bottom of the card):\n"
            f'  "{spec.name_format}"\n'
            f"  Spelled letter-by-letter: {name_spelled}\n"
            f"\n"
            f"Secondary text (smaller, clean sans-serif font, below or above "
            f"the primary text):\n"
            f'  "{spec.greeting_text}"\n'
            f"\n"
            f"Typography constraints:\n"
            f"- Text must be crisp, legible, and correctly spelled\n"
            f"- Use high-contrast colors so text is readable over the photo\n"
            f"- Text should look professionally typeset, not hand-drawn\n"
            f"\n"
            f"Holiday: {spec.holiday}. Color palette: {colors}. "
            f"Visual style: {spec.visual_style}.\n"
            f"\n"
            f"Family photo: {spec.image_prompt}"
        )
    else:
        return (
            f"The inside or back page of a premium holiday greeting card, "
            f"matching the style of Shutterfly, Snapfish, or Minted. Simpler "
            f"than the front — text-focused with subtle decorative accents.\n"
            f"\n"
            f"IMPORTANT — render this EXACT text on the page:\n"
            f"\n"
            f"Main body text (medium size, clean readable serif font, centered "
            f"in the upper half of the page):\n"
            f'  "{spec.backstory_blurb}"\n'
            f"\n"
            f"Signature text (elegant script or serif font, centered below "
            f"the body text):\n"
            f'  "{spec.name_format}"\n'
            f"  Spelled letter-by-letter: {name_spelled}\n"
            f"\n"
            f"Typography constraints:\n"
            f"- All text must be crisp, legible, and correctly spelled\n"
            f"- Use a clean, readable font — not overly decorative\n"
            f"- High contrast against the background\n"
            f"\n"
            f"Holiday: {spec.holiday}. Color palette: {colors}. "
            f"Use subtle holiday ornamentation around the edges."
        )


async def generate_full_card_images_async(
    client: openai.AsyncOpenAI,
    semaphore: asyncio.Semaphore,
    gate: RateLimitGate,
    job: CardJob,
    spec: CardSpec,
    tmp_dir: Path,
    index: int,
    quality: str,
    image_model: str = "gpt-image-1.5",
) -> list[Path]:
    """Generate front (and optionally back) images for a card.

    Returns a list of successfully generated image paths (0-2).
    Images are written to tmp_dir and should be cleaned up by the caller.
    """
    sides = ["front"]
    if spec.page_count >= 2:
        sides.append("back")

    paths: list[Path] = []

    for side in sides:
        image_file = tmp_dir / f"card_{index:03d}_{side}.png"
        prompt = build_full_card_prompt(spec, side)
        status_label = "gen_front" if side == "front" else "gen_back"
        success = await generate_image_openai_async(
            client, semaphore, gate, job, prompt, image_file, quality,
            size=FULL_CARD_SIZE, model=image_model,
            status_label=status_label,
        )
        if success:
            paths.append(image_file)

    return paths
