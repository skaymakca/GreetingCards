#!/usr/bin/env python3
"""Sample Greeting Card PDF Generator.

Generates a corpus of diverse, realistic greeting card PDFs for testing and
demos.  Uses Claude for text/metadata generation and OpenAI gpt-image-1 for
photorealistic family photos, then assembles PDFs with PyMuPDF.

Output
------
    <output_dir>/          PDF files (default: _script_output/YYYYMMDD_HHMM-generate_sample_cards/)

Usage
-----
    # Default: 3 layout cards (no flags needed)
    uv run python -m scripts.generate_sample_cards

    # 10 layout cards + 5 full-image cards
    uv run python -m scripts.generate_sample_cards --layout-cards=10 --full-image-cards=5

    # Only full-image cards (Shutterfly/Minted style)
    uv run python -m scripts.generate_sample_cards --full-image-cards=10

    # With placeholders (no OpenAI cost)
    uv run python -m scripts.generate_sample_cards --layout-cards=5 --no-images
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import random
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anthropic
import fitz  # type: ignore[import-untyped]
import openai
from rich.live import Live
from rich.table import Table
from rich.text import Text

from scripts.helpers import make_output_dir

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class FamilyMember:
    first_name: str
    role: str  # "parent", "child", "pet"
    age: int | None = None


@dataclass
class CardSpec:
    family_surname: str
    family_members: list[FamilyMember]
    name_format: str
    holiday: str
    greeting_text: str
    backstory_blurb: str
    visual_style: str  # photo_card, collage, typography, minimalist, ornate, playful, vintage, modern_grid, full_bleed, polaroid, border_frame
    color_scheme: list[str]  # 2-3 hex colors
    page_count: int  # 1 or 2
    filename: str
    font_family: str
    font_accent: str
    image_prompt: str

    @staticmethod
    def from_dict(d: dict[str, Any]) -> CardSpec:
        members = [
            FamilyMember(
                first_name=str(m["first_name"]),
                role=str(m["role"]),
                age=int(m["age"]) if m.get("age") is not None else None,
            )
            for m in d["family_members"]
        ]
        return CardSpec(
            family_surname=str(d["family_surname"]),
            family_members=members,
            name_format=str(d["name_format"]),
            holiday=str(d["holiday"]),
            greeting_text=str(d["greeting_text"]),
            backstory_blurb=str(d["backstory_blurb"]),
            visual_style=str(d["visual_style"]),
            color_scheme=[str(c) for c in d["color_scheme"]],
            page_count=int(d["page_count"]),
            filename=str(d["filename"]),
            font_family=str(d["font_family"]),
            font_accent=str(d["font_accent"]),
            image_prompt=str(d["image_prompt"]),
        )


@dataclass
class CardJob:
    """Tracks the status of one card being processed."""

    index: int  # 1-based display index
    card_type: str  # "layout" or "full-image"
    filename: str
    style: str
    status: str = "waiting"  # waiting, generating, gen_front, gen_back, composing, done, error, rate_limited
    detail: str = ""  # extra info (e.g., "8.2s", error message)

    def set(self, status: str, detail: str = "") -> None:
        self.status = status
        self.detail = detail


def _build_status_table(jobs: list[CardJob], image_src: str) -> Table:
    """Build a rich Table showing the current status of all card jobs."""
    table = Table(show_header=True, header_style="bold", pad_edge=False)
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Type", width=10)
    table.add_column("Filename", no_wrap=True, max_width=40)
    table.add_column("Style", width=13)
    table.add_column("Status", no_wrap=True)

    status_styles: dict[str, tuple[str, str]] = {
        "waiting": ("dim", "..."),
        "generating": ("yellow", "Generating image..."),
        "gen_front": ("yellow", "Generating front..."),
        "gen_back": ("yellow", "Generating back..."),
        "composing": ("cyan", "Composing PDF..."),
        "done": ("green", "Done"),
        "error": ("red", "Error"),
        "rate_limited": ("magenta", "Rate limited"),
        "placeholder": ("dim", "Placeholder"),
    }

    for job in jobs:
        style, label = status_styles.get(job.status, ("white", job.status))
        status_text = Text(label, style=style)
        if job.detail:
            status_text.append(f" ({job.detail})", style=style)
        table.add_row(
            str(job.index),
            job.card_type,
            job.filename,
            job.style,
            status_text,
        )

    # Summary line
    done = sum(1 for j in jobs if j.status == "done")
    errors = sum(1 for j in jobs if j.status == "error")
    active = sum(1 for j in jobs if j.status in ("generating", "gen_front", "gen_back", "composing"))
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


# ---------------------------------------------------------------------------
# macOS system fonts
# ---------------------------------------------------------------------------

MACOS_FONTS: dict[str, str] = {
    "Georgia": "/System/Library/Fonts/Supplemental/Georgia.ttf",
    "Palatino": "/System/Library/Fonts/Palatino.ttc",
    "Futura": "/System/Library/Fonts/Supplemental/Futura.ttc",
    "Avenir": "/System/Library/Fonts/Avenir.ttc",
    "Avenir Next": "/System/Library/Fonts/Avenir Next.ttc",
    "Snell Roundhand": "/System/Library/Fonts/Supplemental/SnellRoundhand.ttc",
    "Zapfino": "/System/Library/Fonts/Supplemental/Zapfino.ttf",
    "Brush Script MT": "/System/Library/Fonts/Supplemental/Brush Script.ttf",
    "Didot": "/System/Library/Fonts/Supplemental/Didot.ttc",
    "Baskerville": "/System/Library/Fonts/Supplemental/Baskerville.ttc",
    "Helvetica Neue": "/System/Library/Fonts/HelveticaNeue.ttc",
    "Copperplate": "/System/Library/Fonts/Supplemental/Copperplate.ttc",
}

# Fallback fonts guaranteed available in PDF
FALLBACK_BODY = "Helvetica"
FALLBACK_ACCENT = "Times-Roman"

# Track fonts we've already warned about
_font_warnings: set[str] = set()


def _get_font_info(font_spec: str) -> tuple[str, str | None]:
    """Parse font spec into (fontname, fontfile) for fitz.TextWriter.

    Returns:
        (fontname, fontfile) — fontfile is None for built-in PDF fonts.
    """
    if font_spec.startswith("f:"):
        _, name, path = font_spec.split(":", 2)
        return name, path
    return font_spec, None


def _resolve_font(font_name: str) -> str:
    """Resolve a font name to a spec string (either 'f:Name:path' or builtin)."""
    path = MACOS_FONTS.get(font_name)
    if path and os.path.exists(path):
        safe_name = font_name.replace(" ", "")
        return f"f:{safe_name}:{path}"
    if font_name not in _font_warnings:
        _font_warnings.add(font_name)
        print(f"  Warning: Font '{font_name}' not found, using fallback")
    return ""


# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------


def hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    """Convert '#RRGGBB' to (r, g, b) floats in 0-1 range."""
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255)


def contrasting_text_color(bg_hex: str) -> tuple[float, float, float]:
    """Return black or white depending on background luminance."""
    r, g, b = hex_to_rgb(bg_hex)
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return (0, 0, 0) if luminance > 0.5 else (1, 1, 1)


# ---------------------------------------------------------------------------
# Claude API — generate card specs
# ---------------------------------------------------------------------------

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
- "font_family": string — body font, must be one of: {body_fonts}
- "font_accent": string — decorative/display font, must be one of: {accent_fonts}
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
- Font pairings should be sensible (don't pair two decorative fonts)
- Filenames should be diverse and realistic

{seed_instruction}

Return ONLY the JSON array, no other text."""


def generate_card_specs(
    count: int,
    seed: int | None,
    model: str,
) -> list[CardSpec]:
    """Call Claude to generate card specifications."""
    body_fonts = ", ".join(sorted(MACOS_FONTS.keys()))
    accent_fonts = body_fonts  # same pool

    seed_instruction = ""
    if seed is not None:
        seed_instruction = (
            f"Use seed value {seed} for soft reproducibility — "
            f"try to generate similar results when given the same seed and count."
        )

    prompt = CARD_SPEC_PROMPT.format(
        count=count,
        body_fonts=body_fonts,
        accent_fonts=accent_fonts,
        seed_instruction=seed_instruction,
    )

    client = anthropic.Anthropic()

    print(f"Generating {count} card specs with {model}...")
    response = client.messages.create(
        model=model,
        max_tokens=4096 * max(1, count // 5),
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text  # type: ignore[union-attr]

    # Extract JSON from response (handle markdown code blocks)
    text = text.strip()
    if text.startswith("```"):
        # Remove opening fence
        first_newline = text.index("\n")
        text = text[first_newline + 1 :]
        # Remove closing fence
        if text.endswith("```"):
            text = text[: -3].strip()

    try:
        raw_specs = json.loads(text)
    except json.JSONDecodeError:
        # Retry once asking Claude to fix the JSON
        print("  JSON parse error, retrying with fix-up prompt...")
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
                fix_text = fix_text[: -3].strip()
        raw_specs = json.loads(fix_text)

    specs = [CardSpec.from_dict(d) for d in raw_specs]

    # Override page_count with weighted random: ~80% get 2 pages (front + back)
    rng = random.Random(seed)
    for spec in specs:
        spec.page_count = 2 if rng.random() < 0.80 else 1

    two_page = sum(1 for s in specs if s.page_count == 2)
    print(f"  Generated {len(specs)} card specs ({two_page} with back page)")
    return specs


# ---------------------------------------------------------------------------
# OpenAI image generation
# ---------------------------------------------------------------------------


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
    job: CardJob,
    prompt: str,
    output_path: Path,
    quality: str = "high",
    size: str = "1024x1024",
    model: str = "gpt-image-1.5",
    status_label: str = "generating",
) -> bool:
    """Generate an image with OpenAI and save as PNG.

    Uses the shared semaphore for concurrency control and respects
    rate limit errors by pausing for the retry-after duration.
    Updates job.status for live display. Returns True on success, False on failure.
    """
    for attempt in range(5):
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


def generate_placeholder_image(
    color_hex: str,
    output_path: Path,
    size: tuple[int, int] = (1024, 1024),
) -> None:
    """Generate a solid-color placeholder image with Pillow."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", size, color_hex)
    draw = ImageDraw.Draw(img)

    # Draw "PLACEHOLDER" text
    text = "PLACEHOLDER"
    try:
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont = ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/Arial.ttf", 60
        )
    except (OSError, IOError):
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (size[0] - text_w) // 2
    y = (size[1] - text_h) // 2

    # Semi-transparent overlay effect via lighter/darker color
    r, g, b = hex_to_rgb(color_hex)
    overlay = (
        min(255, int(r * 255) + 40),
        min(255, int(g * 255) + 40),
        min(255, int(b * 255) + 40),
    )
    draw.text((x, y), text, fill=overlay, font=font)

    img.save(output_path, "PNG")


# ---------------------------------------------------------------------------
# Card dimensions: 5 x 7 inches = 360 x 504 points
# ---------------------------------------------------------------------------

CARD_W = 360
CARD_H = 504


# ---------------------------------------------------------------------------
# Full-card image generation (--full-card mode)
# ---------------------------------------------------------------------------

# Portrait card size for full-card mode
FULL_CARD_SIZE = "1024x1536"
FULL_CARD_PLACEHOLDER_SIZE = (1024, 1536)


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
    job: CardJob,
    spec: CardSpec,
    tmp_dir: Path,
    index: int,
    quality: str,
    no_images: bool,
    image_model: str = "gpt-image-1.5",
) -> list[Path]:
    """Generate front (and optionally back) images for --full-card mode.

    Returns a list of image paths (1 or 2 depending on page_count).
    Images are written to tmp_dir and should be cleaned up by the caller.
    """
    sides = ["front"]
    if spec.page_count >= 2:
        sides.append("back")

    paths: list[Path] = []
    placeholder_color = spec.color_scheme[0] if spec.color_scheme else "#666688"

    for side in sides:
        image_file = tmp_dir / f"card_{index:03d}_{side}.png"
        paths.append(image_file)

        if no_images:
            generate_placeholder_image(
                placeholder_color, image_file, size=FULL_CARD_PLACEHOLDER_SIZE
            )
            job.set("placeholder")
        else:
            prompt = build_full_card_prompt(spec, side)
            status_label = "gen_front" if side == "front" else "gen_back"
            success = await generate_image_openai_async(
                client, semaphore, job, prompt, image_file, quality,
                size=FULL_CARD_SIZE, model=image_model,
                status_label=status_label,
            )
            if not success:
                generate_placeholder_image(
                    placeholder_color, image_file, size=FULL_CARD_PLACEHOLDER_SIZE
                )

    return paths


def compose_pdf_from_images(
    image_paths: list[Path],
    output_path: Path,
) -> None:
    """Build a PDF where each image is a full-bleed page.

    Used by --full-card mode where the AI generates the entire card design.
    Pages are sized to 5×7 inches (360×504 points) like real greeting cards.
    """
    doc = fitz.open()
    for img_path in image_paths:
        page = doc.new_page(width=CARD_W, height=CARD_H)
        page.insert_image(page.rect, filename=str(img_path))
    doc.save(str(output_path), deflate=True, garbage=3)
    doc.close()


# ---------------------------------------------------------------------------
# PDF layout helpers
# ---------------------------------------------------------------------------

MARGIN = 20


def _insert_text(
    page: fitz.Page,
    rect: fitz.Rect,
    text: str,
    font_spec: str,
    fontsize: float,
    color: tuple[float, float, float],
    align: int = fitz.TEXT_ALIGN_CENTER,
) -> float:
    """Insert text into a rect, handling font resolution. Returns used height."""
    fontname, fontfile = _get_font_info(font_spec)
    if fontfile:
        rc = page.insert_textbox(
            rect,
            text,
            fontname=fontname,
            fontfile=fontfile,
            fontsize=fontsize,
            color=color,
            align=align,
        )
    else:
        # Built-in PDF font
        builtin = FALLBACK_BODY if fontname == "" else fontname
        rc = page.insert_textbox(
            rect,
            text,
            fontname=builtin,
            fontsize=fontsize,
            color=color,
            align=align,
        )
    return rc


def _insert_image(
    page: fitz.Page,
    rect: fitz.Rect,
    image_path: Path,
) -> None:
    """Insert an image into a page, fitting within rect."""
    page.insert_image(rect, filename=str(image_path))


def _add_backstory_page(
    doc: fitz.Document,
    spec: CardSpec,
    body_font: str,
) -> None:
    """Add a second page with the backstory blurb as an inside message."""
    page = doc.new_page(width=CARD_W, height=CARD_H)

    # Light background
    bg_color = hex_to_rgb(spec.color_scheme[-1]) if len(spec.color_scheme) > 2 else (0.97, 0.97, 0.95)
    page.draw_rect(fitz.Rect(0, 0, CARD_W, CARD_H), fill=bg_color)

    # Greeting text at top
    text_color = contrasting_text_color(spec.color_scheme[0])
    greeting_rect = fitz.Rect(MARGIN, MARGIN * 3, CARD_W - MARGIN, MARGIN * 3 + 60)
    _insert_text(page, greeting_rect, spec.greeting_text, body_font, 14, text_color)

    # Divider line
    mid_y = MARGIN * 3 + 70
    line_color = hex_to_rgb(spec.color_scheme[0])
    page.draw_line(
        fitz.Point(CARD_W * 0.2, mid_y),
        fitz.Point(CARD_W * 0.8, mid_y),
        color=line_color,
        width=0.5,
    )

    # Backstory blurb
    blurb_rect = fitz.Rect(MARGIN * 1.5, mid_y + 20, CARD_W - MARGIN * 1.5, CARD_H - MARGIN * 3)
    _insert_text(page, blurb_rect, spec.backstory_blurb, body_font, 11, text_color)

    # Name at bottom
    name_rect = fitz.Rect(MARGIN, CARD_H - MARGIN * 3, CARD_W - MARGIN, CARD_H - MARGIN)
    _insert_text(page, name_rect, spec.name_format, body_font, 12, text_color)


# ---------------------------------------------------------------------------
# Layout functions — one per visual_style
# ---------------------------------------------------------------------------


def layout_photo_card(
    doc: fitz.Document,
    spec: CardSpec,
    image_path: Path,
    body_font: str,
    accent_font: str,
) -> None:
    """Full-bleed photo, color bar at bottom with name + greeting."""
    page = doc.new_page(width=CARD_W, height=CARD_H)

    bar_height = 90
    # Full-bleed image
    img_rect = fitz.Rect(0, 0, CARD_W, CARD_H - bar_height)
    _insert_image(page, img_rect, image_path)

    # Color bar at bottom
    bar_color = hex_to_rgb(spec.color_scheme[0])
    bar_rect = fitz.Rect(0, CARD_H - bar_height, CARD_W, CARD_H)
    page.draw_rect(bar_rect, fill=bar_color)

    # Name text
    text_color = contrasting_text_color(spec.color_scheme[0])
    name_rect = fitz.Rect(MARGIN, CARD_H - bar_height + 10, CARD_W - MARGIN, CARD_H - bar_height + 45)
    _insert_text(page, name_rect, spec.name_format, accent_font, 18, text_color)

    # Greeting text
    greeting_rect = fitz.Rect(MARGIN, CARD_H - bar_height + 45, CARD_W - MARGIN, CARD_H - 10)
    _insert_text(page, greeting_rect, spec.greeting_text, body_font, 10, text_color)


def layout_collage(
    doc: fitz.Document,
    spec: CardSpec,
    image_path: Path,
    body_font: str,
    accent_font: str,
) -> None:
    """Image cropped into grid portions, text below."""
    page = doc.new_page(width=CARD_W, height=CARD_H)

    # Background
    bg_color = hex_to_rgb(spec.color_scheme[-1]) if len(spec.color_scheme) > 2 else (1, 1, 1)
    page.draw_rect(fitz.Rect(0, 0, CARD_W, CARD_H), fill=bg_color)

    gap = 6
    grid_top = MARGIN
    grid_height = CARD_H * 0.6
    half_w = (CARD_W - MARGIN * 2 - gap) / 2
    half_h = (grid_height - gap) / 2

    # 2x2 grid of the same image (simulating cropped portions)
    positions = [
        (MARGIN, grid_top),
        (MARGIN + half_w + gap, grid_top),
        (MARGIN, grid_top + half_h + gap),
        (MARGIN + half_w + gap, grid_top + half_h + gap),
    ]
    for x, y in positions:
        rect = fitz.Rect(x, y, x + half_w, y + half_h)
        _insert_image(page, rect, image_path)

    # Text below grid
    text_top = grid_top + grid_height + 15
    text_color = contrasting_text_color(spec.color_scheme[-1] if len(spec.color_scheme) > 2 else "#ffffff")

    name_rect = fitz.Rect(MARGIN, text_top, CARD_W - MARGIN, text_top + 40)
    _insert_text(page, name_rect, spec.name_format, accent_font, 20, text_color)

    greeting_rect = fitz.Rect(MARGIN, text_top + 45, CARD_W - MARGIN, CARD_H - MARGIN)
    _insert_text(page, greeting_rect, spec.greeting_text, body_font, 11, text_color)


def layout_typography(
    doc: fitz.Document,
    spec: CardSpec,
    image_path: Path,
    body_font: str,
    accent_font: str,
) -> None:
    """Large decorative name text, small image, greeting below."""
    page = doc.new_page(width=CARD_W, height=CARD_H)

    # Background
    bg_color = hex_to_rgb(spec.color_scheme[0])
    page.draw_rect(fitz.Rect(0, 0, CARD_W, CARD_H), fill=bg_color)

    text_color = contrasting_text_color(spec.color_scheme[0])

    # Large name at top
    name_rect = fitz.Rect(MARGIN, MARGIN * 2, CARD_W - MARGIN, MARGIN * 2 + 80)
    _insert_text(page, name_rect, spec.name_format, accent_font, 28, text_color)

    # Small centered image
    img_size = 160
    img_x = (CARD_W - img_size) / 2
    img_y = MARGIN * 2 + 100
    img_rect = fitz.Rect(img_x, img_y, img_x + img_size, img_y + img_size)
    _insert_image(page, img_rect, image_path)

    # Holiday text
    holiday_rect = fitz.Rect(MARGIN, img_y + img_size + 20, CARD_W - MARGIN, img_y + img_size + 55)
    _insert_text(page, holiday_rect, spec.holiday, accent_font, 16, text_color)

    # Greeting below
    greeting_rect = fitz.Rect(MARGIN, img_y + img_size + 60, CARD_W - MARGIN, CARD_H - MARGIN)
    _insert_text(page, greeting_rect, spec.greeting_text, body_font, 11, text_color)


def layout_minimalist(
    doc: fitz.Document,
    spec: CardSpec,
    image_path: Path,
    body_font: str,
    accent_font: str,
) -> None:
    """Centered image with whitespace, name + greeting below."""
    page = doc.new_page(width=CARD_W, height=CARD_H)

    # White background
    page.draw_rect(fitz.Rect(0, 0, CARD_W, CARD_H), fill=(1, 1, 1))

    # Centered image with generous padding
    img_size = 220
    img_x = (CARD_W - img_size) / 2
    img_y = MARGIN * 4
    img_rect = fitz.Rect(img_x, img_y, img_x + img_size, img_y + img_size)
    _insert_image(page, img_rect, image_path)

    text_top = img_y + img_size + 30
    accent_color = hex_to_rgb(spec.color_scheme[0])

    # Name
    name_rect = fitz.Rect(MARGIN, text_top, CARD_W - MARGIN, text_top + 35)
    _insert_text(page, name_rect, spec.name_format, accent_font, 16, accent_color)

    # Greeting
    greeting_rect = fitz.Rect(MARGIN * 2, text_top + 40, CARD_W - MARGIN * 2, CARD_H - MARGIN)
    _insert_text(page, greeting_rect, spec.greeting_text, body_font, 10, (0.3, 0.3, 0.3))


def layout_ornate(
    doc: fitz.Document,
    spec: CardSpec,
    image_path: Path,
    body_font: str,
    accent_font: str,
) -> None:
    """Decorative double-line border, centered image, serif text with dividers."""
    page = doc.new_page(width=CARD_W, height=CARD_H)

    # Background
    bg_color = hex_to_rgb(spec.color_scheme[-1]) if len(spec.color_scheme) > 2 else (0.98, 0.96, 0.92)
    page.draw_rect(fitz.Rect(0, 0, CARD_W, CARD_H), fill=bg_color)

    border_color = hex_to_rgb(spec.color_scheme[0])

    # Double border
    page.draw_rect(fitz.Rect(8, 8, CARD_W - 8, CARD_H - 8), color=border_color, width=1.5)
    page.draw_rect(fitz.Rect(14, 14, CARD_W - 14, CARD_H - 14), color=border_color, width=0.5)

    content_x = 30
    content_w = CARD_W - 60

    # Holiday text at top
    holiday_rect = fitz.Rect(content_x, 35, content_x + content_w, 65)
    _insert_text(page, holiday_rect, spec.holiday, accent_font, 14, border_color)

    # Top divider
    div_y = 72
    page.draw_line(
        fitz.Point(content_x + 30, div_y),
        fitz.Point(content_x + content_w - 30, div_y),
        color=border_color,
        width=0.5,
    )

    # Centered image
    img_size = 200
    img_x = (CARD_W - img_size) / 2
    img_y = 85
    img_rect = fitz.Rect(img_x, img_y, img_x + img_size, img_y + img_size)
    _insert_image(page, img_rect, image_path)

    # Bottom divider
    div_y2 = img_y + img_size + 15
    page.draw_line(
        fitz.Point(content_x + 30, div_y2),
        fitz.Point(content_x + content_w - 30, div_y2),
        color=border_color,
        width=0.5,
    )

    # Name
    text_color = contrasting_text_color(
        spec.color_scheme[-1] if len(spec.color_scheme) > 2 else "#faf5eb"
    )
    name_rect = fitz.Rect(content_x, div_y2 + 12, content_x + content_w, div_y2 + 50)
    _insert_text(page, name_rect, spec.name_format, accent_font, 18, text_color)

    # Greeting
    greeting_rect = fitz.Rect(content_x, div_y2 + 55, content_x + content_w, CARD_H - 25)
    _insert_text(page, greeting_rect, spec.greeting_text, body_font, 10, text_color)


def layout_playful(
    doc: fitz.Document,
    spec: CardSpec,
    image_path: Path,
    body_font: str,
    accent_font: str,
) -> None:
    """Colored background, offset image, bold sans text."""
    page = doc.new_page(width=CARD_W, height=CARD_H)

    # Colored background
    bg_color = hex_to_rgb(spec.color_scheme[0])
    page.draw_rect(fitz.Rect(0, 0, CARD_W, CARD_H), fill=bg_color)

    # Secondary color accent strip
    if len(spec.color_scheme) > 1:
        accent_color = hex_to_rgb(spec.color_scheme[1])
        page.draw_rect(fitz.Rect(0, 0, 25, CARD_H), fill=accent_color)

    text_color = contrasting_text_color(spec.color_scheme[0])

    # Offset image (right-aligned, slightly down)
    img_w = 240
    img_h = 240
    img_x = CARD_W - img_w - MARGIN
    img_y = MARGIN * 3
    img_rect = fitz.Rect(img_x, img_y, img_x + img_w, img_y + img_h)
    _insert_image(page, img_rect, image_path)

    # Name text (left-aligned, bold feel via larger size)
    name_rect = fitz.Rect(35, img_y + img_h + 20, CARD_W - MARGIN, img_y + img_h + 70)
    _insert_text(
        page, name_rect, spec.name_format, accent_font, 22, text_color,
        align=fitz.TEXT_ALIGN_LEFT,
    )

    # Greeting text
    greeting_rect = fitz.Rect(35, img_y + img_h + 75, CARD_W - MARGIN, CARD_H - MARGIN)
    _insert_text(
        page, greeting_rect, spec.greeting_text, body_font, 11, text_color,
        align=fitz.TEXT_ALIGN_LEFT,
    )


def layout_vintage(
    doc: fitz.Document,
    spec: CardSpec,
    image_path: Path,
    body_font: str,
    accent_font: str,
) -> None:
    """Aged paper look, sepia tones, retro typography, scalloped inner border."""
    page = doc.new_page(width=CARD_W, height=CARD_H)

    # Aged paper background
    page.draw_rect(fitz.Rect(0, 0, CARD_W, CARD_H), fill=(0.96, 0.93, 0.87))

    # Scalloped/dotted inner border
    border_color = hex_to_rgb(spec.color_scheme[0]) if spec.color_scheme else (0.6, 0.5, 0.4)
    inset = 12
    page.draw_rect(
        fitz.Rect(inset, inset, CARD_W - inset, CARD_H - inset),
        color=border_color, width=0.8, dashes="[3 3]",
    )

    # Centered image with thick "frame" border
    img_size = 200
    img_x = (CARD_W - img_size) / 2
    img_y = 50
    frame_pad = 6
    frame_rect = fitz.Rect(
        img_x - frame_pad, img_y - frame_pad,
        img_x + img_size + frame_pad, img_y + img_size + frame_pad,
    )
    page.draw_rect(frame_rect, fill=(1, 1, 1), color=border_color, width=1)
    _insert_image(page, fitz.Rect(img_x, img_y, img_x + img_size, img_y + img_size), image_path)

    # Holiday text
    text_top = img_y + img_size + frame_pad + 20
    holiday_rect = fitz.Rect(MARGIN, text_top, CARD_W - MARGIN, text_top + 30)
    _insert_text(page, holiday_rect, spec.holiday, accent_font, 13, border_color)

    # Name
    name_rect = fitz.Rect(MARGIN, text_top + 35, CARD_W - MARGIN, text_top + 70)
    _insert_text(page, name_rect, spec.name_format, accent_font, 18, (0.3, 0.25, 0.2))

    # Greeting
    greeting_rect = fitz.Rect(MARGIN * 2, text_top + 75, CARD_W - MARGIN * 2, CARD_H - 25)
    _insert_text(page, greeting_rect, spec.greeting_text, body_font, 10, (0.4, 0.35, 0.3))


def layout_modern_grid(
    doc: fitz.Document,
    spec: CardSpec,
    image_path: Path,
    body_font: str,
    accent_font: str,
) -> None:
    """3-across photo strip, clean sans-serif text, thin borders."""
    page = doc.new_page(width=CARD_W, height=CARD_H)

    # Clean white background
    page.draw_rect(fitz.Rect(0, 0, CARD_W, CARD_H), fill=(1, 1, 1))

    # Thin accent line at top
    accent_color = hex_to_rgb(spec.color_scheme[0]) if spec.color_scheme else (0.2, 0.2, 0.2)
    page.draw_line(fitz.Point(0, 3), fitz.Point(CARD_W, 3), color=accent_color, width=2)

    # 3-across photo strip
    gap = 5
    strip_top = 40
    photo_w = (CARD_W - MARGIN * 2 - gap * 2) / 3
    photo_h = photo_w  # square
    for col in range(3):
        x = MARGIN + col * (photo_w + gap)
        rect = fitz.Rect(x, strip_top, x + photo_w, strip_top + photo_h)
        _insert_image(page, rect, image_path)

    # Text area below photos
    text_top = strip_top + photo_h + 25

    # Name
    name_rect = fitz.Rect(MARGIN, text_top, CARD_W - MARGIN, text_top + 35)
    _insert_text(page, name_rect, spec.name_format, body_font, 16, accent_color)

    # Thin divider
    div_y = text_top + 42
    page.draw_line(
        fitz.Point(CARD_W * 0.3, div_y), fitz.Point(CARD_W * 0.7, div_y),
        color=(0.8, 0.8, 0.8), width=0.5,
    )

    # Greeting
    greeting_rect = fitz.Rect(MARGIN * 2, div_y + 10, CARD_W - MARGIN * 2, CARD_H - MARGIN)
    _insert_text(page, greeting_rect, spec.greeting_text, body_font, 10, (0.3, 0.3, 0.3))


def layout_full_bleed(
    doc: fitz.Document,
    spec: CardSpec,
    image_path: Path,
    body_font: str,
    accent_font: str,
) -> None:
    """Photo fills entire page, text overlaid with semi-transparent backing."""
    page = doc.new_page(width=CARD_W, height=CARD_H)

    # Full-bleed image
    _insert_image(page, fitz.Rect(0, 0, CARD_W, CARD_H), image_path)

    # Semi-transparent dark band at bottom for text
    band_height = 100
    band_rect = fitz.Rect(0, CARD_H - band_height, CARD_W, CARD_H)
    page.draw_rect(band_rect, fill=(0, 0, 0))
    # Draw again with opacity for overlay effect (PyMuPDF fills are opaque,
    # so we use a dark color that looks like an overlay)
    page.draw_rect(band_rect, fill=(0.1, 0.1, 0.1))

    # Name text (large, white, bold feel)
    name_rect = fitz.Rect(MARGIN, CARD_H - band_height + 15, CARD_W - MARGIN, CARD_H - band_height + 55)
    _insert_text(page, name_rect, spec.name_format, accent_font, 22, (1, 1, 1))

    # Greeting text
    greeting_rect = fitz.Rect(MARGIN, CARD_H - band_height + 55, CARD_W - MARGIN, CARD_H - 10)
    _insert_text(page, greeting_rect, spec.greeting_text, body_font, 10, (0.85, 0.85, 0.85))


def layout_polaroid(
    doc: fitz.Document,
    spec: CardSpec,
    image_path: Path,
    body_font: str,
    accent_font: str,
) -> None:
    """Photo as a tilted polaroid snapshot on a colored background."""
    page = doc.new_page(width=CARD_W, height=CARD_H)

    # Colored background
    bg_color = hex_to_rgb(spec.color_scheme[-1]) if len(spec.color_scheme) > 2 else (0.95, 0.94, 0.92)
    page.draw_rect(fitz.Rect(0, 0, CARD_W, CARD_H), fill=bg_color)

    # Polaroid frame (white rectangle, thicker at bottom for caption area)
    frame_pad_sides = 12
    frame_pad_top = 12
    frame_pad_bottom = 50
    photo_size = 210
    frame_x = (CARD_W - photo_size - frame_pad_sides * 2) / 2
    frame_y = 40

    # Slight rotation via a skewed shadow (approximation — draw offset dark rect)
    shadow_offset = 3
    shadow_rect = fitz.Rect(
        frame_x + shadow_offset, frame_y + shadow_offset,
        frame_x + photo_size + frame_pad_sides * 2 + shadow_offset,
        frame_y + photo_size + frame_pad_top + frame_pad_bottom + shadow_offset,
    )
    page.draw_rect(shadow_rect, fill=(0.8, 0.8, 0.8))

    # White polaroid frame
    frame_rect = fitz.Rect(
        frame_x, frame_y,
        frame_x + photo_size + frame_pad_sides * 2,
        frame_y + photo_size + frame_pad_top + frame_pad_bottom,
    )
    page.draw_rect(frame_rect, fill=(1, 1, 1))

    # Photo inside frame
    photo_rect = fitz.Rect(
        frame_x + frame_pad_sides, frame_y + frame_pad_top,
        frame_x + frame_pad_sides + photo_size, frame_y + frame_pad_top + photo_size,
    )
    _insert_image(page, photo_rect, image_path)

    # Caption inside polaroid bottom area (handwriting-style)
    caption_rect = fitz.Rect(
        frame_x + frame_pad_sides,
        frame_y + frame_pad_top + photo_size + 5,
        frame_x + frame_pad_sides + photo_size,
        frame_y + frame_pad_top + photo_size + frame_pad_bottom - 5,
    )
    _insert_text(page, caption_rect, spec.name_format, accent_font, 14, (0.3, 0.3, 0.3))

    # Greeting below polaroid
    text_top = frame_y + photo_size + frame_pad_top + frame_pad_bottom + 20
    text_color = contrasting_text_color(spec.color_scheme[-1] if len(spec.color_scheme) > 2 else "#f2f0eb")

    greeting_rect = fitz.Rect(MARGIN, text_top, CARD_W - MARGIN, text_top + 40)
    _insert_text(page, greeting_rect, spec.greeting_text, body_font, 11, text_color)

    # Holiday at bottom
    holiday_rect = fitz.Rect(MARGIN, CARD_H - 40, CARD_W - MARGIN, CARD_H - 15)
    _insert_text(page, holiday_rect, spec.holiday, accent_font, 12, text_color)


def layout_border_frame(
    doc: fitz.Document,
    spec: CardSpec,
    image_path: Path,
    body_font: str,
    accent_font: str,
) -> None:
    """Thick decorative border framing a centered photo with text above/below."""
    page = doc.new_page(width=CARD_W, height=CARD_H)

    # Background
    bg_color = hex_to_rgb(spec.color_scheme[-1]) if len(spec.color_scheme) > 2 else (1, 1, 1)
    page.draw_rect(fitz.Rect(0, 0, CARD_W, CARD_H), fill=bg_color)

    border_color = hex_to_rgb(spec.color_scheme[0])
    accent2 = hex_to_rgb(spec.color_scheme[1]) if len(spec.color_scheme) > 1 else border_color

    # Thick outer border
    page.draw_rect(fitz.Rect(6, 6, CARD_W - 6, CARD_H - 6), color=border_color, width=4)

    # Thin inner border with second color
    page.draw_rect(fitz.Rect(14, 14, CARD_W - 14, CARD_H - 14), color=accent2, width=1)

    # Corner accents (small filled squares)
    corner_size = 8
    for cx, cy in [(14, 14), (CARD_W - 14 - corner_size, 14),
                   (14, CARD_H - 14 - corner_size), (CARD_W - 14 - corner_size, CARD_H - 14 - corner_size)]:
        page.draw_rect(fitz.Rect(cx, cy, cx + corner_size, cy + corner_size), fill=border_color)

    content_x = 30
    content_w = CARD_W - 60

    # Holiday text at top
    holiday_rect = fitz.Rect(content_x, 30, content_x + content_w, 55)
    _insert_text(page, holiday_rect, spec.holiday, accent_font, 13, border_color)

    # Centered image
    img_w = 210
    img_h = 180
    img_x = (CARD_W - img_w) / 2
    img_y = 65
    _insert_image(page, fitz.Rect(img_x, img_y, img_x + img_w, img_y + img_h), image_path)

    # Name below image
    text_top = img_y + img_h + 15
    text_color = contrasting_text_color(spec.color_scheme[-1] if len(spec.color_scheme) > 2 else "#ffffff")
    name_rect = fitz.Rect(content_x, text_top, content_x + content_w, text_top + 35)
    _insert_text(page, name_rect, spec.name_format, accent_font, 18, text_color)

    # Greeting
    greeting_rect = fitz.Rect(content_x, text_top + 40, content_x + content_w, CARD_H - 25)
    _insert_text(page, greeting_rect, spec.greeting_text, body_font, 10, text_color)


# Layout dispatch
LAYOUT_FNS: dict[str, type[None] | object] = {
    "photo_card": layout_photo_card,
    "collage": layout_collage,
    "typography": layout_typography,
    "minimalist": layout_minimalist,
    "ornate": layout_ornate,
    "playful": layout_playful,
    "vintage": layout_vintage,
    "modern_grid": layout_modern_grid,
    "full_bleed": layout_full_bleed,
    "polaroid": layout_polaroid,
    "border_frame": layout_border_frame,
}


# ---------------------------------------------------------------------------
# PDF composition
# ---------------------------------------------------------------------------


def _rasterize_doc(doc: fitz.Document, dpi: int = 200) -> fitz.Document:
    """Rasterize every page of a document so the final PDF has no selectable text.

    Renders each page to a pixmap at the given DPI, then builds a new document
    where each page is a single full-bleed image.  This ensures OCR is required
    to extract any text from the resulting PDF.
    """
    raster_doc = fitz.open()
    for page in doc:
        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)

        # Create a new page with the same dimensions as the original
        new_page = raster_doc.new_page(width=page.rect.width, height=page.rect.height)
        new_page.insert_image(new_page.rect, pixmap=pix)

    return raster_doc


def compose_pdf(
    spec: CardSpec,
    image_path: Path,
    output_path: Path,
) -> None:
    """Compose a greeting card PDF from a CardSpec and image.

    The layout is built with vector text and images, then rasterized so the
    final PDF contains only images — no selectable text.  This makes the
    generated cards realistic targets for OCR testing.
    """
    doc = fitz.open()

    body_font = _resolve_font(spec.font_family) or FALLBACK_BODY
    accent_font = _resolve_font(spec.font_accent) or FALLBACK_ACCENT

    # Get layout function
    layout_fn = LAYOUT_FNS.get(spec.visual_style, layout_photo_card)

    # Render front page
    layout_fn(doc, spec, image_path, body_font, accent_font)  # type: ignore[operator]

    # Add backstory page if multi-page
    if spec.page_count >= 2:
        _add_backstory_page(doc, spec, body_font)

    # Rasterize all pages so text is only in image pixels (requires OCR)
    raster_doc = _rasterize_doc(doc)
    doc.close()

    raster_doc.save(str(output_path), deflate=True, garbage=3)
    raster_doc.close()


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------


def validate_api_keys(no_images: bool) -> bool:
    """Check for required API keys. Returns True if valid."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY environment variable is required.")
        print("  Set it with: export ANTHROPIC_API_KEY=your-key-here")
        return False

    if not no_images and not os.environ.get("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY environment variable is required for image generation.")
        print("  Set it with: export OPENAI_API_KEY=your-key-here")
        print("  Or use --no-images to skip image generation.")
        return False

    return True


async def _process_layout_card(
    client: openai.AsyncOpenAI,
    semaphore: asyncio.Semaphore,
    job: CardJob,
    spec: CardSpec,
    tmp_path: Path,
    output_dir: Path,
    image_quality: str,
    image_model: str,
    no_images: bool,
) -> bool:
    """Generate image + compose PDF for one layout card. Returns True on success."""
    image_file = tmp_path / f"layout_{job.index:03d}.png"

    # Generate image
    if no_images:
        placeholder_color = spec.color_scheme[0] if spec.color_scheme else "#666688"
        generate_placeholder_image(placeholder_color, image_file)
        job.set("placeholder")
    else:
        success = await generate_image_openai_async(
            client, semaphore, job, spec.image_prompt, image_file, image_quality,
            model=image_model,
        )
        if not success:
            placeholder_color = spec.color_scheme[0] if spec.color_scheme else "#666688"
            generate_placeholder_image(placeholder_color, image_file)

    # Compose and save PDF
    job.set("composing")
    pdf_path = output_dir / spec.filename
    try:
        compose_pdf(spec, image_file, pdf_path)
        job.set("done", f"{spec.visual_style}, {spec.page_count}p")
        return True
    except Exception as e:
        job.set("error", str(e)[:50])
        return False


async def _process_full_image_card(
    client: openai.AsyncOpenAI,
    semaphore: asyncio.Semaphore,
    job: CardJob,
    spec: CardSpec,
    global_index: int,
    tmp_path: Path,
    output_dir: Path,
    image_quality: str,
    image_model: str,
    no_images: bool,
) -> bool:
    """Generate full card images + compose PDF. Returns True on success."""
    card_images = await generate_full_card_images_async(
        client, semaphore, job, spec, tmp_path, global_index, image_quality,
        no_images, image_model=image_model,
    )

    job.set("composing")
    pdf_path = output_dir / spec.filename
    try:
        compose_pdf_from_images(card_images, pdf_path)
        pages_tag = f"{len(card_images)}p"
        job.set("done", f"full-image, {pages_tag}")
        return True
    except Exception as e:
        job.set("error", str(e)[:50])
        return False


async def async_main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate sample greeting card PDFs for testing and demos.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "output_dir",
        nargs="?",
        default=None,
        help="Output directory (default: _script_output/YYYYMMDD_HHMM-generate_sample_cards/)",
    )
    parser.add_argument(
        "--layout-cards",
        type=int,
        default=None,
        metavar="N",
        help="Number of layout-based cards (AI photo + PyMuPDF composition). "
        "Default: 3 if neither flag is passed.",
    )
    parser.add_argument(
        "--full-image-cards",
        type=int,
        default=None,
        metavar="N",
        help="Number of full-image cards (entire card generated by AI in "
        "Shutterfly/Minted style).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Seed for soft reproducibility via prompt (default: random)",
    )
    parser.add_argument(
        "--no-images",
        action="store_true",
        help="Skip OpenAI image generation; use colored placeholders",
    )
    parser.add_argument(
        "--ai-model",
        default="claude-sonnet-4-6",
        help="Claude model for spec generation (default: claude-sonnet-4-6)",
    )
    parser.add_argument(
        "--image-model",
        default="gpt-image-1.5",
        help="OpenAI image model (default: gpt-image-1.5)",
    )
    parser.add_argument(
        "--image-quality",
        choices=["low", "medium", "high"],
        default="high",
        help="OpenAI image quality (default: high)",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Don't open output folder when done",
    )
    args = parser.parse_args()

    # Default: 3 layout cards if neither flag is passed
    if args.layout_cards is None and args.full_image_cards is None:
        args.layout_cards = 3
    layout_count = args.layout_cards or 0
    full_image_count = args.full_image_cards or 0
    total_count = layout_count + full_image_count

    # Resolve output directory
    if args.output_dir:
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
    else:
        output_dir = make_output_dir("generate_sample_cards")

    # Validate API keys
    if not validate_api_keys(args.no_images):
        sys.exit(1)

    start_time = time.time()
    all_specs: list[CardSpec] = []

    # Describe what we're generating
    parts = []
    if layout_count:
        parts.append(f"{layout_count} layout")
    if full_image_count:
        parts.append(f"{full_image_count} full-image")
    print(f"Plan: {' + '.join(parts)} cards ({total_count} total)\n")

    # Step 1: Generate card specs (single Claude call — stays sync)
    specs = generate_card_specs(total_count, args.seed, args.ai_model)

    # Split specs into layout and full-image batches
    layout_specs = specs[:layout_count]
    full_image_specs = specs[layout_count:layout_count + full_image_count]
    all_specs = layout_specs + full_image_specs

    # Concurrency: 6 concurrent OpenAI image requests
    # Client uses a dummy key when --no-images (never called, avoids init error)
    openai_client = openai.AsyncOpenAI(
        api_key=os.environ.get("OPENAI_API_KEY") or "unused",
    )
    openai_semaphore = asyncio.Semaphore(6)
    image_src = "placeholders" if args.no_images else args.image_model

    # Build CardJob list for the live display
    jobs: list[CardJob] = []
    for i, spec in enumerate(layout_specs):
        jobs.append(CardJob(
            index=i + 1, card_type="layout",
            filename=spec.filename, style=spec.visual_style,
        ))
    for i, spec in enumerate(full_image_specs):
        jobs.append(CardJob(
            index=len(layout_specs) + i + 1, card_type="full-image",
            filename=spec.filename, style=spec.visual_style,
        ))

    # Step 2: Process cards concurrently with live status display
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        with Live(_build_status_table(jobs, image_src), refresh_per_second=4) as live:
            async_tasks: list[asyncio.Task[bool]] = []

            for i, spec in enumerate(layout_specs):
                task = asyncio.create_task(_process_layout_card(
                    openai_client, openai_semaphore, jobs[i], spec,
                    tmp_path, output_dir, args.image_quality, args.image_model,
                    args.no_images,
                ))
                async_tasks.append(task)

            for i, spec in enumerate(full_image_specs):
                job_idx = len(layout_specs) + i
                task = asyncio.create_task(_process_full_image_card(
                    openai_client, openai_semaphore, jobs[job_idx], spec,
                    layout_count + i, tmp_path, output_dir, args.image_quality,
                    args.image_model, args.no_images,
                ))
                async_tasks.append(task)

            # Refresh the table while tasks run
            while not all(t.done() for t in async_tasks):
                live.update(_build_status_table(jobs, image_src))
                await asyncio.sleep(0.25)

            # Final update
            live.update(_build_status_table(jobs, image_src))
            results = [t.result() for t in async_tasks]

    await openai_client.close()
    created = sum(results)

    # Summary
    elapsed = time.time() - start_time
    print(f"\nGenerated {created}/{len(all_specs)} cards in {elapsed:.1f}s")
    if layout_specs:
        print(f"  Layout cards: {len(layout_specs)}")
    if full_image_specs:
        print(f"  Full-image cards: {len(full_image_specs)}")
    print(f"Output: {output_dir}")

    # Style distribution
    style_counts: dict[str, int] = {}
    for spec in all_specs:
        style_counts[spec.visual_style] = style_counts.get(spec.visual_style, 0) + 1
    print(f"Styles: {', '.join(f'{k}={v}' for k, v in sorted(style_counts.items()))}")

    # Holiday distribution
    holiday_counts: dict[str, int] = {}
    for spec in all_specs:
        holiday_counts[spec.holiday] = holiday_counts.get(spec.holiday, 0) + 1
    print(f"Holidays: {len(holiday_counts)} types")

    # Page count distribution
    multi_page = sum(1 for s in all_specs if s.page_count >= 2)
    print(f"Multi-page: {multi_page}/{len(all_specs)} ({100 * multi_page / len(all_specs):.0f}%)")

    # Open output folder
    if not args.no_open:
        try:
            subprocess.run(["open", str(output_dir)], check=False)
        except FileNotFoundError:
            pass


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
