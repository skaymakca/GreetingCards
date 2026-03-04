# Sample Card Generator Architecture

## Key Files

```
scripts/generate_sample_cards/
  __main__.py          # Entry point: calls cli.main()
  cli.py               # CLI parsing, API key validation, async orchestration
  models.py            # CardSpec, CardJob, FamilyMember dataclasses
  spec_generator.py    # Top-level pipeline: deterministic assignment → multiphase generation
  image_generator.py   # OpenAI image generation, RateLimitGate, prompt templates
  pdf_composer.py      # PyMuPDF assembly from temp images
  display.py           # Rich live table rendering

scripts/generate_sample_cards/spec_generators/
  __init__.py          # Public API exports
  constants.py         # HOLIDAYS, VISUAL_STYLES, FILENAME_TEMPLATES, BACK_PAGE_TYPES, BACK_PHOTO_MODES, etc.
  formatting.py        # Deterministic field assignment, filename template filling
  family_names.py      # Phase 1a: unique family name generation (single Claude call)
  color_schemes.py     # Phase 1b: batched color scheme generation
  subtitles.py         # Phase 1c: batched subtitle / "from" line generation
  card_content.py      # Phase 2: per-card creative content (N concurrent calls, 3 prompt variants)
  utils.py             # JSON extraction from Claude responses
```

## Architecture Overview

```
CLI (argparse)
  │
  ├─ Spec Generation Pipeline ──────────────────────────────────────────────┐
  │                                                                         │
  │  assign_generated_fields(count)                                     │
  │    → holidays, visual_styles, page_counts, back_page_types,             │
  │      back_photo_modes (Python)                                          │
  │                                                                         │
  │  Phase 1a: generate_family_names_async()                                │
  │    → 1 Claude call → N unique family names                              │
  │                                                                         │
  │  Phase 1b: generate_color_schemes_async()                               │
  │    → batched Claude calls (up to 20/batch) → N color palettes           │
  │                                                                         │
  │  Phase 1c: generate_subtitles_async()                                   │
  │    → batched Claude calls (up to 20/batch) → N subtitle strings         │
  │                                                                         │
  │  Phase 2: generate_card_content_async() × N                             │
  │    → N concurrent Claude calls (semaphore-gated)                        │
  │    → family members, greeting, backstory/back content, image prompt     │
  │                                                                         │
  │  → list[CardSpec]                                                       │
  ├─────────────────────────────────────────────────────────────────────────┘
  │
  ├─ Image Generation (OpenAI) ─────────────────────────────────────────────┐
  │    generate_full_card_images_async() × N                                │
  │      → front image (always) + back image (if 2-page)                    │
  │      → back page type: "blurb" (text) or "photo" (imagery)             │
  │      → semaphore-gated, RateLimitGate coordinated                       │
  │      → PNG files in temp directory                                      │
  ├─────────────────────────────────────────────────────────────────────────┘
  │
  ├─ PDF Composition ───────────────────────────────────────────────────────┐
  │    compose_pdf_from_images()                                            │
  │      → 5×7" pages, JPEG Q75 (or lossless PNG with --no-image-compression)│
  │      → temp images cleaned up after                                     │
  ├─────────────────────────────────────────────────────────────────────────┘
  │
  └─ Rich Live Table (display updates at 10 Hz while images generate)
```

## Rationale: Splitting Spec Generation

The original design used a single mega-prompt asking Claude to generate all card specs at once. This caused several
problems:

1. **Repeated family names.** Claude would reuse the same 3-4 names across 20 cards, reducing corpus diversity.
2. **Fragile JSON.** A single call returning a large JSON array was prone to truncation and parse errors.
3. **Slow single call.** One sequential call for 20+ cards took 30-60 seconds with no parallelism.
4. **Poor subtitle quality.** Template-based string substitution (`"{first1} & {first2} {surname}"`) produced ugly
   results when names didn't match the template's expectations.

The current design splits generation into deterministic assignment (Python) + four focused AI phases, each with its own
prompt and concurrency model.

## Deterministic vs AI-Generated Fields

| Field               | Source      | Why                                                                        |
|---------------------|-------------|----------------------------------------------------------------------------|
| `holiday`           | Python      | Round-robin + shuffle ensures even distribution                            |
| `visual_style`      | Python      | Round-robin + shuffle ensures variety; aesthetic styles only (no layout)   |
| `page_count`        | Python      | Weighted random (80% two-page, 20% one-page)                               |
| `back_page_type`    | Python      | Weighted random (75% photo, 25% blurb) for 2-page cards                    |
| `back_photo_mode`   | Python      | Weighted random (60% collage, 40% single) for photo-type back pages        |
| `filename`          | Python      | Template chosen by weighted random, filled with deterministic placeholders |
| `family_size_hint`  | Python      | Weighted random hint passed to Claude for family composition               |
| `family_name`       | Claude (1a) | Cultural diversity requires AI taste; uniqueness enforced post-generation  |
| `color_scheme`      | Claude (1b) | Color harmony for holiday+style combos requires aesthetic judgment         |
| `name_format`       | Claude (1c) | Subtitle / "from" line needs creative natural-language formatting          |
| `family_members`    | Claude (2)  | Names, roles, ages need to be coherent and culturally appropriate          |
| `greeting_text`     | Claude (2)  | Creative writing tailored to holiday and family                            |
| `backstory_blurb`   | Claude (2)  | Creative writing for blurb-type back pages                                 |
| `back_greeting`     | Claude (2)  | Short greeting for photo-type back pages                                   |
| `back_image_prompt` | Claude (2)  | Holiday imagery description for photo-type back pages                      |
| `image_prompt`      | Claude (2)  | Detailed visual description needs creative and contextual judgment         |

## Phase 1a: Family Names

**File:** `spec_generators/family_names.py`

A single Claude call generates N unique, culturally diverse family names. The prompt requests representation across
Anglo, Hispanic, East Asian, South Asian, African, Eastern European, and other cultures. Post-processing:

- Parses JSON array via `extract_json()`
- Deduplicates
- Trims to exactly N (or pads with `Family1`, `Family2`, ... if too few)

**Cost:** 1 API call regardless of count.

## Phase 1b: Color Schemes

**File:** `spec_generators/color_schemes.py`

Generates 2-3 hex color palettes for each card's holiday + visual_style combination. Batched into groups of up to 20
pairs per Claude call, with batches fired concurrently via `asyncio.gather()`.

**Why AI?** Color harmony is subjective — a "vintage Christmas" card needs different tones than a "modern grid Diwali"
card. Claude handles this taste-based decision better than a lookup table.

**Fallback:** If a batch returns fewer results than expected, missing entries get a neutral grayscale palette (
`["#333333", "#666666", "#999999"]`).

**Cost:** ceil(N / 20) API calls.

## Phase 1c: Subtitles

**File:** `spec_generators/subtitles.py`

Generates natural "from" lines / subtitles for each card. Batched the same way as color schemes (up to 20 per call).
Each subtitle is a single finished string like "The Garcias", "Bob & Sue Martinez", or "Bob, Sue, Lily (8) & Max (5)
Johnson".

**Why AI?** Template-based filling produced unnatural results. The LLM has creative judgment to vary style (formal vs
casual, with/without ages, family name only, etc.) and produce culturally appropriate pluralizations.

**Fallback:** If Claude returns fewer than expected, missing entries get `"The {family_name} Family"`.

**Cost:** ceil(N / 20) API calls.

## Phase 2: Card Content

**File:** `spec_generators/card_content.py`

N concurrent Claude calls, each generating one card's creative content. Three prompt variants (
`SINGLE_CARD_FRONT_CONTENT_PROMPT`, `DUAL_CARD_BLURB_CONTENT_PROMPT`, `DUAL_CARD_PHOTO_CONTENT_PROMPT`) are selected
based on page count and back page type:

**All cards:**

- `family_members` — array of `{first_name, role, age}` matching the family_size_hint
- `greeting_text` — warm 1-2 sentence holiday greeting
- `image_prompt` — detailed photorealistic family photo description

**Blurb back page** (25% of 2-page cards):

- `backstory_blurb` — 3-6 sentences about the family's year

**Photo back page** (75% of 2-page cards):

- `back_greeting` — short 1-2 sentence holiday greeting (different from front)
- `back_image_prompt` — layout concept, composition, and framing (not people descriptions — those come from the front
  image reference)

Each call is gated by an `asyncio.Semaphore(text_concurrency)` (default 10) and coordinated by a shared `RateLimitGate`.
The subtitle is passed in so Claude writes content consistent with the established "from" identity. On failure after 3
retries with exponential backoff, the card is skipped.

**Cost:** N API calls (minus any that fail).

## Concurrency & Rate Limiting

**Clients:** `AsyncAnthropic` (Claude) and `AsyncOpenAI` (image generation).

**Semaphores:** Two independent semaphores control concurrent API calls:

- `--text-concurrency` (default 10) — Claude spec-generation calls in Phase 2
- `--image-concurrency` (default 5) — OpenAI image generation calls

**`RateLimitGate`** (defined in `image_generator.py`, reused for spec generation):

- A shared coordination point that pauses ALL concurrent tasks when any task hits a rate limit
- No locks needed — asyncio is single-threaded (cooperative multitasking)
- `pause(seconds)` — sets a monotonic resume timestamp; takes the max if already paused
- `wait_if_paused(job)` — called before acquiring the semaphore; sleeps with countdown if paused
- Prevents thundering herd: when the gate lifts, tasks still queue through the semaphore
- Separate gate instances for Claude (spec generation) and OpenAI (image generation)

**Retry strategy:**

- Parse `retry-after-ms` or `retry-after` headers from the error response
- Fall back to 10 seconds if neither header is present
- Phase 2 card content: 3 attempts with exponential backoff (2, 4, 8 seconds)
- Image generation: 5 attempts with exponential backoff (2, 4, 8, 16, 32 seconds)

## Why OpenAI for Images

Claude doesn't generate images. OpenAI's `gpt-image-1.5` was chosen for greeting card generation because of its
relatively strong typography rendering — critical for cards where names, greetings, and backstory text must appear
legible within the artwork.

**Text rendering best practices in prompts:**

- Spell out names letter-by-letter (e.g., "S-M-I-T-H") via `_spell_out()` helper
- Request text in ALL CAPS for better AI rendering accuracy
- Wrap literal text in quotes to distinguish from instructions
- Explicit "do not repeat text" instruction to prevent duplicate rendering
- "Fully clothed and family-friendly" safety language to avoid moderation blocks
- Back page prompts let the model choose fonts that complement the front (no prescriptive font specs)

## Image Generation Pipeline

**File:** `image_generator.py`

Four module-level prompt templates:

- `FRONT_PAGE_PROMPT` — full-bleed photorealistic card with family photo, subtitle, greeting
- `BACK_BLURB_PROMPT` — text-focused back page with backstory and signature
- `BACK_PHOTO_SINGLE_PROMPT` — single photo back page (same shoot as front, distinctly different composition)
- `BACK_PHOTO_COLLAGE_PROMPT` — collage back page (multiple visually distinct candid snapshots)

For each card, `generate_full_card_images_async()` creates:

1. **Front image** (always) — uses `FRONT_PAGE_PROMPT` via `images.generate`
2. **Back image** (if `page_count >= 2`) — uses `BACK_BLURB_PROMPT`, `BACK_PHOTO_SINGLE_PROMPT`, or
   `BACK_PHOTO_COLLAGE_PROMPT` depending on `back_page_type` and `back_photo_mode`

Each image call uses `generate_image_openai_async()`:

- Waits for rate limit gate → acquires semaphore → calls OpenAI → saves PNG
- On `RateLimitError`: pauses the shared gate, sleeps, retries
- On other errors: exponential backoff, retries (up to 5 attempts)
- Image size: 1024x1536 (portrait, matching 5:7 aspect ratio)

**Reference image for photo back pages:** When generating a "photo" type back page, the front image is passed as a
`reference_image` to `generate_image_openai_async()`. This uses OpenAI's `images.edit` endpoint (instead of
`images.generate`) with `input_fidelity="high"` to preserve faces and visual details from the front image. The two photo
prompt variants give the model different constraints:

- **Single mode** (40%): Same people, same clothes, same setting — but a distinctly different composition (new pose,
  different grouping, candid moment, tighter/wider crop). The card should feel cohesive as a set without duplicating the
  front.
- **Collage mode** (60%): Same faces and ages, but different clothes, scenes, and moods; individual portraits and
  subsets (especially children) are encouraged. Each photo in the collage must be visually distinct — no two should look
  like variations of the same shot.

`back_photo_mode` ("single" or "collage") is assigned deterministically by Python during
`assign_generated_fields()`. Image quality is always "high".

Images are saved as temporary PNGs in a temp directory. The caller cleans them up after PDF composition.

## PDF Composition

**File:** `pdf_composer.py`

`compose_pdf_from_images()` assembles final PDFs using PyMuPDF (fitz):

- **Page size:** 5x7 inches (360x504 points) — standard greeting card dimensions
- **Compression:** JPEG Q75 by default (~12x smaller than lossless PNG, no visible degradation)
- **Lossless mode:** `--no-image-compression` passes `jpeg_quality=-1`, embedding raw PNG with deflate
- **Optimization:** `garbage=3` removes duplicate objects in the PDF stream
- Each image is inserted full-bleed (fills the entire page)

## CLI & Output

**Entry point:** `python -m scripts.generate_sample_cards` → `__main__.py` → `cli.main()` → `asyncio.run(async_main())`

**Output directory:** Auto-generated timestamped directory via `script_output_dir("generate_sample_cards")` (e.g.,
`_build/script_output/20260225T1425-generate_sample_cards/`).

**Rich live table** (`display.py`): Updates at 10 Hz while images generate. Columns: #, Family, Holiday, Style, Back (
none/blurb/single/collage), Status. Column widths for Family, Holiday, and Style are computed dynamically from the
longest value in each column. Active tasks show spinners. Summary line counts done/active/rate-limited/error.

**Completion summary:** Prints card count, style distribution, holiday distribution, and multipage percentage. Opens
the output folder in Finder unless `--no-open`.

## Gotchas

- **Rate limit coordination.** Separate `RateLimitGate` instances for Claude (spec generation) and OpenAI (image
  generation). Each phase creates its own gate since they hit different API providers with different rate limits.

- **JSON extraction from Claude.** Claude sometimes wraps JSON in Markdown code fences (` ```json ... ``` `) or includes
  leading/trailing prose. The `extract_json()` helper in `utils.py` strips fences, finds the first `[` or `{`, and
  parses from there. Any extra text Claude included is logged at INFO level for diagnostics.

- **Family name padding.** If Claude returns fewer unique names than requested (e.g., due to duplicates), the pipeline
  pads with `Family1`, `Family2`, etc.

- **Subtitle fallbacks.** If a subtitle batch returns fewer results than expected, missing entries get
  `"The {family_name} Family"` as a fallback.

- **Color scheme fallbacks.** If a batch returns fewer color schemes than pairs submitted, missing entries get a neutral
  grayscale fallback rather than failing the whole batch.

- **Phase 2 failures are non-fatal.** If a card's content generation fails after retries, that card is simply excluded
  from the final output. The pipeline continues with remaining cards.

- **Temp image cleanup.** Images are generated into a temp directory and cleaned up after PDF composition. If the
  process crashes mid-generation, temp files may persist.

- **Back page type affects prompt.** The card content prompt varies based on `back_page_type`: "blurb" asks for
  `backstory_blurb`, "photo" asks for `back_greeting` and `back_image_prompt`. The image generator uses corresponding
  prompt templates.

- **OpenAI safety filter.** Family photo prompts (describing people's poses, physical closeness, clothing) can trigger
  OpenAI's moderation. All image prompts include "fully clothed and family-friendly" to reduce false positives.
  Moderation blocks are logged as warnings and retried.
