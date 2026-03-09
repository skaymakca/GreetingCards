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

| Situation | Mechanism |
|---|---|
| Entire file is untestable (benchmark, interactive harness, trampoline) | `omit` in pyproject.toml |
| A branch/function within a tested file requires unavailable runtime (framework, live GUI, etc.) | `# pragma: no cover` |
| Code that *could* be tested but isn't yet | Neither — write a test |

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

**Files:** `app/gui/components/review_panel.py`, `app/gui/components/preview_panel.py`, `app/gui/components/drop_target.py`, `app/gui/components/html_viewer.py`
**Mechanism:** `# pragma: no cover`
**Lines excluded:** ~470

Event handlers bound to wx widgets (`EVT_PAINT`, `EVT_KEY`, `EVT_CHECKBOX`, `EVT_MOUSE`, etc.) that are dispatched by the wx event loop. These functions:
- Require a running `wx.App` with real widget geometry
- Perform trivial delegation to already-tested business logic
- Cannot be invoked directly without a live event loop providing valid event objects

The business logic they delegate to is tested independently via the test suite.

### 3. NSObject / Objective-C Bridge

**Files:** `app/gui/appearance.py`, `app/core/apple_events.py`
**Mechanism:** `# pragma: no cover`
**Lines excluded:** ~5

- **KVO observer** (`appearance.py`) — `observeValueForKeyPath_ofObject_change_context_` callback triggered by macOS appearance change notifications
- **Apple Events safety guards** (`apple_events.py`) — defensive `if self is None` checks required by PyObjC's bridging model

### 4. Omitted Files

**Configured in:** `pyproject.toml` `[tool.coverage.run] omit`
**Files:** 7 entries

| Pattern | Reason |
|---|---|
| `scripts/*/__main__.py` | Entry-point trampolines (2–3 lines calling `cli.main()`) |
| `scripts/benchmark/*` | Benchmark suite requiring real PDFs and tesserocr hardware |
| `scripts/profiling/*` | Runtime profiler instrumenting live app with cProfile |
| `scripts/visual_test.py` | Interactive wxPython GUI harness for manual visual inspection |
| `scripts/dark_mode_cycler.py` | AppleScript-driven macOS dark mode toggle |
| `scripts/dmg/dmgbuild_settings.py` | Executed by dmgbuild with injected `defines` dict, not importable |
| `scripts/build_family_name_db/benchmark_compression.py` | Compression format benchmark requiring real TSV data |

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
