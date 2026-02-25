# Licenses Viewer

Generates comprehensive license HTML from a layered system: config files, `uv.lock`, `.dist-info` metadata, and committed license texts.

**Key files:**
- `app/core/license_models.py` — dataclasses (PackageCategory, SystemDep, PackageOverride, LicenseConfig, DiscoveredPackage, LicenseRegistry)
- `app/core/license_discovery.py` — discovery + HTML generation logic
- `app/gui/licenses_dialog.py` — viewer only (~30 lines)
- `content/licenses/config.toml` — manual configuration: `[[system]]` seeds and `[[package]]` overrides
- `content/licenses/manual/` — handwritten license texts (committed, never auto-modified)

## Directory Structure

```
content/                         ← Committed source assets
└── licenses/
    ├── config.toml              ← [[system]] seeds + [[package]] overrides
    └── manual/                  ← Hand-written license texts
        ├── python.txt
        └── tesseract.txt

_build/                          ← Gitignored generated artifacts
├── licenses/
│   ├── registry.toml            ← Generated: resolved state of all packages
│   └── texts/                   ← Auto-extracted from .dist-info
│       ├── anthropic.txt
│       ├── pillow.txt
│       └── ...
└── runtime_content/html/
    ├── licenses/                ← Generated HTML output (bundled in app)
    │   ├── index.html
    │   ├── greeting-cards.html
    │   ├── system.html
    │   ├── runtime.html
    │   ├── development.html
    │   ├── transitive.html
    │   └── page_order.txt       ← Navigation manifest (read at runtime)
    └── common/
        ├── css/viewer.css       ← Shared stylesheet (referenced via ../common/css/viewer.css)
        └── js/search.js         ← Shared search/highlight functions
```

## Config Format

`content/licenses/config.toml` uses two array-of-tables sections:

### `[[system]]` — Seeds for dependencies not in `uv.lock`

```toml
[[system]]
slug = "python"
display = "Python"
version = "3.14"
license_type = "PSF License 2.0"
notes = "Bundled via PyInstaller"
url = "https://python.org"
```

### `[[package]]` — Overrides for auto-discovered fields

Non-empty fields override the auto-discovered value. Empty/missing fields are ignored.

```toml
[[package]]
name = "anthropic"
display = "Anthropic SDK"
```

Available override fields: `display`, `category`, `license_type`, `homepage`, `notes`.

## How It Works

### Two-Phase Pipeline

**Phase 1: `sync_registry()`** (entry point for `make licenses-sync`):

1. Reads `content/licenses/config.toml` for system deps and package overrides
2. Computes SHA-256 hash of `uv.lock`
3. Parses `uv.lock` (TOML) for all package names, versions, and dependency edges
4. Finds greeting-cards direct deps in `uv.lock` → Runtime category
5. Reads `pyproject.toml` dev group → Development category
6. Everything else → Transitive category
7. For each package, finds its `.dist-info` directory in site-packages:
   - Extracts license type from `METADATA`
   - Extracts homepage URL from `METADATA` (`Project-URL` or `Home-page` fields)
   - Extracts license text and writes to `_build/licenses/texts/<slug>.txt` (only when version changed or file missing)
8. Applies config overrides (display name, category, etc.)
9. Writes `_build/licenses/registry.toml` with full resolved state

**Phase 2: `generate_licenses_html()`** (entry point for `make html-content`):

1. Calls `sync_registry()` to ensure registry is up to date
2. Reads app license from repo root `LICENSE` file
3. Reads license texts from `content/licenses/manual/` (source) and `_build/licenses/texts/` (generated)
4. Renders Jinja2 templates to produce category-based HTML pages (flat structure, no `pages/` subdir)
5. CSS is shared via `../common/css/viewer.css` (no copy step needed)
6. JS is included via `../common/js/search.js`

### Invalidation

- **uv.lock hash change:** Triggers full re-sync of all packages
- **Version change:** Individual text files regenerated when package version differs from registry
- **manual/ files:** Never auto-touched; edits are always manual

## HTML Structure

Licenses are grouped into **category pages** (6 files). Each category page contains all packages in that category, separated by `<hr class="version-divider">` dividers.

### Page Types

| File                  | Content                                                    |
|-----------------------|------------------------------------------------------------|
| `index.html`          | Overview with dependency type explanations, summary tables |
| `greeting-cards.html` | App's own BSD 3-Clause license                             |
| `system.html`         | Python and Tesseract (not in uv.lock)                      |
| `runtime.html`        | Libraries the app directly imports                         |
| `development.html`    | Testing, development, and build tools                      |
| `transitive.html`     | Dependencies pulled in by other packages                   |

### Linking

- **Index table** links to `category_page.html#slug` (e.g. `runtime.html#anthropic`)
- **Sidebar** links to category pages (not individual packages)
- **Homepage links** (↗) appear in both index tables and category page headings, linking to package websites

## Dataclasses

All data structures use Python dataclasses from `app/core/license_models.py`:

| Class               | Purpose                                                                          |
|---------------------|----------------------------------------------------------------------------------|
| `PackageCategory`   | Enum: RUNTIME, DEVELOPMENT, TRANSITIVE                                           |
| `SystemDep`         | Python, Tesseract (not in uv.lock); includes `url` field                         |
| `PackageOverride`   | Partial entry from config.toml; non-empty fields override auto-discovered values |
| `LicenseConfig`     | Parsed from config.toml: system deps + package overrides                         |
| `DiscoveredPackage` | One per package with version, license, category, text file path, homepage        |
| `LicenseRegistry`   | Full resolved state: hash + system deps + packages                               |

## Data Sources

| Source                              | Data                                                                     |
|-------------------------------------|--------------------------------------------------------------------------|
| `content/licenses/config.toml`      | System dep seeds, package overrides (display name, category, etc.)       |
| `uv.lock`                           | Package names, versions, dependency graph; greeting-cards deps = Runtime |
| `pyproject.toml`                    | Dev dependency group → Development category                              |
| `.dist-info/METADATA`               | License type, homepage URL                                               |
| `.dist-info/licenses/` or `LICENSE` | Full license text                                                        |
| `content/licenses/manual/*.txt`     | Hand-written license texts for system deps                               |
| `LICENSE` (repo root)               | App's own license text                                                   |

## Package Categories

| Category    | Meaning             | How determined                                |
|-------------|---------------------|-----------------------------------------------|
| Runtime     | App imports it      | In greeting-cards' direct deps in `uv.lock`   |
| Development | Dev/build tool      | In `pyproject.toml` `[dependency-groups] dev` |
| Transitive  | Pulled in by others | Everything else                               |

Config overrides can force any package into a specific category via the `category` field.

## Templates

HTML is generated from Jinja2 templates in `content/html/templates/`:

- `base.html.j2` — shared DOCTYPE/head/body layout with sidebar and content blocks
- `licenses_sidebar.html.j2` — simple flat list of category page links
- `licenses_index.html.j2` — extends base; dependency type explanations + three overview tables
- `licenses_page.html.j2` — extends base; renders multiple license entries with `<hr>` dividers, anchor IDs, and homepage links

Templates use `autoescape=True` for safety. Data is passed as dicts for template compatibility.

## Sidebar Structure

```
Home
Greeting Cards
System
Runtime
Development
Transitive
```

Simple flat list — each entry links to a category page. Active page is highlighted.

## Menu Integration

Help menu → "Licenses" → calls `show_licenses(parent)` → `show_viewer()` with `singleton_key="licenses"`.

The viewer reads from `_build/runtime_content/html/licenses/` (dev mode) or `_MEIPASS/_runtime_content/html/licenses/` (bundle). `get_page_order(base_path)` reads `page_order.txt` from the output directory. See `docs/architecture/html-viewer.md` for the shared manifest pattern.

## Make Targets

```makefile
licenses-sync:  # Sync registry from uv.lock + .dist-info → _build/licenses/
html-content:   # generates help, changelog, and licenses HTML → _build/runtime_content/html/
```

Both `run` and `app` targets depend on `html-content`. `make licenses-sync` still exists as a standalone target for use after `uv add`.

## Gotchas

- **`.dist-info` naming varies:** Package names use PEP 503 normalization (hyphens ↔ underscores). The `_find_dist_info()` function normalizes both sides for matching.
- **Missing `.dist-info`:** Platform-specific packages not installed on macOS (greenlet, pefile, pywin32-ctypes) may lack dist-info. These show "Unknown" license type and "License text not available."
- **License text location varies:** Some packages use `licenses/` subdir (modern format), others use root `LICENSE`/`COPYING`. The `_find_license_file()` function checks both.
- **`License:` field may be missing:** Falls back to `Classifier: License :: OSI Approved ::` or "See LICENSE file".
- **Homepage extraction priority:** Checks `Project-URL: Homepage/Repository/Source` first, falls back to `Home-page:` field.
- **App license reads from repo root:** The `LICENSE` file is read at generation time, not hardcoded. This ensures the real copyright holder name appears.
- **Run `make licenses-sync` after `uv add`:** uv has no post-sync hooks, so registry sync must be triggered manually after dependency changes.
