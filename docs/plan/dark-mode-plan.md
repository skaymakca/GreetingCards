# Plan: Dark Mode Detection and UI Handling (Issue #3)

## Context

The app has zero dark mode support. All colors are hardcoded for light mode. This is a multi-phase effort with commits after each phase so we can iterate on quality.

---

## Phase 1: Detection + Debug Window

Build the detection infrastructure and a temporary debug window to verify it works.

### 1a. New file: `app/gui/appearance.py`

Uses KVO on `NSApp.effectiveAppearance` (official Apple-supported approach):

```python
import objc
from Foundation import NSObject, NSKeyValueObservingOptionNew
from AppKit import NSApplication

class _AppearanceObserver(NSObject):
    _callback = objc.ivar()

    def observeValueForKeyPath_ofObject_change_context_(self, path, obj, change, ctx):
        if callable(self._callback):
            wx.CallAfter(self._callback)

observer = _AppearanceObserver.alloc().init()
observer._callback = some_function

NSApplication.sharedApplication().addObserver_forKeyPath_options_context_(
    observer, "effectiveAppearance", NSKeyValueObservingOptionNew, 0
)

# Cleanup:
NSApplication.sharedApplication().removeObserver_forKeyPath_(observer, "effectiveAppearance")
```

Module API:
- `is_dark_mode() -> bool` — checks `NSApp.effectiveAppearance().name()` for "Dark"
- `start_observer(callback)` — registers KVO for live changes
- `stop_observer()` — cleanup

### 1b. Temporary debug window

Add a small window that launches alongside the main window showing:
```
Mode: Light  (or)  Mode: Dark
```
Updates live when macOS appearance changes. This validates the detection + observer wiring works before we touch any real UI.

### 1c. Tests for `appearance.py`

Mock `NSApplication` to test `is_dark_mode()` and observer callback.

**Commit after Phase 1.**

---

## Phase 2: Assess + Fix Native wxPython UI

### 2a. Visual assessment in dark mode

Launch the app in dark mode and catalog every element that looks wrong:
- Text invisible (near-black on dark)
- Backgrounds clashing (white panels on dark chrome)
- Icons invisible (near-black on dark toolbar)
- Borders wrong color

### 2b. Minimal override strategy

Only special-case elements that actually need it. The approach:

1. Add `Color.refresh()` to `app/gui/styles.py` — reassigns only the colors that need dark-mode variants (BG_PRIMARY, BG_SECONDARY, BG_SELECTED, TEXT_PRIMARY, TEXT_SECONDARY, BORDER). Semantic colors (ACCENT, SUCCESS, etc.) stay unchanged.

2. Add `Color.icon_hex()` — returns appropriate icon tint color for current mode.

3. Update `app/gui/icons.py` — change `color_hex` defaults to use `Color.icon_hex()`, add `clear_cache()`.

4. Add `refresh_colors()` to panels that set colors at construction time:
   - `filter_sidebar.py` — section header labels
   - `preview_panel.py` — canvas background
   - `review_panel.py` — detail panel labels
   - `html_viewer.py` — toolbar separator line

5. Wire `_on_appearance_changed` in `main_window.py` — refresh colors, clear icon cache, update toolbar icons, call panel `refresh_colors()`, repaint.

6. Menu bar / context menu icons — accept as minor cosmetic issue (baked into wx.MenuItem at construction, 11pt barely visible).

### 2c. Tests for Color.refresh(), icon cache clearing

**Commit after Phase 2.**

---

## Phase 3: HTML/CSS Dark Mode

### 3a. `content/html/common/css/viewer.css`

Convert hardcoded colors to CSS custom properties + `@media (prefers-color-scheme: dark)` block. Pattern already exists in `scripts/benchmark_common.py`.

WebKit in `wx.html2.WebView` respects `prefers-color-scheme` automatically — no Python changes needed.

### 3b. Run `make html-content` to regenerate

### 3c. Visual assessment of Help, Changelog, Licenses viewers in dark mode

**Commit after Phase 3.**

---

## Phase 4: Cleanup + Final Commit

1. Remove the temporary debug window
2. Run code quality checks (pyright, mypy, pytest)
3. Create `docs/architecture/dark-mode.md` and update CLAUDE.md table
4. Update CHANGELOG.md
5. Final commit

---

## Research: Event-Driven Detection Approaches

### Approach 1: KVO on `NSApp.effectiveAppearance` (Selected)

The official Apple-supported way. Observe the `effectiveAppearance` key path on `NSApplication.sharedApplication()`. Uses pyobjc's KVO support with an `NSObject` subclass implementing `observeValueForKeyPath_ofObject_change_context_`.

**Pros:** Official Apple API, fires immediately on change, documented behavior.
**Cons:** Requires NSObject subclass, must remove observer on cleanup.

### Approach 2: NSDistributedNotificationCenter (Rejected)

Listen for `AppleInterfaceThemeChangedNotification`. Simpler API but undocumented notification name (stable since Mojave 2018, widely used).

### Approach 3: Timer Polling (Rejected)

2-second wx.Timer that checks `effectiveAppearance`. Simplest code but not event-driven.

### Sources
- [Indie Stack: Supporting Dark Mode - Responding to Change](https://indiestack.com/2018/10/supporting-dark-mode-responding-to-change/)
- [PyObjC KVO example](https://pyobjc.readthedocs.io/en/latest/examples/Cocoa/Foundation/Scripts/simple-kvo/index.html)
- [Apple: addObserver:forKeyPath:options:context:](https://developer.apple.com/documentation/objectivec/nsobject/1412787-addobserver)
- [Jesse Squires: Observing appearance changes](https://www.jessesquires.com/blog/2020/01/08/observing-appearance-changes-on-ios-and-macos/)

---

## Files Modified (across all phases)

| File | Phase | Change |
|------|-------|--------|
| `app/gui/appearance.py` (new) | 1 | Detection + KVO observer |
| `app/gui/main_window.py` | 1, 2, 4 | Debug window (temp), appearance wiring, cleanup |
| `app/gui/styles.py` | 2 | `Color.refresh()`, `Color.icon_hex()` |
| `app/gui/icons.py` | 2 | Dynamic default color, `clear_cache()` |
| `app/gui/filter_sidebar.py` | 2 | `refresh_colors()` |
| `app/gui/preview_panel.py` | 2 | `refresh_colors()` |
| `app/gui/review_panel.py` | 2 | `refresh_colors()` |
| `app/gui/html_viewer.py` | 2 | `refresh_colors()` |
| `content/html/common/css/viewer.css` | 3 | CSS variables + dark media query |
| `tests/gui/test_appearance.py` (new) | 1 | Detection tests |
| `tests/gui/test_styles.py` | 2 | Color.refresh() tests |
| `docs/architecture/dark-mode.md` (new) | 4 | Architecture doc |

## Verification (each phase)

1. `uv run pyright app/ scripts/` — 0 errors
2. `uv run mypy app/ scripts/` — no new errors
3. `uv run pytest tests/ -x` — all pass
4. Manual test: switch dark/light in System Settings, verify UI updates
