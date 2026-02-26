# Dark Mode Architecture

## Overview

The app supports automatic dark/light mode switching using macOS native appearance detection via KVO (Key-Value Observing) on `NSApplication.effectiveAppearance`. All three layers — native wxPython UI, HTML viewers, and toolbar icons — respond to appearance changes in real time.

## Detection Layer

**File:** `app/gui/appearance.py`

Uses pyobjc to observe the `effectiveAppearance` key path on `NSApplication.sharedApplication()`. When the system appearance changes, the KVO observer fires and dispatches the callback to the wx main thread via `wx.CallAfter`.

Public API:
- `is_dark_mode() -> bool` — checks if `effectiveAppearance` name contains "Dark"
- `start_observer(callback)` — registers KVO observer (called at app startup)
- `stop_observer()` — removes KVO observer (called at app close)

The observer is started in `MainWindow.__init__` and stopped in `MainWindow._on_close`.

## GUI Layer (wxPython)

**File:** `app/gui/styles.py` — `Color` class

Mode-dependent colors are class attributes that get reassigned by `Color.refresh()`:
- `BG_PRIMARY`, `BG_SECONDARY`, `BG_SELECTED`
- `TEXT_PRIMARY`, `TEXT_SECONDARY`
- `BORDER`

Semantic colors (`ACCENT`, `SUCCESS`, `WARNING`, `ERROR`, `MANUAL_BLUE`) are fixed across modes.

`Color.icon_hex()` returns the appropriate SF Symbol tint color for the current mode.

**File:** `app/gui/icons.py`

`load_sf_symbol()` defaults to `Color.icon_hex()` for tinting. `clear_cache()` invalidates the icon cache so icons are re-rendered with the new tint.

### Appearance Change Flow

When macOS appearance changes, `MainWindow._on_appearance_changed` runs:

1. `Color.refresh()` — reassigns mode-dependent color class attributes
2. `icons.clear_cache()` — invalidates cached toolbar/icon bitmaps
3. `_refresh_toolbar_icons()` — re-renders toolbar SF Symbols with new tint
4. Panel `refresh_colors()` — each panel re-applies colors to its widgets:
   - `FilterSidebar.refresh_colors()` — section header labels
   - `PreviewPanel.refresh_colors()` — canvas background
   - `ReviewPanel.refresh_colors()` — detail panel labels
5. Top-level window iteration — calls `refresh_colors()` on any window that supports it (e.g., `HtmlViewer` toolbar separator), then `Refresh()`/`Update()`

### Panels with `refresh_colors()`

Panels that set explicit colors at construction time need a `refresh_colors()` method to re-apply them when the mode changes. Most wx widgets inherit system colors automatically; only widgets with explicitly set foreground/background colors need refresh.

## HTML Layer (CSS)

**File:** `content/html/common/css/viewer.css`

All colors use CSS custom properties defined in `:root`. A `@media (prefers-color-scheme: dark)` block overrides them for dark mode. WebKit in `wx.html2.WebView` respects `prefers-color-scheme` automatically — no Python-side signaling needed.

**File:** `content/html/common/js/search.js`

Search highlight colors also include a `@media (prefers-color-scheme: dark)` block in the injected `<style>` element.

## Gotchas

- **No Python changes needed for HTML dark mode.** WebKit handles `prefers-color-scheme` natively.
- **`Color.refresh()` mutates class attributes.** All code reading `Color.BG_PRIMARY` etc. gets the updated value after refresh. Widgets that cache colors at construction must implement `refresh_colors()`.
- **Icon cache must be cleared.** SF Symbol icons are rendered as bitmaps with a specific tint. The cache key doesn't include color, so `clear_cache()` is required before re-rendering.
- **Menu bar icons are not refreshed.** They're baked into `wx.MenuItem` at construction and are too small (11pt) to matter visually.
