# HTML Viewer (Shared WebView Base)

Shared WebView-based viewer used by the Help system, Changelog viewer, and Licenses viewer. Provides toolbar navigation (Home/Prev/Next), cross-page search with JavaScript highlighting, singleton window management, and external link interception.

**Key file:** `app/gui/html_viewer.py`

## Architecture

`HTMLViewerWindow` encapsulates everything needed for a WebView viewer:

- wx.Frame with toolbar, search controls, and WebView
- Text indexing via `_TextExtractor` (HTMLParser subclass)
- Cross-page search with `_build_page_index()` and `_count_occurrences()`
- JavaScript in-page highlighting via `_HIGHLIGHT_JS`
- Prev/Next page and match navigation
- External link interception (http/https URLs open in system browser)

`show_viewer()` is the public entry point. It manages singleton windows via a module-level `_viewer_refs: dict[str, weakref.ref]` keyed by `singleton_key`.

## External Link Handling

`EVT_WEBVIEW_NAVIGATING` is bound to intercept navigation events. When the URL starts with `http://` or `https://`, the event is vetoed and `wx.LaunchDefaultBrowser()` opens it in the system browser. All other URLs (local file:// links) are allowed through normally.

This benefits all three consumers — help pages, changelog, and license pages can safely include external links without trapping the user inside the WebView.

## Consumers

| Consumer  | Key file              | Singleton key | Content                                 |
|-----------|-----------------------|---------------|-----------------------------------------|
| Help      | `help_dialog.py`      | `"help"`      | Generated from markdown                 |
| Changelog | `changelog_dialog.py` | `"changelog"` | Generated from `CHANGELOG.md`           |
| Licenses  | `licenses_dialog.py`  | `"licenses"`  | Generated from `uv.lock` + `.dist-info` |

See per-consumer docs:
- `docs/architecture/help-system.md`
- `docs/architecture/changelog-viewer.md`
- `docs/architecture/licenses-viewer.md`

## Search

Three-layer architecture with debounce and 3-character minimum:

### Input Filtering
- **3-character minimum** (`_MIN_SEARCH_LEN = 3`): queries under 3 chars immediately clear highlights without triggering a search. Prevents expensive DOM work on single-character typing.
- **200ms debounce** (`_DEBOUNCE_MS = 200`): a `wx.Timer` delays the search until typing pauses. Each keystroke restarts the timer.

### Layer 1: Python Text Index
At window creation, `_build_page_index()` reads all HTML files and builds `dict[str, str]` (path → lowercase plain text). `_TextExtractor(HTMLParser)` only captures text inside `<div class="content">`, skipping sidebar, script, and style elements.

### Layer 2: Python Search Logic
Search state managed via closures: `search_pages`, `page_cursor`, `match_cursor`, `pending_mark`, `pending_focus`, `last_query`.

Key functions:
- `_mark_all()` — calls `shlMark(query)` via `RunScript` and updates `last_query`. Only called when the query changes.
- `_focus_match(idx)` — calls `shlFocus(idx)` via `RunScript` to move the current-match cursor. Called on prev/next without re-marking.
- `_navigate_to_page()` — if same page, only re-marks when query changed, then focuses. If different page, sets `pending_mark`/`pending_focus` flags for `on_page_loaded`.

### Layer 3: JavaScript Highlighting

JavaScript highlighting functions are defined in `content/html/common/js/search.js` (copied to `_build/runtime_content/html/common/js/search.js` during generation). All HTML files include a `<script src="...search.js">` tag. No more `_MARK_JS`, `_FOCUS_JS`, `_CLEAR_JS` string literals in Python.

Three named functions separate the expensive DOM walk from the cheap cursor movement:

**`shlMark(query)`** — Full DOM walk + highlight. Only called when the query changes. TreeWalker finds matches, wraps in `<mark class="_shl">` elements in reverse DOM order to preserve offsets. Python calls `webview.RunScript(f"shlMark({json.dumps(query)})")`.

**`shlFocus(idx)`** — Moves the "current match" cursor. Called on prev/next. Toggles `_cur` class on `<mark>` elements + `scrollIntoView()`. No DOM walk — just `querySelectorAll` + class toggle. Python calls `webview.RunScript(f"shlFocus({idx})")`.

**`shlClear()`** — Removes all highlights. Unwraps `<mark>` elements + `normalize()`. Python calls `webview.RunScript("shlClear()")`.

## Page Order Manifest

All three consumers use a consistent `page_order.txt` manifest pattern for toolbar arrow navigation:

1. **Generation time:** Each builder writes `page_order.txt` to the output directory alongside the HTML files
2. **Runtime:** Each dialog calls `get_page_order(base_path)` which reads the manifest
3. **Bundle:** The manifest is bundled inside `_build/runtime_content/html/` alongside the HTML, so it works identically in source and app bundle modes

This avoids re-deriving page order at runtime (which previously caused alphabetical sorting bugs when the HTML filenames didn't match the intended navigation order).

## Singleton Management

`_viewer_refs` is a `dict[str, weakref.ref]` mapping singleton keys to frame weakrefs. `show_viewer()` checks the ref:
- If alive and not being deleted → `Raise()` the existing window
- Otherwise, → create a new `HTMLViewerWindow` and store the ref

## Toolbar Layout

```
┌─────────────────────────────────────────────────────────────────┐
│ [Home] [Prev] [Next]  ←stretch→  "2 of 5" [Search...] [↑] [↓] │
└─────────────────────────────────────────────────────────────────┘
```

## Menu Integration

All three viewers are launched from the Help menu:

```
Help
├── About Greeting Cards
├── ─────────────────
├── Greeting Cards Help  ← help viewer
├── What's New           ← changelog viewer
└── Licenses             ← licenses viewer
```

## Gotchas

- **`_TextExtractor` must track div depth** for nested divs inside `.content`.
- **`ChangeValue()` vs `SetValue()`:** `_clear_search()` uses `ChangeValue("")` to avoid retriggering `EVT_TEXT`.
- **`pending_mark`/`pending_focus` pattern:** JS highlighting requires DOM to be loaded; set flags and wait for `EVT_WEBVIEW_LOADED`.
- **Empty query infinite loop:** `str.find("", start)` never returns `-1`. `_count_occurrences` guards with early return.
- **Reverse-order wrapping in JS (fallback path):** Matches wrapped last-to-first to preserve text node offsets.
- **`last_query` tracks redundant re-marking:** `_navigate_to_page` skips `_mark_all()` when the query hasn't changed (same-page prev/next).
