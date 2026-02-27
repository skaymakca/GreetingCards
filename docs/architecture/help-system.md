# Help System

Help pages generated from Markdown and displayed in the shared WebView viewer.

**Key files:** `app/gui/dialogs/help.py` (thin wrapper), `app/core/content/help_builder.py` (Markdown → HTML generation), `app/gui/html_viewer.py` (shared viewer — see `docs/architecture/html-viewer.md`)

## How It Works

`app/gui/dialogs/help.py` is a thin wrapper that calls `show_viewer()` with path resolution. `_HELP_REL_PATH = Path("_build/runtime_content") / "html" / "help"`.

`content/help_builder.py` generates HTML from Markdown source files using the `markdown` library and Jinja2 templates.

## Content Structure

### Source (committed)

Help Markdown files use a filename-based ordering convention:

```
content/html/
├── help/
│   ├── 1 - index.md              ← Home page
│   ├── 2 - getting-started.md
│   ├── 3 - toolbar.md
│   ├── 4 - card-list.md
│   ├── 5 - preview.md
│   ├── 6 - shortcuts.md
│   ├── 7 - ai-models.md
│   └── 8 - tips.md
├── common/
│   ├── css/viewer.css            ← Shared stylesheet for all viewers
│   └── js/search.js              ← JavaScript search/highlight functions
└── templates/
    └── help_page.html.j2         ← Jinja2 template for help pages
```

### Filename convention

Files must be named `<order> - <slug>.md` where `<order>` is a positive integer starting at 1 with no gaps or duplicates. The slug becomes the HTML filename (e.g. `getting-started.html`). The pipeline errors out if numbering is invalid.

To reorder pages, rename the numeric prefixes. To add a page, insert at the desired position and renumber subsequent files.

### Generated output (gitignored)

```
_build/runtime_content/html/
├── help/
│   ├── index.html                ← Generated home page
│   ├── page_order.txt            ← Navigation manifest (read at runtime)
│   └── pages/
│       ├── getting-started.html
│       ├── toolbar.html
│       ├── card-list.html
│       ├── preview.html
│       ├── shortcuts.html
│       └── tips.html
└── common/
    ├── css/viewer.css            ← Copied from content/html/common/css/
    └── js/search.js              ← Copied from content/html/common/js/
```

### Markdown Frontmatter

Each Markdown file has YAML frontmatter defining the page title:

```markdown
---
title: Getting Started
---

# Getting Started

Page content here...
```

If `title` is omitted, it defaults to the slug converted to title case.

## Generation Pipeline

`help_builder.py` generates HTML via `make content`:

1. Reads Markdown files from `content/html/help/`, parses numeric order from filenames
2. Validates numbering (contiguous 1..N, no gaps, no duplicates)
3. Parses YAML frontmatter for title
4. Converts Markdown to HTML using the `markdown` library
5. Renders through `content/html/templates/help_page.html.j2` with Jinja2
6. Writes output to `_build/runtime_content/html/help/`
7. Writes `page_order.txt` manifest for runtime toolbar navigation
8. Copies shared CSS and JS to `_build/runtime_content/html/common/`

Every generated page has the same HTML structure:

```html
<div class="sidebar">
    <h2>Contents</h2>
    <ul><!-- nav links, one marked class="active" --></ul>
</div>
<div class="content">
    <!-- page body -->
</div>
```

Sidebar navigation is generated automatically from the filename ordering.

## Page Navigation

`get_page_order(base_path)` in `content/help_builder.py` reads `page_order.txt` from the generated output directory. This manifest is written during generation and preserves the numeric filename ordering. The shared viewer toolbar provides Home, Previous, Next navigation. See `docs/architecture/html-viewer.md` for toolbar, search, and manifest details.

## CSS

`content/html/common/css/viewer.css` is the shared stylesheet for all viewers. It defines:
- Flexbox layout (sidebar + content)
- Sidebar styling (160px wide, #f5f5f5 background)
- Content area (max-width 600px, scrollable)
- Typography, tables, code blocks, keyboard shortcuts
- Version date and divider styles (used by changelog)

The file is copied to `_build/runtime_content/html/common/css/viewer.css` during generation. All viewers reference it via relative path.

## Menu Integration

Help menu → "Greeting Cards Help" → calls `show_help(parent)` → `show_viewer()` with `singleton_key="help"`.
