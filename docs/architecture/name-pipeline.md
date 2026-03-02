# Name Pipeline

OCR extraction through AI analysis, cleaning, formatting, database storage, and rename.

**Key files:** `app/core/naming/family_name/` (cleaning, formatting, data lookup), `app/core/naming/extractor.py`, `app/core/pipeline/ai_analyzer.py`, `app/core/naming/filename_safety.py` (filename sanitization only), `app/core/database.py`, `app/core/naming/renamer.py`, `app/core/naming/rename_filter.py` (post-rename filtering), `app/gui/rename_display.py` (rename presentation helpers)

## Pipeline Overview

```
PDF file
    │
    ├─ render_all_pages() → PIL images (200 DPI)
    │
    ├─ OCR path:
    │   extract_text_all_pages() → raw text
    │   └─ extract_family_names() → list[NameMatch(name, confidence)]
    │       Regex patterns: HIGH → MEDIUM → LOW
    │
    ├─ AI path:
    │   analyze_card_with_ai_async() → AIResult(best_name, alternates)
    │       Claude Sonnet with page images + extraction prompt
    │
    ├─ Raw storage (DB):
    │   save_raw_ocr(hash, text)    → raw_ocr_results table
    │   save_raw_ai(hash, name, alts) → raw_ai_results table (JSON)
    │
    ├─ Candidate processing:
    │   reprocess_candidates_from_raw(hash)
    │   └─ For each raw result:
    │       clean_and_filter_family_names()  → clean + filter pipeline
    │       sanitize_for_filename()          → replace invalid chars
    │       smart_title_case_family_name()   → proper capitalization
    │       → INSERT INTO candidates (deduplicated by name+method)
    │   └─ Auto-select best candidate (AI high > OCR high)
    │
    └─ Rename:
        build_target_filename(card, year) → "Holiday Cards {year} - {Name} Family.pdf"
        build_rename_plan() → per-directory dedup
        execute_rename_plan() → actual file renames
```

## OCR Extraction (`naming/extractor.py`)

Regex-based pattern matching at three confidence levels:

### HIGH Confidence
- `"The Smith Family"` → `Smith`
- `"The Smiths"` (plural at end) → `Smith`
- `"From the Johnsons"` / `"From the Smith Family"` → `Smith`
- `"Love, The Smiths"` → `Smith`

### MEDIUM Confidence
- `"With love, John & Jane Smith"` → `Smith`
- `"-- The Smiths"` (dashed prefix) → `Smith`
- `"Smith's"` (possessive) → `Smith`
- `"John & Jane Smith"` (no prefix) → `Smith`

### LOW Confidence
- `"Love, First Last"` → `Last`
- Last line with capitalized non-greeting words → last capitalized word

Results are deduplicated by name (case-insensitive) preserving order. Greeting words (Merry, Christmas, Happy, etc.) are filtered out.

## AI Analysis (`ai_analyzer.py`)

Single async function used for all AI analysis (single card, selected, or batch):
- `analyze_card_with_ai_async()` — async `anthropic.AsyncAnthropic` client

### Prompt Structure
Sends all page images as base64 PNG content blocks, followed by a text prompt requesting just family last names, one per line. Model: configurable (default `claude-sonnet-4-6`), max 256 tokens.

### Response Parsing (`_parse_response`)
- `"UNKNOWN"` → empty AIResult
- Lines > 50 chars or containing skip words (shows, appears, page, etc.) → filtered
- First valid line → `best_name`, remaining → `alternates`

## Family Name Package (`app/core/naming/family_name/`)

Consolidated package for all family name cleaning, formatting, and data lookup. Three submodules:

### Data Layer (`data.py`)

**`FamilyNameDatabase`** — Master database of 213K+ family names merged from US Census 2010 (162K names with rank/count), Faker locale providers (5K names with proper display forms like O'Brien, MacDonald), and smashew/NameDatabases (134K international names). Loaded from `content/data/family_name_database.tsv.gz` (gzip-compressed TSV, ~1.7 MB, loads in ~55ms).

Each entry is a `FamilyNameEntry(display_form, rank, count, alternates)` dataclass. Census rank/count are 0 for non-Census names. Alternates are accepted variant display forms (e.g., "Van-Dyke" as alternate of "Van Dyke").

- `normalize(name)` — static method: NFKD Unicode decomposition + special char map (ß→ss, ø→o, æ→ae) + lowercase + strip non-alpha. So "O'Brien", "OBRIEN", "Müller", "MULLER" all match the same key.
- `__contains__` — normalized membership test: `"Morales" in family_name_db` → `True`
- `display(name)` — canonical display form: `family_name_db.display("OBRIEN")` → `"O'Brien"`
- `rank(name)` / `count(name)` — Census frequency data (0 if not in Census)
- `alternates(name)` — accepted variant display forms as a tuple
- `match_display(raw)` — match against any known display form (primary or alternate). Returns the matched form as-is, or None. Uses case-insensitive but punctuation-preserving matching.
- `related_forms(raw)` — all other forms (primary + alternates) excluding the matched one. Used to generate additional candidates.
- `load()` — classmethod: reads gzip TSV via `get_runtime_content_path()`, returns empty DB if file missing.

**Data files:**
- `content/data/family_name_database.tsv` — committed source TSV (5 columns: normalized, display, rank, count, alternates)
- `content/data/family_name_overrides.tsv` — manual curations that trump auto-generated forms
- `_build/runtime_content/data/family_name_database.tsv.gz` — gzip-compressed, generated by `make content`

**Build script:** `uv run python -m scripts.build_family_name_db` merges Census + Faker + smashew, applies overrides, writes TSV. Non-winning display forms from source conflicts become alternates.

**`FilteredNames`** — Blocklist of generic words that should never be a family name: card services ("snapfish", "shutterfly", "minted"), generic words ("family", "holiday", "greeting"), and holiday names ("Christmas", "new year", "season's greetings"). Uses the same `normalize()` for case/punctuation-insensitive matching.

Module-level singletons are created at first import:
```python
family_name_db: FamilyNameDatabase = FamilyNameDatabase.load()
filtered_names: FilteredNames = FilteredNames()
```

### Cleaning (`cleaning.py`)

**`strip_plural_family_name(name)`** — Smart de-pluralization:
1. Check `family_name_db` — if present, return unchanged (all 213K+ names protected)
2. Short names (≤2 chars) or names ending in "ss" — return unchanged
3. Sibilant endings (shes, ches, xes, zes) — strip "es"
4. Consonant-pair endings (ths, wns, rts) — strip "s"
5. Otherwise, return unchanged

**`clean_family_name(name)`** — Remove noise:
- Strip "The ", " Family", quotes, "From: ", "Sent by: ", colon prefixes
- Apply `strip_plural_family_name()`

**`strip_family_name_punctuation(name)`** — Clean OCR artifacts: strip leading/trailing punctuation, collapse whitespace, remove quotes.

**`clean_and_filter_family_names(names)`** — Full pipeline with display form bypass:
1. Check `family_name_db.match_display()` — if the raw name matches a known display form (primary or alternate), use it as-is and add all related forms as additional candidates. This bypasses cleaning for recognized names.
2. For unrecognized names: `clean_family_name()` on each name
3. `sanitize_for_filename()` to replace filesystem-invalid chars
4. Filter against `filtered_names` blocklist
5. Drop empty results

The display form bypass applies to both OCR and AI candidates since both flow through this function.

### Formatting (`formatting.py`)

**`smart_title_case_family_name(name)`** — Proper capitalization with DB-first lookup:

For single-token inputs without apostrophes or hyphens, the database display form is used first (e.g., `OBRIEN` → `O'Brien` from Faker). If no DB match, falls back to heuristic rules:

| Rule           | Example                                                |
|----------------|--------------------------------------------------------|
| DB display     | OBRIEN → O'Brien, MCDONALD → McDonald                  |
| Mc/Mac prefix  | mcdonald → McDonald, macdonald → MacDonald             |
| Mac exceptions | macintosh → Macintosh (not MacIntosh)                  |
| Particles      | van, von, de, del, der → lowercase (unless first word) |
| Suffixes       | jr → Jr., sr → Sr., ii/iii/iv → II/III/IV              |
| Hyphens        | smith-jones → Smith-Jones                              |
| Apostrophes    | o'brien → O'Brien                                      |

DB lookup is skipped for multi-word and structured inputs (spaces, hyphens, apostrophes) since these already carry word boundary info the heuristic handles well. Hierarchical formatting: split by spaces → check particles → split by apostrophes → split by hyphens → apply rules.

### Package `__init__.py`

Re-exports all public API so callers import from `app.core.naming.family_name`:
```python
from app.core.naming.family_name import clean_and_filter_family_names
from app.core.naming.family_name import smart_title_case_family_name
from app.core.naming.family_name import family_name_db, filtered_names
from app.core.naming.family_name import FamilyNameDatabase, FamilyNameEntry
```

## Filename Sanitization (`naming/filename_safety.py`)

`naming/filename_safety.py` contains only:

- **`sanitize_for_filename(name)`** — Replace `\/:*?"<>|` with `-`
- **`INVALID_FILENAME_CHARS`** — frozenset of invalid chars
- **`_INVALID_FS_CHARS`** — compiled regex for the same chars

## Database Storage (`database.py`)

### Schema
```
cards (file_hash PK)
├── selected_family_name    # Manual entry only (NULL if candidate selected)
├── selected_candidate_id   # FK to candidates (NULL if manual)
└── remove_family           # Omit "Family" from filename

candidates (id PK, file_hash FK)
├── family_name             # Cleaned name
├── method                  # 'ocr' | 'ai'
└── confidence              # 'high' | 'medium' | 'low'

raw_ocr_results (file_hash FK, unique)
└── ocr_text                # Full raw OCR text

raw_ai_results (file_hash FK, unique)
└── raw_response            # JSON: {"best_name": "...", "alternates": [...]}
```

### Key Operations
- **`reprocess_candidates_from_raw()`:** Clears all candidates, reparses raw OCR+AI data with current cleaning logic, auto-selects best. Preserves manual entries.
- **`get_card_state()`:** Resolves display name from either `selected_family_name` (manual) or `selected_candidate_id` (candidate lookup). Returns `CardState`.
- **Candidate sort order:** AI results first, then OCR. Within each method: high > medium > low.

### Candidate Processing

When candidates are added (via `_add_candidate_inline` or `add_candidate`), the cleaning pipeline is called with lazy imports:
```python
from app.core.naming.family_name import clean_and_filter_family_names, smart_title_case_family_name
cleaned = clean_and_filter_family_names([family_name])
clean_name = smart_title_case_family_name(cleaned[0])
```

### Raw Data Separation
Raw OCR text and AI responses are stored separately from cleaned candidates. This enables:
1. Re-processing when cleaning logic improves (upgrade path)
2. Debugging AI responses
3. Comparing raw vs cleaned results

## Rename (`naming/renamer.py`)

### Plan Building
`build_rename_plan()` generates a list of `RenamePlanItem` with status:

| Status         | Meaning                                            |
|----------------|----------------------------------------------------|
| `ok`           | Normal rename                                      |
| `duplicate`    | Same target name exists → numbered: `Name (2).pdf` |
| `skip_same`    | Already has correct name                           |
| `skip_no_name` | No family name extracted                           |
| `skip_error`   | Card had processing error                          |

### Per-Directory Dedup
Duplicate tracking uses `dir_files: dict[Path, set[str]]` — seeded from actual directory contents on first encounter. Each directory is independent.

### "See Through Own Name"
When a card's target name collides, its **own** current filename is temporarily removed from the existing set. If the card already sits at a correctly-numbered slot (e.g., `Smith (2).pdf`), it resolves as `skip_same` instead of getting renumbered.

```python
own_name = file_path.name.lower()
existing.discard(own_name)
new_path = _find_available_name(directory, ...)
if new_path == file_path:
    # Already at correct slot → skip_same
```

### Execution
`execute_rename_plan()` performs actual renames and updates each card's `file_paths` and `primary_path` in-place for consistency. Each `RenameResult` carries a `card` back-reference (from the plan item) and a `RenameOutcome` enum so the caller can trace results back to their source cards.

### RenameOutcome Enum

Each `RenameResult` has an `outcome` field (`app/models/card.RenameOutcome`) for machine-readable status:

| Outcome              | Meaning                            |
|----------------------|------------------------------------|
| `RENAMED`            | File was successfully renamed      |
| `ALREADY_CORRECT`    | File already has the correct name  |
| `SKIP_NO_NAME`       | No family name extracted           |
| `SKIP_ERROR`         | Card had processing error          |
| `ERROR_TARGET_EXISTS`| Target name already exists         |
| `ERROR_OS`           | OS-level rename failure            |

`RESOLVED_OUTCOMES` (`app/core/naming/rename_filter.py`) is a `frozenset({RENAMED, ALREADY_CORRECT})` — the outcomes that count as "done." Used by `RenameService.execute()` for path-mapping updates and by `MainWindow._remove_completed_results()` for post-rename cleanup.

### Post-Rename Cleanup
`MainWindow._remove_completed_results()` selectively removes resolved paths (those with outcomes in `RESOLVED_OUTCOMES`) from cards. Cards with no remaining paths are deleted. Failed or unresolved paths (no name, errors) are kept for the user to address.

### Rename Presentation (`app/gui/rename_display.py`)
Presentation helpers for the rename confirmation and completion dialogs live in `app/gui/rename_display.py` (GUI layer, not core). Functions: `summarize_plan()`, `format_plan_summary()`, `summarize_results()`, `format_results_summary()`, `get_plan_item_display()`, `is_skip_status()`, `filter_visible_results()`.

## Gotchas

- **Raw vs cleaned:** Never apply cleaning at extraction time. Raw data goes to DB; cleaning happens in `clean_and_filter_family_names` during `reprocess_candidates_from_raw`.
- **smart_title_case_family_name order matters:** Particles must be checked before Mc/Mac rules. Suffixes must be checked before standard capitalization.
- **Single plural-stripping path:** `strip_plural_family_name()` is the single entry point for de-pluralization, called inside `clean_family_name()`. No duplicate stripping paths.
- **Candidate uniqueness:** `(file_hash, family_name, method)` is a unique constraint. Adding a duplicate returns the existing candidate's ID.
- **Normalized lookup:** `FamilyNameDatabase` and `FilteredNames` both use `normalize()` (NFKD + special char map + lowercase + strip non-alpha) for lookups. This means "O'Brien" matches "OBRIEN", "Müller" matches "Muller", and "Núñez" matches "Nunez" — intentional for robust matching. Special chars that NFKD doesn't decompose (ß, ø, æ, ð, þ, đ, ł) are handled by a manual map.
- **Unicode alternates:** The build script auto-generates ASCII alternates for Unicode display forms (Müller→Muller, Núñez→Nunez) via `ascii_fold()`. Faker locale cross-references also generate alternates when different locales provide Unicode vs ASCII forms of the same name.
- **DB-first formatting guard:** `smart_title_case_family_name()` only uses the DB display for single-token inputs without hyphens/apostrophes. Structured inputs (e.g., "smith-jones", "o'brien") already carry word boundary info and use heuristics instead.
- **Build script chicken-and-egg:** The build script (`scripts/build_family_name_db/`) uses internal formatting functions (`_format_particle`, `_format_word_with_structure`) directly, not `smart_title_case_family_name()`, to avoid depending on the DB it's building.
- **Mock patch paths:** Because `database.py` does `from app.core.naming.family_name import ...`, mocks must target `app.core.naming.family_name.clean_and_filter_family_names` (package level), not the submodule path.
- **Display form bypass + blocklist:** The `match_display()` bypass in `clean_and_filter_family_names()` still checks the `filtered_names` blocklist. Some real surnames (e.g., "Holiday") overlap with filtered words and must not bypass cleaning.
- **Display index vs normalize:** `match_display()` uses case-insensitive but punctuation-preserving matching (`.lower()`), NOT `normalize()`. This is intentional: "Van-Dyke" and "Van Dyke" must remain distinct matches, but `normalize()` strips both to "vandyke".
- **Multiple candidates from alternates:** When `clean_and_filter_family_names()` matches a known display form, it returns the matched form PLUS all related forms. `_add_candidate_inline()` and `add_candidate()` iterate over all cleaned results, creating a candidate for each. The unique constraint handles dedup.
- **File placement:** Raw `.tsv` is committed in `content/data/`; `.tsv.gz` only exists in `_build/runtime_content/data/` (generated by `make content`). The `.tsv.gz` should never be in `content/data/`.
