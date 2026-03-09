# Testing Exclusions

How and why certain code is excluded from coverage tracking. Companion to [`docs/coverage-analysis.md`](../coverage-analysis.md).

---

## Exclusion Mechanisms

There are two ways to exclude code from coverage tracking, each suited to different situations:

### `[tool.coverage.run] omit` — entire files

Used for files that are **entirely untestable** as a unit. These are never imported by the test suite and contain no logic that can be meaningfully exercised in isolation.

Configured in `pyproject.toml` under `[tool.coverage.run]`:

```toml
[tool.coverage.run]
omit = [
    "scripts/*/__main__.py",       # Entry-point trampolines
    "scripts/benchmark/*",         # Requires real hardware/data
    # ... etc
]
```

### `# pragma: no cover` — specific branches or functions

Used for code **within otherwise-tested files** where specific branches or functions cannot execute in the test environment. The rest of the file is tested normally.

```python
if sparkle.is_available():  # pragma: no cover — Sparkle framework not available in tests
    # This block only runs in the signed app bundle
    ...
```

### When to use which

| Situation                                                                                       | Mechanism                |
|-------------------------------------------------------------------------------------------------|--------------------------|
| Entire file is untestable (benchmark, interactive harness, trampoline)                          | `omit` in pyproject.toml |
| A branch/function within a tested file requires unavailable runtime (framework, live GUI, etc.) | `# pragma: no cover`     |
| Code that *could* be tested but isn't yet                                                       | Neither — write a test   |

---

## Exclusion Categories

### 1. Sparkle Framework Integration

**Files:** `app/core/sparkle.py`, `app/gui/dialogs/settings.py`, `app/gui/components/toolbar.py`, `app/core/services/config_service.py`
**Mechanism:** `# pragma: no cover`
**Lines excluded:** ~22

The Sparkle auto-update framework (`Sparkle.framework`) is loaded via PyObjC from the app bundle's `Contents/Frameworks/` directory. It is only available in the signed, bundled `.app` — never during test execution.

Excluded code includes:
- **ObjC exception handler** (`sparkle.py`) — `except Exception` block that catches PyObjC class loading failures
- **Updater start success path** (`sparkle.py`) — `logger.debug` after `startUpdater()` completes
- **Auto-update UI** (`settings.py`) — checkbox creation and event handler behind `is_available()` guard
- **Menu item insertion** (`toolbar.py`) — "Check for Updates" menu item and binding behind `is_available()` guard
- **Config wrappers** (`config_service.py`) — `has_prompted_auto_update()` and `set_prompted_auto_update()`, thin facades only called from Sparkle UI paths

### 2. wxPython Event Handlers

**Files:** `app/gui/components/review_panel.py`, `app/gui/components/preview_panel.py`, `app/gui/components/drop_target.py`
**Mechanism:** `# pragma: no cover`
**Lines excluded:** ~420

Event handlers bound to wx widgets (`EVT_PAINT`, `EVT_KEY`, `EVT_CHECKBOX`, `EVT_MOUSE`, etc.) that are dispatched by the wx event loop. These functions:
- Require a running `wx.App` with real widget geometry
- Perform trivial delegation to already-tested business logic
- Cannot be invoked directly without a live event loop providing valid event objects

The business logic they delegate to is tested independently via the test suite.

**Note:** `app/gui/components/html_viewer.py` search methods (`_mark_all`, `_focus_match`, `_clear_highlights`, `_navigate_to_page`, `current_page_info`, `on_page_loaded`) were previously excluded but are now tested via mock patching of the WebView's `RunScript`, `GetCurrentURL`, and `LoadURL` methods.

### 3. NSObject / Objective-C Bridge

**Files:** `app/gui/appearance.py`, `app/core/apple_events.py`
**Mechanism:** `# pragma: no cover`
**Lines excluded:** ~8

- **KVO observer** (`appearance.py`) — `observeValueForKeyPath_ofObject_change_context_` callback triggered by macOS appearance change notifications
- **Apple Events safety guards** (`apple_events.py`) — defensive `if self is None` checks required by PyObjC's bridging model
- **Apple Events closure** (`apple_events.py`) — `_do()` closure inside `handleGetLoadedCards_reply_`, dispatched via `_call_on_main_thread` and not reachable in tests without a live NSAppleEventManager

### 4. wx.CallAfter Closures and App Entry Point

**Files:** `app/gui/main_window.py`
**Mechanism:** `# pragma: no cover`
**Lines excluded:** ~7

Closures passed to `wx.CallAfter` that are defined inside methods running in background threads or during layout. These closures:
- Are dispatched by the wx event loop and require a running `wx.App` to execute
- Perform trivial delegation to already-tested methods on the main thread

Excluded code includes:
- **`_apply` closure** (`_apply_content_sash_position`) — reads splitter width and sets sash position after layout
- **`_on_progress` closure** (`_process_cards`) — forwards processing progress to the main thread
- **`_on_complete` closure** (`_process_cards`) — signals processing completion on the main thread
- **`run()` method** — app entry point that calls `self._frame.Show()`, only executable with a live `wx.App`

### 5. Script `if __name__ == "__main__"` Guards

**Files:** `scripts/dmg/background.py`, `scripts/dmg/readme.py`, `scripts/reformat_md_tables.py`, `scripts/run_tests.py`
**Mechanism:** `# pragma: no cover`
**Lines excluded:** ~4

Direct-execution entry points in scripts that have their `main()` functions tested via imports. The `if __name__ == "__main__"` guard line itself is not reachable when the module is imported by the test suite.

### 6. Unreachable Defensive Guards

**Files:** `scripts/reformat_md_tables.py`, `scripts/build_family_name_db/merger.py`
**Mechanism:** `# pragma: no cover`
**Lines excluded:** ~2

Guards that are structurally unreachable due to preceding logic but exist as safety nets:
- **Fence handler guard** (`reformat_md_tables.py`) — `if table_lines` inside `in_code_block` block is always empty because the fence toggle at line 82-84 already flushes `table_lines` before entering the code block body
- **No-candidates guard** (`merger.py`) — `if not candidates: continue` can never trigger because `all_keys` is the union of all source dicts, so at least one source always provides a candidate

### 7. Omitted Files

**Configured in:** `pyproject.toml` `[tool.coverage.run] omit`
**Files:** 7 entries

| Pattern                                                 | Reason                                                            |
|---------------------------------------------------------|-------------------------------------------------------------------|
| `scripts/*/__main__.py`                                 | Entry-point trampolines (2–3 lines calling `cli.main()`)          |
| `scripts/benchmark/*`                                   | Benchmark suite requiring real PDFs and tesserocr hardware        |
| `scripts/profiling/*`                                   | Runtime profiler instrumenting live app with cProfile             |
| `scripts/visual_test.py`                                | Interactive wxPython GUI harness for manual visual inspection     |
| `scripts/dark_mode_cycler.py`                           | AppleScript-driven macOS dark mode toggle                         |
| `scripts/dmg/dmgbuild_settings.py`                      | Executed by dmgbuild with injected `defines` dict, not importable |
| `scripts/build_family_name_db/benchmark_compression.py` | Compression format benchmark requiring real TSV data              |

---

## Guidelines

### When to add `# pragma: no cover`

Add the pragma when **all** of these are true:
1. The code requires a runtime dependency unavailable in tests (Sparkle framework, live wx event loop, macOS KVO)
2. The logic is trivial (delegation, logging, simple state updates)
3. The surrounding file is otherwise well-tested
4. Mocking the dependency would be complex and add no meaningful confidence

### When NOT to exclude

- **Testable logic** — if a function contains branching, validation, or transformation, write a test instead
- **Error paths that can be triggered** — if you can simulate the error condition, test it
- **New features** — default to writing tests; only exclude after confirming the runtime dependency cannot be mocked

### Adding a new exclusion

1. Add `# pragma: no cover` with a brief `—` reason suffix
2. Update this document's relevant category section
3. Run coverage to verify the exclusion takes effect
