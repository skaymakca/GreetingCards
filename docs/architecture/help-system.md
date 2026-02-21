# Help System (WebView + Cross-Page Search)

WebView-based help viewer with HTML content pages, Python-side text indexing, and JavaScript in-page highlighting.

**Key file:** `app/gui/help_dialog.py`

## Why WebView

The help system uses `wx.html2.WebView` instead of native wx controls because:

- **Rich formatting** — HTML/CSS provides sidebar navigation, styled headings, and links without custom widget code
- **Separation of content and code** — Help content is authored as plain HTML files with a shared CSS stylesheet, independent of Python code

## Content Structure

```
help/
├── index.html                  ← Home page
├── css/help.css                ← Shared stylesheet
└── pages/
    ├── getting-started.html
    ├── toolbar.html
    ├── card-list.html
    ├── preview.html
    ├── shortcuts.html
    └── tips.html
```

Every page has the same HTML structure:

```html
<div class="sidebar">
    <h2>Contents</h2>
    <ul><!-- nav links, one marked class="active" --></ul>
</div>
<div class="content">
    <!-- page body -->
</div>
```

The CSS sidebar provides persistent navigation across all pages. Each page marks its own link as `class="active"`.

## Page Navigation

`_PAGE_ORDER` defines the sequential ordering of all 8 pages. The toolbar provides:

| Button | Action |
|--------|--------|
| Home | Navigate to `index.html`, clear search |
| Previous | Go to previous page in `_PAGE_ORDER`, clear search |
| Next | Go to next page in `_PAGE_ORDER`, clear search |

Prev/Next are enabled/disabled based on current position. Navigation buttons clear any active search state to avoid stale highlights.

## Search Architecture

Search spans three layers: Python text indexing, Python navigation logic, and JavaScript DOM highlighting.

### Layer 1: Python Text Index

At window creation, `_build_page_index(base_path)` reads all 8 HTML files and builds a `dict[str, str]` mapping relative path → lowercase plain text. Text extraction uses `_TextExtractor(HTMLParser)`, which:

- **Only** captures text inside `<div class="content">`
- Tracks nested div depth to correctly detect when the content div closes
- Skips `<script>` and `<style>` elements
- Ignores sidebar, `<title>`, `<head>`, and all other content outside `.content`

This is critical — earlier approaches that extracted all visible text or excluded only the sidebar caused false matches from TOC/title text that appears on every page.

### Layer 2: Python Search Logic

Search state is managed via closures inside `show_help()`:

```
search_pages: list[_PageMatch]  — pages with matches (NamedTuple: page, count)
page_cursor: int                — index into search_pages
match_cursor: int               — match index within current page
pending_highlight: bool         — highlight after next page load
```

Closures use `nonlocal` to rebind scalar state variables (`page_cursor`, `match_cursor`, `pending_highlight`). `search_pages` is mutated in-place via `.clear()` / `.append()` so doesn't need `nonlocal`.

**Search flow:**

1. User types in `SearchCtrl` → `EVT_TEXT` → `_run_search(query)`
2. `_run_search` scans `page_index` via `_count_occurrences()` to find pages with matches and their counts
3. If the current page has results, stays on it; otherwise navigates to first matching page
4. `_navigate_to_page(pg_idx, mt_idx)` either highlights in-place or loads a new URL and sets `pending_highlight`
5. `EVT_WEBVIEW_LOADED` fires → if `pending_highlight`, runs JavaScript highlighting

**Match navigation (Prev Match / Next Match):**

- Steps through individual matches within a page (`match_cursor`)
- When reaching the end of a page's matches, wraps to the next/previous page with results
- Wraps around from last page to first (and vice versa)

### Layer 3: JavaScript Highlighting

We use custom JavaScript (`_HIGHLIGHT_JS`) instead of the native `webview.Find()` because:

- **`webview.Find()` searches the entire DOM** including the sidebar, causing false highlights on TOC links
- Custom JS targets only `.content` div using `document.createTreeWalker(content, NodeFilter.SHOW_TEXT)`
- Provides full control over highlight colors and current-match focus

The JavaScript template (`_HIGHLIGHT_JS`) takes two parameters: `%s` (JSON-encoded query) and `%d` (0-based index of current match). It:

1. Injects a `<style>` element (once) for highlight CSS
2. Clears all existing `<mark class="_shl">` elements, restoring original text nodes
3. Normalizes the DOM (`content.normalize()`)
4. Walks all text nodes in `.content`, finding case-insensitive matches
5. Wraps each match in `<mark class="_shl">` (light blue: `#CCDEFF`) or `<mark class="_shl _cur">` (current match: `#007AFF` with white text)
6. Scrolls the current match into view with `scrollIntoView({block: 'center'})`
7. Returns the total match count

Matches are wrapped in reverse DOM order to preserve text node offsets.

## Toolbar Layout

```
┌─────────────────────────────────────────────────────────┐
│ [Home] [Prev] [Next]  ←stretch→  "2 of 5" [Search...] [↑] [↓] │
└─────────────────────────────────────────────────────────┘
```

- `AddStretchableSpace()` pushes search controls to the right
- `wx.StaticText` label shows `"X of N"`, `"No results"`, or empty
- `wx.SearchCtrl` dynamically resizes via `EVT_SIZE` handler to fill available space
- Cmd+F accelerator focuses the search control

## Singleton Window

`_help_window_ref` is a module-level `weakref.ref` to the help frame. `show_help()` checks this ref to either raise an existing window or create a new one. When the frame is destroyed, the weakref returns `None` automatically.

## `_count_occurrences(text, query_lower)`

Counts non-overlapping occurrences. Guards against empty query (which would cause an infinite loop with `str.find`).

## Test Coverage

| Area | Coverage | Notes |
|------|----------|-------|
| `_TextExtractor` | Full | 10 tests covering content extraction, sidebar exclusion, script/style skipping, nested divs, multi-class matching, edge cases |
| `_build_page_index` | Full | Tests against real help files + graceful missing-file handling |
| `_count_occurrences` | Full | Including empty query guard, empty text, and real index data |
| Help content files | Full | All pages exist, CSS exists, sidebar present, active link per page |
| Toolbar/SearchCtrl | Structural | Widget existence, tool count/labels, initial enabled states, placeholder text |
| Search closures | Not tested | Interactive logic (JS execution, page navigation) requires live WebView with loaded DOM |

## Gotchas

- **`_TextExtractor` must track div depth:** The content div may contain nested `<div>` elements. A simple flag without depth tracking would exit content mode at the first `</div>`, missing nested content.
- **`_TextExtractor` uses `split()` class matching:** `"content" in classes.split()` to correctly handle multi-class attributes like `class="main content"` without false-matching `class="not-content"`.
- **`ChangeValue()` vs `SetValue()`:** `_clear_search()` uses `ChangeValue("")` to reset the search control without triggering `EVT_TEXT`, which would re-run the search.
- **`pending_highlight` pattern:** JavaScript highlighting requires the DOM to be fully loaded. When navigating to a new page, we set a flag and wait for `EVT_WEBVIEW_LOADED` before running the highlight script.
- **Empty query infinite loop:** `str.find("", start)` always returns `start`, never `-1`. `_count_occurrences` guards against this with an early return.
- **Reverse-order wrapping in JS:** Matches are wrapped from last to first in DOM order so that wrapping earlier matches doesn't shift the offsets of later ones.
