# Project Instructions for Claude

## 🚫 CRITICAL: NO AUTO-COMMITS 🚫

**NEVER commit code without explicit user request.**

- ❌ Do NOT commit after completing tasks
- ❌ Do NOT commit after writing tests
- ❌ Do NOT commit after fixing bugs
- ✅ ONLY commit when user explicitly says "commit X"
- ✅ Keep track of changes to write good commit messages when asked
- ✅ Include `Fixes #N` or `Fixes #N, #M` in commit/PR messages when the work resolves GitHub issues
- ✅ **Always commit ALL unstaged changes** — never do partial/selective commits unless explicitly told to. Tests run against the full working tree, so partial commits can leave broken states in the history.

---

## 🚫 CRITICAL: NO SENSITIVE DATA IN COMMITS 🚫

**NEVER commit secrets, credentials, or user-specific identity information.**

- ❌ Do NOT commit certificate files (`.cer`, `.p12`, `.p8`, `.pem`, `.key`)
- ❌ Do NOT commit `.env` files or inline secrets in code
- ❌ Do NOT hardcode signing identities, Apple IDs, team IDs, or keychain profile names
- ❌ Do NOT include user-specific paths, names, or identifiers in committed code
- ✅ Use environment variables (`$CODESIGN_IDENTITY`) or macOS Keychain for credentials
- ✅ Use CLI flags (`--identity`, `--keychain-profile`) that read from env/keychain
- ✅ Keep examples generic: `your@email.com`, `TEAMID`, `YOUR_IDENTITY`

---

## 🚫 CRITICAL: DO NOT MODIFY GITHUB ISSUES 🚫

**NEVER create, close, or edit GitHub issues without explicit user permission.**

- ❌ Do NOT create new issues without being asked
- ❌ Do NOT close or modify existing issues without being asked
- ✅ ONLY manage issues when user explicitly asks you to
- Use `gh issue list` to view open issues
- **GitHub repo:** `skaymakca/GreetingCards` — ALWAYS use `--repo skaymakca/GreetingCards` for `gh` commands, and `repos/skaymakca/GreetingCards/...` for `gh api` URL paths. The username is **skaymakca**, NOT sukru or any other variant.

---

## ⚠️ CRITICAL: ALWAYS USE ABSOLUTE PATHS ⚠️

**NEVER use `cd` in commands. ALWAYS use absolute paths.**

- ❌ `cd /some/dir && command` — triggers manual approval for path resolution
- ❌ `cd /some/dir; command > file` — triggers manual approval
- ✅ `command /absolute/path/to/target` — runs without approval friction
- ✅ `gh issue create --repo owner/repo` — no cd needed
- The working directory is `/Users/sukru/code/GreetingCards` — use absolute paths from there
- You have full access to the codebase. Find files with Glob/Grep, reference them by absolute path.

---

## ⚠️ CRITICAL: ALWAYS USE UV ⚠️

**NEVER use system Python or pip. ONLY use `uv run` for all commands.**

### Correct usage:
```bash
# ✅ CORRECT - Use uv run
uv run pytest tests/
uv run python main.py
uv add package-name

# ✅ CORRECT - Install/sync dependencies
uv sync              # all deps (including dev)
uv sync --no-dev     # production only

# ❌ WRONG - System Python (DO NOT USE)
python3 -m pytest tests/
python3 main.py
pip install package-name
.venv/bin/python main.py
/Library/Frameworks/Python.framework/Versions/3.14/bin/python3
```

### Rules:
- **ALWAYS** use `uv run` to execute Python commands
- **ALWAYS** use `uv add` to add new dependencies
- **NEVER** use `python3`, `pip`, or direct `.venv/bin/python` paths
- **NEVER** install packages outside uv's management
- If a command fails, check that you're using `uv run` first
- The venv directory is `.venv` (managed by uv, do not create manually)

---

## ⚠️ Shell Command Rules ⚠️

**Follow these rules for ALL bash commands to avoid permission prompts.**

### No command substitution
- ❌ `git commit -m "$(date)"` — `$(...)` triggers approval
- ❌ `` git commit -m "`date`" `` — backtick substitution also triggers approval
- ✅ Split into two commands: first run `date`, then use the result

### No complex quoting in flag values
- ❌ `grep --include="*.py" pattern`
- ✅ `grep --include='*.py' pattern` or `grep -r pattern --include=\*.py`

### No command chaining (&&, ||, ;)
- ❌ `mkdir build && cmake ..`
- ✅ Issue each command separately, one per Bash tool call
- Exception: simple read-only pipes are fine (e.g., `git log --oneline | head -5`)

### No multiline constructs or heredocs
- ❌ Multi-line bash strings or heredocs in a single command
- ✅ Use the Write tool to create a file, then execute it
- ✅ Or break into sequential single-line commands
- For git commits: use `git commit -m 'single line message'` or write message to a temp file and use `git commit -F /tmp/msg.txt`

### No output redirection for writing files
- ❌ `echo "text" > file.txt` or `command >> file.txt`
- ✅ Use the Write or Edit tool instead

### No inline environment variables
- ❌ `VAR=value command`
- ✅ Use `env VAR=value command` or set variables separately

### No process substitution
- ❌ `diff <(cmd1) <(cmd2)`
- ✅ Write outputs to temp files first, then diff

### No background operators
- ❌ `command &`
- ✅ Use the `run_in_background` parameter on the Bash tool

### Prefer make targets and dedicated tools
- Use `make check`, `make lint`, `make app` etc. — single simple commands
- Use Read/Write/Edit/Grep/Glob tools instead of cat/echo/sed/grep/find

### General principle
When in doubt, break complex shell operations into multiple simple sequential commands. Prefer clarity over cleverness. One command per Bash tool call.

---

## LSP (Language Server Protocol)

**Always use the LSP tool** for code navigation instead of guessing or grepping. It provides accurate, type-aware results.

### When to use LSP
- **`goToDefinition`** — jump to where a symbol is defined (class, function, variable)
- **`findReferences`** — find all usages of a symbol across the codebase
- **`hover`** — get type info and docstrings for a symbol
- **`documentSymbol`** — list all symbols in a file (overview of a module)
- **`goToImplementation`** — find concrete implementations of abstract methods
- **`incomingCalls` / `outgoingCalls`** — trace call chains

### When LSP is better than Grep
- Finding all callers of a method (Grep misses aliased/dynamic calls)
- Navigating to the actual definition (not just string matches)
- Understanding type signatures and overloads
- Getting a quick overview of a module's public API (`documentSymbol`)

### If LSP fails
If the LSP tool returns an error or "no server available", **tell the user immediately** so they can check their LSP configuration. Example: "LSP server is not responding for Python files — you may need to restart it. Falling back to Grep for now."

---

## Project Overview

Greeting Cards - macOS app for organizing and renaming greeting card PDFs using OCR and AI.

### Tech Stack
- Python 3.14 (from python.org)
- wxPython for native macOS GUI
- PyMuPDF for PDF rendering
- Anthropic Claude API for AI analysis

### Notes
- macOS native widgets: use wx widgets without explicit bg colors
- Python 3.14: exception variables cleared after except block
- Always test both source version and app bundle when making UI changes

### Release Pipeline
Release steps (signing, notarization, DMG creation, GitHub release) require per-machine credentials. Run `uv run python -m scripts.configure_release` to interactively generate `release-local.sh` — a gitignored shell script with the developer's signing identity and keychain profile baked in. Use `./release-local.sh <step>` or `./release-local.sh <from>-<to>` to run pipeline steps. Never hardcode credentials in committed code.

### High-Level Layout

```
app/
  core/         # Business logic (OCR, AI, rename, database, PDF, config)
  gui/          # wxPython UI (main window, panels, dialogs, styles, icons)
  models/       # Data models (CardResult, RenamePlanItem, etc.)
content/        # Static assets (HTML templates, CSS, JS, help Markdown, licenses, sdef)
docker/         # Docker infrastructure (Dockerfile, docker-compose.yml)
packaging/      # PyInstaller specs + signing configs (entitlements.plist)
scripts/        # Standalone scripts and benchmarks
  benchmark/    # OCR and concurrency benchmark suite
tests/          # Pytest suite (mirrors app/ structure)
main.py         # Entry point
```

Key entry points:
- `main.py` → `app.gui.main_window.MainWindow` — the app
- `scripts/visual_test.py` — visual test harness for all dialogs/panels
- `packaging/Greeting Cards.spec` — PyInstaller bundle config

---

## Architecture Docs

When editing files in these areas, **read the corresponding doc first**, then **update the doc** if your changes alter the documented behavior.

| Files Being Edited                                                                                                                                                                  | Read First                                                            |
|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------|
| `app/gui/main_window.py` (filters, `_refresh_display`)                                                                                                                              | `docs/architecture/filter-pipeline.md`                                |
| `app/gui/main_window_mixins/*.py`                                                                                                                                                   | `docs/architecture/main-window-mixins.md`                             |
| `app/core/apple_events.py`, `app/core/scripting_protocol.py`                                                                                                                        | `docs/architecture/apple-events.md`                                   |
| `app/gui/main_window_mixins/apple_events_mixin.py`                                                                                                                                  | `docs/architecture/apple-events.md`                                   |
| `app/gui/components/filter_sidebar.py`                                                                                                                                              | `docs/architecture/filter-pipeline.md`                                |
| `app/gui/main_window.py` (card loading, state, dedup)                                                                                                                               | `docs/architecture/card-data-model.md`                                |
| `app/core/card_store.py`, `app/core/services/card_service.py`, `app/core/services/ai_service.py`, `app/core/services/processing_service.py`, `app/core/services/rename_service.py`  | `docs/architecture/card-data-model.md`                                |
| `app/models/card.py`                                                                                                                                                                | `docs/architecture/card-data-model.md`                                |
| `app/gui/components/review_panel.py`                                                                                                                                                | `docs/architecture/review-panel.md`                                   |
| `app/gui/main_window.py` (processing, AI, threads)                                                                                                                                  | `docs/architecture/async-processing.md`                               |
| `app/core/pipeline/ai_analyzer.py`, `app/core/pipeline/ai_batch.py`                                                                                                                 | `docs/architecture/async-processing.md`                               |
| `app/core/pipeline/pdf_worker.py`, `app/core/pipeline/rate_limit.py`, `app/core/pipeline/ocr_engine.py`, `app/core/pipeline/pdf_renderer.py`, `app/core/pipeline/card_processor.py` | `docs/architecture/async-processing.md`                               |
| `app/core/naming/family_name/*.py`                                                                                                                                                  | `docs/architecture/name-pipeline.md`                                  |
| `app/core/naming/extractor.py`, `app/core/naming/filename_safety.py`                                                                                                                | `docs/architecture/name-pipeline.md`                                  |
| `app/core/database.py`, `app/core/naming/renamer.py`                                                                                                                                | `docs/architecture/name-pipeline.md`                                  |
| `app/gui/rename_display.py`                                                                                                                                                         | `docs/architecture/name-pipeline.md`                                  |
| `app/gui/dialogs/help.py`, `app/core/content/help_builder.py`                                                                                                                       | `docs/architecture/help-system.md`                                    |
| `content/html/help/*.md`                                                                                                                                                            | `docs/architecture/help-system.md`                                    |
| `app/gui/components/html_viewer.py`, `content/html/common/js/search.js`                                                                                                             | `docs/architecture/html-viewer.md`                                    |
| `app/core/content/changelog.py`, `app/core/content/changelog_models.py`                                                                                                             | `docs/architecture/changelog-viewer.md`                               |
| `app/gui/dialogs/changelog.py`, `content/html/templates/changelog_page.html.j2`                                                                                                     | `docs/architecture/changelog-viewer.md`                               |
| `app/core/content/license_models.py`, `app/core/content/license_sync.py`                                                                                                            | `docs/architecture/licenses-viewer.md`                                |
| `app/core/content/license_html.py`, `app/gui/dialogs/licenses.py`                                                                                                                   | `docs/architecture/licenses-viewer.md`                                |
| `content/html/templates/licenses_*.html.j2`                                                                                                                                         | `docs/architecture/licenses-viewer.md`                                |
| `content/licenses/config.toml`, `content/licenses/manual/*`                                                                                                                         | `docs/architecture/licenses-viewer.md`                                |
| `CHANGELOG.md`                                                                                                                                                                      | `CLAUDE.md` (changelog conventions below)                             |
| `app/core/config.py`, `app/core/keychain.py`, `app/core/paths.py`, `app/core/services/config_service.py`                                                                            | `docs/architecture/config-and-preferences.md`                         |
| `app/gui/dialogs/settings.py`                                                                                                                                                       | `docs/architecture/config-and-preferences.md`                         |
| `app/gui/appearance.py`, `app/gui/styles.py` (Color.refresh)                                                                                                                        | `docs/architecture/dark-mode.md`                                      |
| `app/gui/icons.py` (clear_cache, icon tint)                                                                                                                                         | `docs/architecture/dark-mode.md`                                      |
| `app/gui/main_window.py` (appearance observer, refresh)                                                                                                                             | `docs/architecture/dark-mode.md`                                      |
| `content/html/common/css/viewer.css` (color variables)                                                                                                                              | `docs/architecture/dark-mode.md`                                      |
| `scripts/*.py` (adding/removing/renaming scripts)                                                                                                                                   | Update `Makefile` `show-scripts` target + `README.md` Scripts section |
| `scripts/generate_sample_cards/**`                                                                                                                                                  | `docs/architecture/sample-card-generator.md`                          |
| `scripts/helpers.py`, `scripts/**/__main__.py`                                                                                                                                      | `docs/architecture/scripts-infrastructure.md`                         |
| `tests/scripts/**`                                                                                                                                                                  | `docs/architecture/scripts-infrastructure.md`                         |
| `# noinspection` comments in any `*.py` file                                                                                                                                        | `docs/architecture/pycharm-inspections.md`                            |
| `# pragma: no cover` comments in any `*.py` file, `[tool.coverage.run] omit` in `pyproject.toml`                                                                                   | `docs/architecture/testing-exclusions.md`                             |
| `scripts/dmg/**` (including `dmgbuild_settings.py`)                                                                                                                                 | `docs/architecture/dmg-creation.md`                                   |
| `content/dmg/readme.md`, `content/dmg/Sample Cards/`                                                                                                                                | `docs/architecture/dmg-creation.md`                                   |
| `scripts/sign/**`, `scripts/notarize/**`, `scripts/release/**`                                                                                                                      | `docs/architecture/release-pipeline.md`                               |
| `app/core/sparkle.py`                                                                                                                                                               | `docs/architecture/auto-update.md`                                    |
| `scripts/appcast/*.py`                                                                                                                                                              | `docs/architecture/auto-update.md`                                    |
| `scripts/configure_release/*.py`                                                                                                                                                    | `docs/architecture/release-pipeline.md`                               |
| `packaging/entitlements.plist`, `packaging/Greeting Cards.spec` (upx/signing)                                                                                                       | `docs/architecture/release-pipeline.md`                               |
| `README-Release-Checklist.md`                                                                                                                                                       | `docs/architecture/release-pipeline.md`                               |
| Markdown tables in any `*.md` file                                                                                                                                                  | `docs/pycharm-table-formatting.md`                                    |
| `docker/Dockerfile`, `docker/docker-compose.yml`, `.github/workflows/ci.yml`, `.github/actions/setup-build-env/action.yml`                                                          | `docs/architecture/docker-and-ci.md`                                  |

### Test Count
When adding or removing tests, update the test count in `README.md` (search for "tests** covering") to match the actual number from `pytest` output.

### Keeping Docs in Sync

- **After modifying code:** If your changes affect control flow, data structures, callback contracts, or gotchas described in an architecture doc, update the doc in the same work session. Don't leave stale docs behind.
- **If docs contradict code:** The code is the source of truth. Update the doc to match. If the code seems wrong based on the doc's described intent, flag the discrepancy to the user before changing either — it may be an out-of-date doc or a misaligned implementation that needs discussion.
- **New subsystems:** If you add a major new subsystem (new panel, new processing pipeline, etc.), create a new doc in `docs/architecture/` and add it to the table above.

### Changelog Conventions

`CHANGELOG.md` is user-facing (not developer-facing). When updating it:

- **Audience:** End users, not developers
- **Format:** Summary sentence(s) first, then bullets
- **Language:** Plain language — describe *what changed*, not *how*
- **Grouping:** Each `major.minor` version gets its own `## ` entry with date; patch versions fold into their parent
- **When to update:** When making user-visible changes
- **Build step:** `make content` regenerates HTML from the Markdown; `make app` runs this automatically

### License Sync

After adding or updating packages with `uv add`, run `make licenses-sync` to update the license registry and extract new license texts. Then run `make content` to regenerate the HTML.

### Timestamp Conventions

- **Core/app code** (`app/`): Use UTC-aware timestamps (`datetime.now(UTC)`)
- **Scripts** (`scripts/`): Use naive local time (`datetime.now()`) — scripts run locally
- **Filename timestamps**: `strftime("%Y%m%dT%H%M")` → `YYYYMMDDThhmm` (e.g., `20260303T1422`)
- **Log format**: ISO 8601 with `T` separator (`%Y-%m-%dT%H:%M:%S`)
- **Elapsed timers**: Use `time.monotonic()`, never `time.time()`

---

## Code Quality Audit

When asked to audit the codebase, follow the methodology in [`docs/code-quality-audit.md`](docs/code-quality-audit.md). Findings go into `_build/audit/YYYYMMDDThhmm-code-quality.md`.

## Coverage Analysis

When asked to analyze or improve test coverage, follow the methodology in [`docs/coverage-analysis.md`](docs/coverage-analysis.md). Analysis goes into `_build/coverage/YYYYMMDDThhmm/coverage-analysis.md`; remediation reports go into `_build/coverage/YYYYMMDDThhmm/remediation-report.md`.

## MVC Compliance Audit

When asked to audit MVC compliance, follow the methodology in [`docs/mvc-compliance-audit.md`](docs/mvc-compliance-audit.md). Findings go into `_build/audit/YYYYMMDDThhmm-mvc-compliance.md`.

---

## Pre-Commit Checks

Before committing, run these checks and fix any issues:

| Command                   | Purpose                                                 | Expected             |
|---------------------------|---------------------------------------------------------|----------------------|
| `make check`              | **All static checks** (type + lint + format + security) | 0 errors             |
| `make pyright`            | Static type checking (strict structural types)          | 0 errors, 0 warnings |
| `make mypy`               | Static type checking (nominal types, plugin-based)      | 0 errors             |
| `make lint`               | Ruff linting (code quality, bug patterns, imports)      | 0 errors             |
| `make format-check`       | Ruff formatting check                                   | 0 reformatted        |
| `make security`           | Bandit security scan (app + scripts)                    | 0 issues             |
| `uv run pytest tests/ -x` | Run all tests                                           | All pass             |

**Quick pre-commit:** `make check && uv run pytest tests/ -x`

**pyright** (`[tool.pyright]` in `pyproject.toml`): Catches structural type errors, unused imports, unreachable code. Zero-warning baseline.

**mypy** (`[tool.mypy]` in `pyproject.toml`): Catches nominal type mismatches, SQLAlchemy plugin issues. `import-untyped` errors are suppressed per-module for stubless third-party libs (wx, AppKit, Foundation, objc, tesserocr, fitz) via `[[tool.mypy.overrides]]`.

**ruff** (`[tool.ruff]` in `pyproject.toml`): Linting (pyflakes, pycodestyle, isort, bugbear, simplify, etc.) and formatting. Use `make lint-fix` for auto-fixes, `make format` to reformat.

**bandit** (`[tool.bandit]` in `pyproject.toml`): Security scanning for app/ and scripts/. Subprocess and known false positives are pre-configured as skips.

---

## PyCharm Inspections (MCP)

When the JetBrains MCP server is available, use PyCharm inspections for deeper semantic analysis beyond what CLI tools catch.

**"Check with PyCharm"** — When asked to check files with PyCharm, inspect all Python files in these directories:
- `main.py`
- `app/**/*.py`
- `scripts/*.py`

Use `mcp__jetbrains__get_file_problems` on each file. **Batch all files in a single parallel call** — PyCharm handles them quickly.

**Expected:** 0 errors, 0 warnings (excluding intentional `# noinspection` suppressions).

**When to use:** As a supplementary check alongside `make check`. PyCharm catches things CLI tools miss (e.g., framework-specific issues, unresolved references in dynamic code, wxPython API misuse).
