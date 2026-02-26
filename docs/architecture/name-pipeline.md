# Name Pipeline

OCR extraction through AI analysis, cleaning, formatting, database storage, and rename.

**Key files:** `app/core/family_name/` (cleaning, formatting, data lookup), `app/core/name_extractor.py`, `app/core/ai_analyzer.py`, `app/core/name_formatting.py` (filename sanitization only), `app/core/database.py`, `app/core/renamer.py`

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
        target_filename(year) → "Holiday Cards {year} - {Name} Family.pdf"
        build_rename_plan() → per-directory dedup
        execute_rename_plan() → actual file renames
```

## OCR Extraction (`name_extractor.py`)

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

## Family Name Package (`app/core/family_name/`)

Consolidated package for all family name cleaning, formatting, and data lookup. Three submodules:

### Data Layer (`data.py`)

Two container classes with `__contains__` support for `in` checks:

**`PreservedFamilyNames`** — Census-sourced surnames ending in 's' that should not be de-pluralized (e.g., "Morales", "Williams", "Jones"). Loaded from `content/data/preserved_family_names.txt` (12,762 names).

- `normalize(name)` — static method: lowercase + strip all non-alpha chars. Used for both loading and lookup so "O'Brien", "OBRIEN", "o brien" all match the same key.
- `__contains__` — normalized lookup: `"Morales" in preserved_family_names` → `True`
- `load()` — classmethod: reads text file via `get_runtime_content_path()`, returns empty set if file missing.

**`FilteredNames`** — Blocklist of generic words that should never be a family name: card services ("snapfish", "shutterfly", "minted"), generic words ("family", "holiday", "greeting"), and holiday names ("christmas", "new year", "season's greetings"). Uses the same `normalize()` for case/punctuation-insensitive matching.

Module-level singletons are created at first import:
```python
preserved_family_names: PreservedFamilyNames = PreservedFamilyNames.load()
filtered_names: FilteredNames = FilteredNames()
```

### Cleaning (`cleaning.py`)

**`strip_plural_family_name(name)`** — Smart de-pluralization:
1. Check `preserved_family_names` — if present, return unchanged (Census names like "Morales")
2. Short names (≤2 chars) or names ending in "ss" — return unchanged
3. Sibilant endings (shes, ches, xes, zes) — strip "es"
4. Consonant-pair endings (ths, wns, rts) — strip "s"
5. Otherwise — return unchanged

**`clean_family_name(name)`** — Remove noise:
- Strip "The ", " Family", quotes, "From: ", "Sent by: ", colon prefixes
- Apply `strip_plural_family_name()`

**`strip_family_name_punctuation(name)`** — Clean OCR artifacts: strip leading/trailing punctuation, collapse whitespace, remove quotes.

**`clean_and_filter_family_names(names)`** — Full pipeline:
1. `clean_family_name()` on each name
2. `sanitize_for_filename()` to replace filesystem-invalid chars
3. Filter against `filtered_names` blocklist
4. Drop empty results

### Formatting (`formatting.py`)

**`smart_title_case_family_name(name)`** — Proper capitalization with special rules:

| Rule           | Example                                                |
|----------------|--------------------------------------------------------|
| Mc/Mac prefix  | mcdonald → McDonald, macdonald → MacDonald             |
| Mac exceptions | macintosh → Macintosh (not MacIntosh)                  |
| Particles      | van, von, de, del, der → lowercase (unless first word) |
| Suffixes       | jr → Jr., sr → Sr., ii/iii/iv → II/III/IV              |
| Hyphens        | smith-jones → Smith-Jones                              |
| Apostrophes    | o'brien → O'Brien                                      |

Hierarchical formatting: split by spaces → check particles → split by apostrophes → split by hyphens → apply rules.

### Package `__init__.py`

Re-exports all public API so callers import from `app.core.family_name`:
```python
from app.core.family_name import clean_and_filter_family_names
from app.core.family_name import smart_title_case_family_name
from app.core.family_name import preserved_family_names
```

## Filename Sanitization (`name_formatting.py`)

After the family name package consolidation, `name_formatting.py` contains only:

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
from app.core.family_name import clean_and_filter_family_names, smart_title_case_family_name
cleaned = clean_and_filter_family_names([family_name])
clean_name = smart_title_case_family_name(cleaned[0])
```

### Raw Data Separation
Raw OCR text and AI responses are stored separately from cleaned candidates. This enables:
1. Re-processing when cleaning logic improves (upgrade path)
2. Debugging AI responses
3. Comparing raw vs cleaned results

## Rename (`renamer.py`)

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
`execute_rename_plan()` performs actual renames and updates each card's `file_paths` and `primary_path` in-place for consistency. Each `RenameResult` carries a `card` back-reference (from the plan item) so the caller can trace results back to their source cards.

### Post-Rename Cleanup
`MainWindow._remove_completed_results()` selectively removes resolved paths (renamed or already correct) from cards. Cards with no remaining paths are deleted. Failed or unresolved paths (no name, errors) are kept for the user to address.

## Gotchas

- **Raw vs cleaned:** Never apply cleaning at extraction time. Raw data goes to DB; cleaning happens in `clean_and_filter_family_names` during `reprocess_candidates_from_raw`.
- **smart_title_case_family_name order matters:** Particles must be checked before Mc/Mac rules. Suffixes must be checked before standard capitalization.
- **Single plural-stripping path:** `strip_plural_family_name()` is the single entry point for de-pluralization, called inside `clean_family_name()`. No duplicate stripping paths.
- **Candidate uniqueness:** `(file_hash, family_name, method)` is a unique constraint. Adding a duplicate returns the existing candidate's ID.
- **Normalized lookup:** `PreservedFamilyNames` and `FilteredNames` both use `normalize()` (lowercase + strip non-alpha) for lookups. This means "O'Brien" matches "OBRIEN" matches "obrien" — intentional for robust matching.
- **Mock patch paths:** Because `database.py` does `from app.core.family_name import ...`, mocks must target `app.core.family_name.clean_and_filter_family_names` (package level), not the submodule path.
