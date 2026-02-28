# PyCharm Inspection Suppressions

The project includes shared PyCharm settings in `.idea/` (inspection profile, custom dictionary, inspection scope). These are committed to the repository so the team gets consistent inspection behavior out of the box.

PyCharm inspections are run periodically. Most findings are false positives due to wxPython/SQLAlchemy stub limitations, macOS framework imports without stubs, and wxPython API conventions. Genuine issues are fixed; false positives are suppressed with **`# noinspection` comments** on individual statements, classes, or functions. We do not use an inspection profile to disable inspections project-wide — real-time IDE feedback during editing is more valuable than silencing entire categories.

## Non-Python Findings

### Inline Suppression (CSS, HTML, JS)

CSS and HTML support inline suppression comments. JS uses `// noinspection`.

| Language | Syntax                              | Notes                                                                                                                                                             |
|----------|-------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| CSS      | `/*noinspection CssXxx*/`           | No spaces around `noinspection`. Works for property-level inspections. `CssUnusedSymbol` is broken ([WEB-40359](https://youtrack.jetbrains.com/issue/WEB-40359)). |
| HTML     | `<!--noinspection XxxInspection-->` | Must be placed directly before the specific element with the finding, not a parent element.                                                                       |
| JS       | `// noinspection JSXxx`             | Works like Python — place before the statement.                                                                                                                   |

**Suppressed inline:**

| Inspection                  | File         | Technique                                                                                         |
|-----------------------------|--------------|---------------------------------------------------------------------------------------------------|
| CssNonIntegerLengthInPixels | `viewer.css` | `/*noinspection*/` before `letter-spacing: 0.5px`                                                 |
| JSUnusedGlobalSymbols       | `search.js`  | `// noinspection` before `shlMark`, `shlFocus`, `shlClear` — called from Python via `RunScript()` |

### Markdown Findings

Markdown files have no inline suppression mechanism. GrazieInspection (Grammar) findings are fixed in the text rather than suppressed — grammar checking is kept active on Markdown to catch real issues.

MarkdownIncorrectTableFormatting findings are fixed by keeping tables padded/aligned (columns justified with spaces). GrazieInspection findings are fixed in the source text. Both inspections are kept active.

MarkdownUnresolvedFileReference cannot be fixed — all findings are in `content/html/help/1 - index.md` where links to `pages/*.html` are resolved at build time, not on disk. This inspection is suppressed via scope.

**Scope-based suppression:** A shared scope (`.idea/scopes/Markdown_and_Other_Inspection_Suppressions.xml`, pattern `file:*.md`) and inspection profile (`.idea/inspectionProfiles/Project_Default.xml`) disable MarkdownUnresolvedFileReference for Markdown files. This works in both the editor and batch "Inspect Code" runs (fixed in [IJPL-225115](https://youtrack.jetbrains.com/issue/IJPL-225115), PyCharm 2025.3.3).

> **Tip:** If you're writing or editing Markdown with file paths that should resolve on disk (e.g., architecture docs linking to other files), temporarily re-enable MarkdownUnresolvedFileReference in Settings > Editor > Inspections to catch broken links. The scope suppression only exists because the help content files use paths resolved at build time.

## CLI Inspections

PyCharm inspections can be run from the command line via `make pycharm-inspect`. This uses PyCharm's `inspect.sh` to launch a headless IDE instance that runs all inspections from the shared `Project_Default` profile. Results are written as XML files to `/tmp/pycharm-inspect-out/`.

The target auto-detects PyCharm (Professional or Community) in `~/Applications` (JetBrains Toolbox) first, then `/Applications`. It skips gracefully if neither is found. Override with `PYCHARM_APP` env var for non-standard locations.

**Limitations:** The headless runner starts a full IDE instance, so it takes a minute or two. Some inspections (notably Grazie grammar) may not produce results in headless mode. The headless instance may also reset your IDE theme to the default on next launch. For the most complete picture, use Code > Inspect Code inside the IDE.

## Custom Dictionary

Project-specific words are in `.idea/dictionaries/project.xml`. Add technical terms, proper names, and benchmark variable names here to suppress SpellChecking false positives.

## `# noinspection` Comments

### Suppression Syntax

```python
# noinspection PyXxx          — suppress for the next statement
# noinspection PyXxx,PyYyy    — suppress multiple inspections
```

```javascript
// noinspection JSXxx          — suppress for the next statement
```

Place **before a statement** (line-level) or **before a class/function** (scope-level). The comment suppresses the inspection for the entire scope of the next statement.

**Important:**
- Placing `# noinspection` before a module docstring only suppresses for the docstring itself, NOT the entire file. For file-wide suppression, place it before each relevant class or function.
- Suppression on an outer function does NOT propagate into nested functions. Each nested function needs its own `# noinspection` comment.
- Markdown files have **no inline suppression mechanism**. CSS and HTML inline suppression works (see [Non-Python Findings](#non-python-findings) above).

### Inline-Suppressed Inspections

#### PyTypeChecker — wxPython and SQLAlchemy stub gaps
wxPython stubs mistype `tuple[int,int]` vs `wx.Size`, `Bitmap` vs `BitmapBundle`, and similar. SQLAlchemy `InstrumentedAttribute[T]` vs `T` causes false positives in query expressions. pyright catches real type errors in CI.

**Files:** `app/gui/main_window.py`, `app/gui/components/review_panel.py`, `app/gui/components/filter_sidebar.py`, `app/gui/components/preview_panel.py`, `app/gui/dialogs/common.py`, `app/gui/icons.py`, `app/gui/context_menu.py`, `app/gui/components/html_viewer.py` (`build_help_menu` — `Bitmap` vs `BitmapBundle`), `app/core/database.py` (`add_candidate`, `_add_candidate_inline` — `InstrumentedAttribute[int]` vs `int`), `app/gui/components/toolbar.py` (class-level `# noinspection PyProtectedMember,PyTypeChecker` — `Bitmap` vs `BitmapBundle`, `tuple[int,int]` vs `wx.Size`, and protected `MainWindow` member access by design), `scripts/helpers.py` (`script_output_dir` — `@contextmanager` transforms `Generator[Path]` into `AbstractContextManager[Path]` at runtime; PyCharm can't see through the decorator), `scripts/benchmark/ocr_concurrency.py`, `scripts/benchmark/ocr_configuration_quality.py`, `scripts/benchmark/pre_processing_concurrency.py`, `scripts/generate_sample_cards/cli.py`, `scripts/generate_sample_cards/image_generator.py`, `scripts/generate_sample_cards/spec_generator.py`

#### PyUnusedLocal — wxPython callback `event` parameters
All wxPython event callbacks require an `event` parameter by signature even when unused. pyright catches real unused variables in CI.

**Files:** `app/gui/main_window.py`, `app/gui/components/review_panel.py`, `app/gui/components/filter_sidebar.py`, `app/gui/dialogs/settings.py`, `app/gui/dialogs/common.py`, `app/gui/context_menu.py`, `app/gui/components/html_viewer.py`, `scripts/benchmark/ocr_configuration_quality.py`

#### PyUnresolvedReferences — macOS framework imports and dynamic attributes
`app/gui/icons.py` imports Foundation classes (`NSImage`, `NSColor`, etc.) and `app/gui/appearance.py` uses `objc.ivar`. These resolve at runtime on macOS but have no type stubs. `app/gui/main_window.py` has dynamic attributes (`_toolbar`, `_search_ctrl`, `_year_ctrl`, `_reload_id`) set by `ToolbarManager` at init time; suppressed at class level.

**Files:** `app/gui/icons.py`, `app/gui/appearance.py`, `app/gui/main_window.py`

#### PyBroadException — intentional broad catches
Appearance observer, app startup, and process-pool worker error handling catch `Exception` broadly because failures in these paths must not crash the app.

**Files:** `app/gui/appearance.py`, `app/gui/main_window.py` (class-level)

#### PyPep8Naming — wxPython/ObjC API overrides
wxPython requires CamelCase method names for `DataViewModel` overrides (`GetColumnCount`, `GetColumnType`). ObjC bridge methods use Objective-C naming. Style factory methods (`TITLE`, `HEADING`, etc.) use uppercase by convention.

**Files:** `app/gui/components/review_panel.py`, `app/gui/dialogs/common.py`, `app/gui/appearance.py`, `app/gui/styles.py`, `app/gui/main_window.py`

#### PyProtectedMember — PyInstaller and test internals
`sys._MEIPASS` is the standard PyInstaller API for detecting bundled mode. `scripts/visual_test.py` accesses `MainWindow` internals intentionally for the visual test harness.

**Files:** `app/core/paths.py`, `scripts/visual_test.py`

#### PyRedundantParentheses — benchmark return tuples
Benchmark scripts use parenthesized return tuples for readability.

**Files:** `scripts/benchmark/ocr_concurrency.py`, `scripts/benchmark/pre_processing_concurrency.py`

#### PyAttributeOutsideInit — wxPython widget creation pattern
Complex wxPython UIs build widgets in helper methods (`_build_key_section`, etc.) called from `__init__`, not directly in `__init__` itself. PyCharm doesn't trace this pattern.

**Files:** `app/gui/components/filter_sidebar.py`, `app/gui/components/review_panel.py`, `app/gui/dialogs/settings.py`

#### PyUnusedImports — intentional re-exports and optional dependencies
`get_page_order` is re-exported from `changelog.py` and `help_builder.py` for consumer convenience. `cv2` and `numpy` in `scripts/benchmark/common.py` are optional imports used conditionally.

**Files:** `app/core/content/changelog.py`, `app/core/content/help_builder.py`, `scripts/benchmark/common.py`

#### PyMethodMayBeStatic — callbacks and overrides
Methods flagged as "may be static" are wxPython callbacks, DataViewModel overrides, or methods that logically belong to the instance even if they don't currently use `self`.

**Files:** `app/gui/components/filter_sidebar.py`, `app/gui/main_window.py`, `app/gui/components/preview_panel.py`, `app/gui/components/review_panel.py`, `scripts/visual_test.py`

#### PyArgumentList — dynamic dispatch false positives
`wx.GetTopLevelWindows()` and PyObjC dynamic calls trigger false argument-count warnings.

**Files:** `app/gui/main_window.py`, `scripts/visual_test.py`

#### PyShadowingNames — benchmark loop variables
Benchmark scripts reuse variable names in isolated loop iterations and helper functions. Harmless in context.

**Files:** `scripts/benchmark/ocr_concurrency.py`, `scripts/benchmark/pre_processing_concurrency.py`, `scripts/benchmark/ocr_configuration_quality.py`, `app/gui/components/html_viewer.py`

#### PyListCreation — deliberate multistep list building
Benchmark report generation builds lists incrementally for readability.

**Files:** `scripts/benchmark/ocr_concurrency.py`, `scripts/benchmark/pre_processing_concurrency.py`

#### GrazieInspection — technical prose false positives
False positives on technical terms, range notation (`1..N`), code values (`'ai'`), and hyphenated compounds in docstrings and comments.

**Files:** `app/gui/components/filter_sidebar.py`, `app/gui/components/preview_panel.py`, `app/core/database.py`, `app/core/content/help_builder.py`, `scripts/benchmark/ocr_concurrency.py`, `scripts/benchmark/pre_processing_concurrency.py`

#### DuplicatedCode — similar-but-distinct patterns
Benchmark scripts share structural patterns (report generation, result tables) that are intentionally not abstracted. Database CRUD methods have similar shapes by nature.

**Files:** `app/gui/main_window.py`, `app/gui/components/toolbar.py` (`build_menu_bar` — event binding patterns mirror `build_toolbar`), `app/core/database.py`, `app/core/pipeline/pdf_renderer.py`, `scripts/benchmark/ocr_concurrency.py`, `scripts/benchmark/pre_processing_concurrency.py`, `scripts/benchmark/ocr_configuration_quality.py`, `scripts/visual_test.py` (`_build_right_column` — three identical button-creation loops)
