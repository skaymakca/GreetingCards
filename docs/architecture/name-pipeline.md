# Name Pipeline

OCR extraction through AI analysis, cleaning, formatting, database storage, and rename.

**Key files:** `app/core/name_extractor.py`, `app/core/ai_analyzer.py`, `app/core/name_formatting.py`, `app/core/database.py`, `app/core/renamer.py`

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
    │       clean_family_name() → strip quotes, prefixes, greeting words
    │       deparameterize_name() → remove plural 's'
    │       sanitize_for_filename() → replace invalid chars
    │       smart_title_case() → proper capitalization
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

Results are deduplicated by name (case-insensitive) preserving order. Greeting words (merry, christmas, happy, etc.) are filtered out.

## AI Analysis (`ai_analyzer.py`)

Single async function used for all AI analysis (single card, selected, or batch):
- `analyze_card_with_ai_async()` — async `anthropic.AsyncAnthropic` client

### Prompt Structure
Sends all page images as base64 PNG content blocks, followed by a text prompt requesting just family last names, one per line. Model: `claude-sonnet-4-5-20250929`, max 256 tokens.

### Response Parsing (`_parse_response`)
- `"UNKNOWN"` → empty AIResult
- Lines > 50 chars or containing skip words (shows, appears, page, etc.) → filtered
- First valid line → `best_name`, remaining → `alternates`

## Name Cleaning

Cleaning is applied **only when loading from DB** (in `database._clean_and_filter_names`), not at extraction time. This lets raw data be re-processed with improved logic.

### Cleaning Chain
```
clean_family_name()        # Remove "The ", " Family", quotes, "From: ", "Sent by: "
    → deparameterize_name() # "Smiths" → "Smith" (smart plural removal)
    → sanitize_for_filename() # Replace \/:*?"<>| with "-"
    → Filter against blocklist # "unknown", "snapfish", "shutterfly"
    → smart_title_case()    # Final formatting
```

### smart_title_case (`name_formatting.py`)

Hierarchical formatting: split by spaces → check particles → split by apostrophes → split by hyphens → apply rules.

| Rule | Example |
|------|---------|
| Mc/Mac prefix | mcdonald → McDonald, macdonald → MacDonald |
| Mac exceptions | macintosh → Macintosh (not MacIntosh) |
| Particles | van, von, de, del, der → lowercase (unless first word) |
| Suffixes | jr → Jr., sr → Sr., ii/iii/iv → II/III/IV |
| Hyphens | smith-jones → Smith-Jones |
| Apostrophes | o'brien → O'Brien |

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
- **`reprocess_candidates_from_raw()`:** Clears all candidates, re-parses raw OCR+AI data with current cleaning logic, auto-selects best. Preserves manual entries.
- **`get_card_state()`:** Resolves display name from either `selected_family_name` (manual) or `selected_candidate_id` (candidate lookup). Returns `CardState`.
- **Candidate sort order:** AI results first, then OCR. Within each method: high > medium > low.

### Raw Data Separation
Raw OCR text and AI responses are stored separately from cleaned candidates. This enables:
1. Re-processing when cleaning logic improves (upgrade path)
2. Debugging AI responses
3. Comparing raw vs cleaned results

## Rename (`renamer.py`)

### Plan Building
`build_rename_plan()` generates a list of `RenamePlanItem` with status:

| Status | Meaning |
|--------|---------|
| `ok` | Normal rename |
| `duplicate` | Same target name exists → numbered: `Name (2).pdf` |
| `skip_same` | Already has correct name |
| `skip_no_name` | No family name extracted |
| `skip_error` | Card had processing error |

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

- **Raw vs cleaned:** Never apply cleaning at extraction time. Raw data goes to DB; cleaning happens in `_clean_and_filter_names` during `reprocess_candidates_from_raw`.
- **smart_title_case order matters:** Particles must be checked before Mc/Mac rules. Suffixes must be checked before standard capitalization.
- **`_strip_plural` in ai_analyzer.py:** A second plural-stripping function exists in `clean_family_name()` (conservative), separate from `deparameterize_name()` in `name_formatting.py`. Both are applied during the cleaning chain.
- **Candidate uniqueness:** `(file_hash, family_name, method)` is a unique constraint. Adding a duplicate returns the existing candidate's ID.
