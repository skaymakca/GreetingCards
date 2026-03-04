# Config & Preferences

User configuration: API key, AI model selection, and how persistence differs between dev and bundled modes.

**Key files:** `app/core/config.py`, `app/core/paths.py`, `app/core/services/config_service.py`, `app/gui/dialogs/settings.py`

## Storage Overview

The app uses two persistence mechanisms for different purposes:

| What                                  | Storage                            | Why                                                      |
|---------------------------------------|------------------------------------|----------------------------------------------------------|
| API key, AI model, auto-update prompt | `preferences.plist` (XML plist)    | User preferences — small, simple key-value pairs         |
| OCR results, AI results, manual edits | `GreetingCards.sqlite` (SQLite)    | Cached/derived data — structured, queryable, rebuildable |

Both files live in the same data directory (see below). The plist is read/written via `plistlib`; the database via SQLAlchemy.

## Path Resolution by Mode

All paths are determined by `is_bundled()` in `app/core/paths.py` (checks for `sys._MEIPASS` set by PyInstaller).

| Mode                      | Data dir (prefs + DB)                            | Runtime content (tessdata, HTML, family name DB) |
|---------------------------|--------------------------------------------------|--------------------------------------------------|
| Source (`python main.py`) | `project_root/.local/GreetingCards/`             | `project_root/_build/runtime_content/`           |
| Bundle (`.app`)           | `~/Library/Application Support/GreetingCards/`   | `sys._MEIPASS/_runtime_content/`                 |

Both data directories are auto-created on first access. The modes use separate data directories so that development builds cannot corrupt production data (schema migrations, test resets, etc.).

## API Key Resolution

`get_api_key()` resolution differs by mode:

- **Bundle mode** (`.app`): reads from `preferences.plist` only. Environment variables are ignored.
- **Source mode** (`python main.py`): checks `ANTHROPIC_API_KEY` env var first, falls back to `preferences.plist`. If both sources have different non-empty keys, a warning is logged once per process.

`save_api_key()` writes to both the plist and `os.environ` so the key is available immediately in the current process.

The placeholder value `"your-api-key-here"` is treated as unset.

## AI Model Selection

`get_ai_model()` / `save_ai_model()` manage the chosen Claude model.

### Available Models

Defined in `AI_MODELS` tuple of `ModelInfo` dataclasses:

| Model ID            | Label             | Default? |
|---------------------|-------------------|----------|
| `claude-haiku-4-5`  | Claude Haiku 4.5  |          |
| `claude-sonnet-4-6` | Claude Sonnet 4.6 | Yes      |
| `claude-opus-4-6`   | Claude Opus 4.6   |          |

### Stale Model Migration

`get_ai_model()` validates the stored model ID against the current `AI_MODELS` registry. If the stored value is missing or not in the registry (e.g., an older model ID from a previous version):

1. The default model (`claude-sonnet-4-6`) is written back to the plist
2. The default is returned

This autocorrects on first read (typically at app startup when the Settings dialog or AI analyzer reads the preference), so no explicit migration step is needed.

### Usage in AI Analyzer

`analyze_card_with_ai_async()` in `ai_analyzer.py` calls `get_ai_model()` to get the model ID for each API request. The model is read fresh each time, so changing it in Settings takes effect immediately for the next analysis.

## First-Launch Auto-Update Opt-In

`has_prompted_auto_update()` / `set_prompted_auto_update()` manage a boolean flag (`AUTO_UPDATE_PROMPTED`) in `preferences.plist`.

On first launch (bundled mode only), `main.py` checks this flag before starting Sparkle. If the user hasn't been prompted yet, a `wx.MessageBox` asks whether to enable automatic update checks. The choice is written to Sparkle's `NSUserDefaults` via `set_auto_check_enabled()`, and the flag is set so the dialog never appears again.

Existing users who upgrade to a version with this feature will see the dialog once — a polite one-time ask consistent with standard macOS app behavior.

## Settings Dialog

`GeneralPreferencesPage` in `settings.py` exposes both preferences:

- **API Key** — text field + Save button; status label hidden until save action
- **AI Model** — `wx.Choice` dropdown; saves immediately on selection change (no Save button needed)

The dropdown labels are built from the `AI_MODELS` registry: `"{label} — {description}"`.

## Plist vs Database: Design Rationale

- **Plist** is for user preferences that are small, opaque, and must survive data resets. The "Reset All Card Data" button in Advanced settings clears the SQLite DB (manual entries, candidates, cached OCR/AI) but never touches the plist.
- **SQLite** is for cached/derived data that can be recomputed from source files. It's keyed by content hash, supports structured queries, and is safe to drop and recreate.
