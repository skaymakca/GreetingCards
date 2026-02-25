"""CLI parsing, API key validation, and main async flow."""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import openai
from rich.console import Console
from rich.live import Live

from scripts.generate_sample_cards.display import build_status_table
from scripts.generate_sample_cards.image_generator import (
    RateLimitGate,
    generate_full_card_images_async,
)
from scripts.generate_sample_cards.models import CardJob, CardSpec
from scripts.generate_sample_cards.pdf_composer import compose_pdf_from_images
from scripts.generate_sample_cards.spec_generator import generate_card_specs
from scripts.helpers import make_output_dir


def validate_api_keys() -> bool:
    """Check for required API keys. Returns True if valid."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY environment variable is required.")
        print("  Set it with: export ANTHROPIC_API_KEY=your-key-here")
        return False

    if not os.environ.get("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY environment variable is required for image generation.")
        print("  Set it with: export OPENAI_API_KEY=your-key-here")
        return False

    return True


async def _process_card(
    client: openai.AsyncOpenAI,
    semaphore: asyncio.Semaphore,
    gate: RateLimitGate,
    job: CardJob,
    spec: CardSpec,
    index: int,
    tmp_path: Path,
    output_dir: Path,
    image_quality: str,
    image_model: str,
) -> bool:
    """Generate full card images + compose PDF. Returns True on success."""
    card_images = await generate_full_card_images_async(
        client,
        semaphore,
        gate,
        job,
        spec,
        tmp_path,
        index,
        image_quality,
        image_model=image_model,
    )

    if not card_images:
        job.set("error", "no images generated")
        return False

    job.set("composing")
    pdf_path = output_dir / spec.filename
    try:
        compose_pdf_from_images(card_images, pdf_path)
        job.set("done", f"{len(card_images)}p")
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
        help="Output directory (default: _build/script_output/YYYYMMDD_HHMM-generate_sample_cards/)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=3,
        metavar="N",
        help="Number of cards to generate (default: 3)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Seed for soft reproducibility via prompt (default: random)",
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
        "--concurrency",
        type=int,
        default=5,
        metavar="N",
        help="Max concurrent OpenAI image requests (default: 5)",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Don't open output folder when done",
    )
    args = parser.parse_args()

    count = args.count

    # Resolve output directory
    if args.output_dir:
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
    else:
        output_dir = make_output_dir("generate_sample_cards")

    # Validate API keys
    if not validate_api_keys():
        sys.exit(1)

    console = Console(highlight=False)
    start_time = time.time()

    console.print(f"Plan: {count} cards\n")

    # Step 1: Generate card specs (with spinner)
    specs = generate_card_specs(count, args.seed, args.ai_model)

    # Concurrency: 6 concurrent OpenAI image requests, shared rate limit gate
    openai_client = openai.AsyncOpenAI()
    openai_semaphore = asyncio.Semaphore(args.concurrency)
    rate_limit_gate = RateLimitGate()

    # Build CardJob list for the live display
    jobs: list[CardJob] = []
    for i, spec in enumerate(specs):
        jobs.append(
            CardJob(
                index=i + 1,
                filename=spec.filename,
                pages=spec.page_count,
                style=spec.visual_style,
            )
        )

    # Step 2: Process cards concurrently with live status display
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        with Live(
            build_status_table(jobs, args.image_model),
            refresh_per_second=10,
            console=console,
        ) as live:
            async_tasks: list[asyncio.Task[bool]] = []

            for i, spec in enumerate(specs):
                task = asyncio.create_task(
                    _process_card(
                        openai_client,
                        openai_semaphore,
                        rate_limit_gate,
                        jobs[i],
                        spec,
                        i,
                        tmp_path,
                        output_dir,
                        args.image_quality,
                        args.image_model,
                    )
                )
                async_tasks.append(task)

            # Refresh the table while tasks run
            while not all(t.done() for t in async_tasks):
                live.update(build_status_table(jobs, args.image_model))
                await asyncio.sleep(0.1)

            # Final update
            live.update(build_status_table(jobs, args.image_model))
            results = [t.result() for t in async_tasks]

    await openai_client.close()
    created = sum(results)

    # Summary
    elapsed = time.time() - start_time
    console.print(f"\nGenerated {created}/{len(specs)} cards in {elapsed:.1f}s")
    console.print(f"Output: {output_dir}")

    # Style distribution
    style_counts: dict[str, int] = {}
    for spec in specs:
        style_counts[spec.visual_style] = style_counts.get(spec.visual_style, 0) + 1
    console.print(f"Styles: {', '.join(f'{k}={v}' for k, v in sorted(style_counts.items()))}")

    # Holiday distribution
    holiday_counts: dict[str, int] = {}
    for spec in specs:
        holiday_counts[spec.holiday] = holiday_counts.get(spec.holiday, 0) + 1
    console.print(f"Holidays: {len(holiday_counts)} types")

    # Page count distribution
    multi_page = sum(1 for s in specs if s.page_count >= 2)
    console.print(f"Multi-page: {multi_page}/{len(specs)} ({100 * multi_page / len(specs):.0f}%)")

    # Open output folder
    if not args.no_open:
        try:
            subprocess.run(["open", str(output_dir)], check=False)
        except FileNotFoundError:
            pass


def main() -> None:
    asyncio.run(async_main())
