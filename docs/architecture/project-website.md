# Project Website

The project website is a Hugo-generated static site hosted on GitHub Pages alongside the Sparkle appcast.

**Key files:** `website/`, `.github/workflows/deploy-website.yml`

---

## Architecture Overview

```
website/                      Hugo source (on main branch)
  hugo.toml                   Site config (baseURL, params, feature list)
  content/
    _index.md                 Homepage content (tagline + description)
  layouts/                    Custom templates (no external theme)
    _default/
      baseof.html             Base template (head, nav, footer)
      single.html             Single page template
      list.html               List page template
    index.html                Homepage — composes hero, features, download
    partials/
      hero.html               Hero section (icon, title, CTA, screenshot)
      features.html           Feature grid (6 cards with inline SVG icons)
      download.html           Download CTA section
  static/                     Static assets (CSS, images)
    css/style.css             Landing page styles (warm neutral palette, dark mode)
    images/
      icon.png                App icon (copied from content/images/)
      screenshot.png          Full app screenshot (original PNG, ~3 MB)
      screenshot.jpg          Compressed screenshot (quality 85, ~600 KB — served in HTML)
  public/                     Build output (gitignored)
```

Hugo source lives on `main` in `website/`. Changes go through normal PR review and CI. No external theme — templates are self-contained to avoid git submodule complexity.

### Design

Single-page landing page with "warm precision" aesthetic — Apple-style layout with warm neutrals instead of cold whites/blacks. Key design elements:

- **Warm palette:** `#FAFAF8` light / `#111113` dark backgrounds
- **Dark mode:** Automatic via `prefers-color-scheme` media query
- **Sticky nav:** Frosted-glass blur effect
- **Feature grid:** 3 columns (desktop), 2 (tablet), 1 (mobile) with hover lift
- **Entrance animations:** Staggered fade-in-up on page load
- **Screenshot:** Served as compressed JPG; original PNG kept as source of truth

### Configuration

`hugo.toml` contains `[params]` with:
- App metadata: `description`, `tagline`
- URLs: `githubRepo`, `releasesURL`
- `[[params.features]]` array: each entry has `title`, `description`, `icon` (maps to inline SVG in `features.html`)

### Version Sync

The app version is sourced from `pyproject.toml` (single source of truth) and injected into Hugo at build time via a generated data file:

1. `make website` / `make website-serve` run the `_sync-website-version` Makefile target
2. This reads `pyproject.toml` and writes `website/data/version.json` (`{"version": "X.Y.Z"}`)
3. Hugo templates reference `{{ .Site.Data.version.version }}` (in `download.html`)
4. The generated file is gitignored (`website/data/.gitignore`)

The CI deploy workflow (`.github/workflows/deploy-website.yml`) performs the same sync step before running `hugo --minify`. This ensures `make bump-*` targets only need to update `pyproject.toml` — the website version follows automatically.

---

## Appcast Coexistence

The `gh-pages` branch hosts both the Hugo-generated website and `appcast.xml`. They coexist through independent, non-conflicting operations:

| Operation    | What it does                                              | Preserves other files? |
|--------------|-----------------------------------------------------------|------------------------|
| Hugo deploy  | `peaceiris/actions-gh-pages@v4` with `keep_files: true`   | Yes — appcast.xml      |
| Appcast push | `cmd_push()` does `git add appcast.xml` (not `git add .`) | Yes — Hugo output      |

**Race conditions:** Extremely unlikely — Hugo deploy only triggers on `website/**` changes to main, appcast push is manual and takes seconds. If they overlap, one push fails non-fast-forward and can be retried.

---

## Deploy Workflow

`.github/workflows/deploy-website.yml`:

- **Trigger:** Push to `main` with changes in `website/**`, or manual `workflow_dispatch`
- **Runner:** `ubuntu-latest` (Hugo is cross-platform)
- **Steps:** Checkout → Install Hugo → Build with `--minify` → Deploy to gh-pages
- **Key setting:** `keep_files: true` preserves `appcast.xml` on gh-pages

The workflow uses `peaceiris/actions-gh-pages@v4` which force-pushes Hugo output to the `gh-pages` branch, but `keep_files: true` ensures files not in Hugo's output (like `appcast.xml`) are preserved.

---

## GitHub Pages Configuration

The site is served at `https://skaymakca.github.io/GreetingCards/`. The `/GreetingCards/` subpath is required for GitHub Pages project repos. Hugo's `baseURL` in `hugo.toml` is set accordingly, and template functions (`relURL`, `absURL`) handle path prefixing automatically.

**GitHub repo settings:** Pages should be configured to deploy from the `gh-pages` branch (root).

---

## Local Development

```bash
make website         # Build site to website/public/
make website-serve   # Dev server with live reload at http://localhost:1313/GreetingCards/
```

Hugo is a standalone Go binary — install via `brew install hugo`. Not managed by uv.

---

## Gotchas

- **`appcast.xml` is NOT in `website/static/`.** It is generated dynamically with Sparkle EdDSA signatures during release and lives only on gh-pages, managed by `cmd_push()` in `scripts/appcast/cli.py`.
- **`website/public/` is gitignored.** Hugo build output should never be committed to `main`.
- **`keep_files: true` is critical.** Without it, each Hugo deploy would delete `appcast.xml` from gh-pages, breaking auto-updates.
- **The deploy workflow only triggers on `website/**` changes.** Other changes to `main` (code, docs, tests) do not trigger a website deploy.
