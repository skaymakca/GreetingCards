# Config & Preferences

User configuration: API key, AI model selection, and how persistence differs between dev and bundled modes.

**Key files:** `app/core/config.py`, `app/core/paths.py`, `app/gui/settings_dialog.py`

## Storage Overview

The app uses two persistence mechanisms for different purposes:

| What | Storage | Why |
|---|---|---|
| API key, AI model choice | `preferences.plist` (binary plist) | User preferences — small, simple key-value pairs |
| OCR results, AI results, manual edits | `GreetingCards.sqlite` (SQLite) | Cached/derived data — structured, queryable, rebuildable |

Both files live in the same data directory (see below). The plist is read/written via `plistlib`; the database via SQLAlchemy.

## Data Directory by Mode

Determined by `get_data_dir()` in `app/core/paths.py`:

| Mode | Detection | Data Directory |
|---|---|---|
| Dev (`python main.py`) | `sys._MEIPASS` not set | `project_root/.local/` (auto-created) |
| Bundled (`.app`) | `sys._MEIPASS` exists | `~/Library/Application Support/GreetingCards/` |

Both directories are auto-created on first access.

## API Key Resolution

`get_api_key()` checks two sources (both modes use the same logic):

1. **`ANTHROPIC_API_KEY` environment variable** — checked first
2. **`preferences.plist`** — read from data dir

Env var takes precedence when both are set. If both sources have different non-empty keys, a warning is logged once per process (module-level `_mismatch_warned` flag prevents repeat warnings).

`save_api_key()` writes to both the plist and `os.environ` so the key is available immediately in the current process.

The placeholder value `"your-api-key-here"` is treated as unset.

## AI Model Selection

`get_ai_model()` / `save_ai_model()` manage the chosen Claude model.

### Available Models

Defined in `AI_MODELS` tuple of `ModelInfo` dataclasses:

| Model ID | Label | Default? |
|---|---|---|
| `claude-haiku-4-5-20251001` | Claude Haiku 4.5 | |
| `claude-sonnet-4-6` | Claude Sonnet 4.6 | Yes |
| `claude-opus-4-6` | Claude Opus 4.6 | |

### Stale Model Migration

`get_ai_model()` validates the stored model ID against the current `AI_MODELS` registry. If the stored value is missing or not in the registry (e.g., an older model ID from a previous version):

1. The default model (`claude-sonnet-4-6`) is written back to the plist
2. The default is returned

This auto-corrects on first read (typically at app startup when the Settings dialog or AI analyzer reads the preference), so no explicit migration step is needed.

### Usage in AI Analyzer

`analyze_card_with_ai_async()` in `ai_analyzer.py` calls `get_ai_model()` to get the model ID for each API request. The model is read fresh each time, so changing it in Settings takes effect immediately for the next analysis.

## Settings Dialog

`GeneralPreferencesPage` in `settings_dialog.py` exposes both preferences:

- **API Key** — text field + Save button; status label hidden until save action
- **AI Model** — `wx.Choice` dropdown; saves immediately on selection change (no Save button needed)

The dropdown labels are built from the `AI_MODELS` registry: `"{label} — {description}"`.

## Plist vs Database: Design Rationale

- **Plist** is for user preferences that are small, opaque, and must survive data resets. The "Reset All Card Data" button in Advanced settings clears the SQLite DB (manual entries, candidates, cached OCR/AI) but never touches the plist.
- **SQLite** is for cached/derived data that can be recomputed from source files. It's keyed by content hash, supports structured queries, and is safe to drop and recreate.
