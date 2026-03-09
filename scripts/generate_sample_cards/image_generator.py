"""OpenAI image generation with shared rate limit gating."""

from __future__ import annotations

import asyncio
import base64
import logging
import time
import urllib.request
from pathlib import Path

import anthropic
import openai

from scripts.generate_sample_cards.models import CardJob, CardSpec

log = logging.getLogger(__name__)

# Portrait card size for full-card mode
FULL_CARD_SIZE = "1024x1536"

FRONT_PAGE_PROMPT = """\
A premium commercial holiday greeting card front, in the style of \
Shutterfly, Snapfish, or Minted. Full-bleed photorealistic family \
photo with decorative holiday ornamentation and elegant typography. \
Everyone is fully clothed and the scene is family-friendly.

IMPORTANT — render this EXACT text on the card:

Primary text (large, elegant serif or script font, prominently \
placed at the top or bottom of the card):
  "{name_format}"
  Spelled letter-by-letter: {name_spelled}

Secondary text (smaller, clean sans-serif font, below or above \
the primary text):
  "{greeting_text}"

Typography constraints:
- Text must be crisp, legible, and correctly spelled
- Use high-contrast colors so text is readable over the photo
- Text should look professionally typeset, not hand-drawn

Holiday: {holiday}. Color palette: {colors}. \
Visual style: {visual_style}.

Family photo: {image_prompt}"""

BACK_BLURB_PROMPT = """\
The inside or back page of a premium holiday greeting card, \
matching the style of Shutterfly, Snapfish, or Minted. Simpler \
than the front — text-focused with subtle decorative accents. \
The scene is fully clothed and family-friendly.

IMPORTANT — render this EXACT text on the page. Each piece of \
text must appear exactly once — do not repeat or duplicate any text.

Blurb (placed above the signature):
  "{backstory_blurb}"

Signature (placed below the blurb):
  "{name_format}"
  Spelled letter-by-letter: {name_spelled}

Choose a layout and font pairing that complements the visual style \
and holiday. Text must be crisp, legible, correctly spelled, and \
high-contrast against the background.

Holiday: {holiday}. Color palette: {colors}. \
Use subtle holiday ornamentation around the edges."""

BACK_PHOTO_SINGLE_PROMPT = """\
The back page of a premium holiday greeting card, matching the style \
of Shutterfly, Snapfish, or Minted. This page continues the same \
photo shoot as the front page (provided as the reference image) — \
same people, same clothes, same location. However, the composition \
must be distinctly different: a new pose, a different grouping, a \
candid moment, a wider or tighter crop, people doing something \
different (laughing together, walking, playing, hugging). The card \
should feel cohesive as a set, but each page should be its own \
compelling photograph — not a duplicate of the front. Everyone \
is fully clothed and the scene is family-friendly.

IMPORTANT — render this EXACT text on the page. Each piece of \
text must appear exactly once — do not repeat or duplicate any text.

Greeting:
  "{back_greeting}"

Signature:
  "{name_format}"
  Spelled letter-by-letter: {name_spelled}

Choose a font that complements the front page. Text must be crisp, \
legible, correctly spelled, and high-contrast over the photo.

Holiday: {holiday}. Color palette: {colors}. \
Visual style: {visual_style}.

Photo direction: {back_image_prompt}"""

BACK_PHOTO_COLLAGE_PROMPT = """\
The back page of a premium holiday greeting card, matching the style \
of Shutterfly, Snapfish, or Minted. A photo collage page with \
multiple candid snapshots of the family from throughout the year. \
The people should look like the same family from the front page \
(provided as the reference image) — same faces, same ages — but \
they can be in different clothes, different scenes, and different \
moods. Not every photo needs everyone — individual portraits and \
subsets are great, especially children. Each photo in the collage \
must be visually distinct from the others — different setting, \
different activity, different composition. No two photos should \
look like variations of the same shot. Everyone is fully clothed \
and the scene is family-friendly.

IMPORTANT — render this EXACT text on the page. Each piece of \
text must appear exactly once — do not repeat or duplicate any text.

Greeting:
  "{back_greeting}"

Signature:
  "{name_format}"
  Spelled letter-by-letter: {name_spelled}

Choose a font that complements the front page. Text must be crisp, \
legible, correctly spelled, and high-contrast over the photos.

Holiday: {holiday}. Color palette: {colors}. \
Visual style: {visual_style}.

Collage concept: {back_image_prompt}"""


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


# noinspection PyTypeChecker
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
    reference_image: Path | None = None,
) -> bool:
    """Generate an image with OpenAI and save as PNG.

    Uses the shared semaphore for concurrency control and the shared gate
    to pause when any task hits a rate limit. Returns True on success.

    If *reference_image* is provided, uses the edit endpoint so the model
    can see the reference (e.g. front page) for visual consistency.
    """
    for attempt in range(5):
        # Wait for any global rate limit pause before competing for a slot
        await gate.wait_if_paused(job)
        async with semaphore:
            job.set(status_label)
            try:
                if reference_image and reference_image.exists():
                    result = await client.images.edit(  # type: ignore[call-overload]
                        model=model,
                        image=[reference_image],
                        prompt=prompt,
                        n=1,
                        size=size,  # pyright: ignore[reportArgumentType]
                        quality=quality,  # pyright: ignore[reportArgumentType]
                        input_fidelity="high",
                    )
                else:
                    result = await client.images.generate(  # type: ignore[call-overload]
                        model=model,
                        prompt=prompt,
                        n=1,
                        size=size,  # pyright: ignore[reportArgumentType]
                        quality=quality,  # pyright: ignore[reportArgumentType]
                    )

                if not result.data:
                    return False
                image_data = result.data[0]
                if image_data.b64_json:
                    img_bytes = base64.b64decode(image_data.b64_json)
                    output_path.write_bytes(img_bytes)
                    return True
                elif image_data.url:
                    urllib.request.urlretrieve(image_data.url, output_path)  # nosec B310
                    return True

                return False

            except openai.RateLimitError as e:
                wait = _parse_retry_after(e)
                gate.pause(wait)
                job.set("rate_limited", f"{wait:.0f}s")
                await asyncio.sleep(wait)
                continue

            except Exception as e:
                endpoint = "edit" if reference_image else "generate"
                log.warning(
                    "Card %d %s attempt %d/%d failed (%s): %s",
                    job.index,
                    endpoint,
                    attempt + 1,
                    5,
                    type(e).__name__,
                    e,
                )
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
        return FRONT_PAGE_PROMPT.format(
            name_format=spec.name_format,
            name_spelled=name_spelled,
            greeting_text=spec.greeting_text,
            holiday=spec.holiday,
            colors=colors,
            visual_style=spec.visual_style,
            image_prompt=spec.image_prompt,
        )
    elif spec.back_page_type == "photo":
        template = BACK_PHOTO_SINGLE_PROMPT if spec.back_photo_mode == "single" else BACK_PHOTO_COLLAGE_PROMPT
        return template.format(
            back_greeting=spec.back_greeting,
            name_format=spec.name_format,
            name_spelled=name_spelled,
            holiday=spec.holiday,
            colors=colors,
            visual_style=spec.visual_style,
            back_image_prompt=spec.back_image_prompt,
        )
    else:
        # "blurb" back page (text-focused)
        return BACK_BLURB_PROMPT.format(
            backstory_blurb=spec.backstory_blurb,
            name_format=spec.name_format,
            name_spelled=name_spelled,
            holiday=spec.holiday,
            colors=colors,
        )


async def generate_full_card_images_async(
    client: openai.AsyncOpenAI,
    semaphore: asyncio.Semaphore,
    gate: RateLimitGate,
    job: CardJob,
    spec: CardSpec,
    tmp_dir: Path,
    index: int,
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
    front_image: Path | None = None

    for side in sides:
        image_file = tmp_dir / f"card_{index:03d}_{side}.png"
        prompt = build_full_card_prompt(spec, side)
        status_label = "gen_front" if side == "front" else "gen_back"

        # For photo-type back pages, pass the front image as a reference
        # so the generated back page has visually consistent people/style.
        ref = front_image if side == "back" and spec.back_page_type == "photo" else None

        success = await generate_image_openai_async(
            client,
            semaphore,
            gate,
            job,
            prompt,
            image_file,
            size=FULL_CARD_SIZE,
            model=image_model,
            status_label=status_label,
            reference_image=ref,
        )
        if success:
            paths.append(image_file)
            if side == "front":
                front_image = image_file

    return paths
