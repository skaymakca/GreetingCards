# DMG Creation

Produces a polished drag-to-install DMG for macOS distribution using **dmgbuild**.

**Key files:** `scripts/dmg/dmgbuild_settings.py` (layout config), `scripts/dmg/` (orchestrator + README + background generators), `content/dmg/readme.md` (readme source), `content/dmg/Sample Cards/` (bundled sample PDFs)

---

## Build Pipeline

```
make dmg
  ├── make app                                  (existing: icon → content → tessdata → PyInstaller)
  └── uv run python -m scripts.dmg
        ├── scripts.dmg.background.generate()  → _build/dmg/background.png + background@2x.png
        ├── scripts.dmg.readme.generate()      → _build/dmg/Read Me.rtfd/
        └── dmgbuild.build_dmg(...)            → dist/Greeting Cards - X.Y.Z.dmg
```

---

## DMG Window Layout (660 × 480 logical points)

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│    [Greeting Cards.app]  ───────────▶  [Applications]           │
│         (152, 105)         arrow         (482, 105)              │
│                                                                  │
│    [Read Me.rtfd]              [Sample Cards]                    │
│       (152, 285)                (482, 285)                       │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

Icon positions were determined by manual Finder placement on an editable (UDRW) DMG, then extracted from the `.DS_Store` binary via `struct.unpack` on Iloc entries.

---

## Files in the DMG

| Item | Source | Role |
|---|---|---|
| `Greeting Cards.app` | `dist/Greeting Cards.app` | The app bundle |
| `Applications` | symlink → `/Applications` | Drop target |
| `Read Me.rtfd` | `_build/dmg/Read Me.rtfd` (generated) | Quick-start instructions with app icon |
| `Sample Cards/` | `content/dmg/Sample Cards/` | Example PDFs |

Files are added in order: Read Me, Sample Cards, then the app last. This prevents Finder from pre-selecting the app when the DMG opens.

---

## `scripts/dmg/` Package

The orchestrator package handles the full DMG build:

| Module | Purpose |
|---|---|
| `__main__.py` | CLI entry point: reads version, generates background + README, calls dmgbuild |
| `readme.py` | Converts `content/dmg/readme.md` → RTFD with embedded icon |
| `background.py` | Generates 1× and @2x gradient background with arrow and small-caps label |

### Orchestrator flow (`__main__.py`)

1. Read version from `pyproject.toml`
2. Call `background.generate()` → `_build/dmg/background.png` + `background@2x.png`
3. Call `readme.generate(version)` → `_build/dmg/Read Me.rtfd/`
4. Call `dmgbuild.build_dmg()` with:
   - Settings: `scripts/dmg/dmgbuild_settings.py`
   - Volume name: `"Greeting Cards - {version}"`
   - Defines: `app_path`, `readme_path`, `sample_cards_path`, `background`
   - Output: `dist/Greeting Cards - {version}.dmg`

The `--editable` flag builds a read-write (UDRW) DMG for manual icon positioning in Finder.

---

## `scripts/dmg/dmgbuild_settings.py`

A Python file executed by dmgbuild at runtime. dmgbuild injects a `defines` dict containing values passed via the Python API:

| define key | Value |
|---|---|
| `app_path` | `dist/Greeting Cards.app` |
| `readme_path` | `_build/dmg/Read Me.rtfd` |
| `sample_cards_path` | `content/dmg/Sample Cards` |
| `background` | `_build/dmg/background.png` |
| `format` | `UDRW` (only when `--editable`) |

Because `defines` is injected at runtime and not imported, ruff raises F821 (undefined name). This is suppressed globally for `scripts/dmg/dmgbuild_settings.py` via `pyproject.toml` per-file-ignores. pyright also excludes this file.

Key settings: `icon_size = 80`, `text_size = 13`, `show_icon_preview = True`, `window_rect = ((200, 200), (660, 480))`.

---

## Background Image

`scripts/dmg/background.py` generates two PNGs:
- `_build/dmg/background.png` — 660×480 (1× logical size)
- `_build/dmg/background@2x.png` — 1320×960 (Retina)

dmgbuild automatically discovers the `@2x` variant when both files are in the same directory and combines them into a multi-page TIFF for the DMG. Finder displays the @2x version on Retina screens.

The background contains:
- **Gradient:** Left-to-right steel-blue-gray → near-white
- **Arrow:** Subtle right-pointing arrow between app and Applications icons, shaft ends at triangle base
- **Label:** "Drag to Install" in small caps using San Francisco (SFNS.ttf) at Semibold weight (650), with Helvetica fallback

All coordinates scale with a `scale` parameter (1 or 2) so both resolutions are pixel-consistent.

---

## Read Me

`content/dmg/readme.md` is the committed Markdown source. `scripts/dmg/readme.py` converts it to an RTFD package at build time, injecting:

- 128×128 app icon (centred, via `\NeXTGraphic` — RTFD is required because TextEdit does not render `\pict\pngblip` images in plain RTF)
- "Greeting Cards" title (bold, large)
- "Version: X.Y.Z" subtitle (grey)
- Markdown body: `## headings`, `**bold**`, numbered lists, bullet lists, paragraphs

The RTFD package contains `TXT.rtf` (the RTF text with a `\NeXTGraphic icon.png` reference) and `icon.png` (copied from `content/images/icon.png`).

Output: `_build/dmg/Read Me.rtfd/` (generated RTFD package, gitignored).

### Why RTFD, not RTF

The Read Me was originally generated as a plain RTF file using the standard `\pict\pngblip` image embedding syntax. Despite adding the correct `\picw`/`\pich` pixel dimensions and converting the source PNG from RGBA to RGB, the icon never appeared in TextEdit. **TextEdit on macOS does not render `\pict\pngblip` images in plain RTF at all.** This is a fundamental limitation, not a missing field.

The correct format for images in TextEdit is **RTFD** (Rich Text Format Directory) — a macOS package (directory with a `.rtfd` extension) containing:
- `TXT.rtf` — the RTF text with `\NeXTGraphic` references
- The image files themselves (e.g. `icon.png`)

RTFD originated in NeXTSTEP and is the native rich text format on macOS.

### NeXTGraphic syntax

The image reference syntax in `TXT.rtf` is:

```rtf
{{\NeXTGraphic icon.png \width2560 \height2560 \noorient \appleattachmentpadding0 \appleembedtype0 \appleaqc
}\'ac}
```

Key structural details:
- **Double braces** `{{`/`}}` — outer group wraps the NeXTGraphic destination
- **Placeholder character** `\'ac` (byte 0xAC) between the inner `}` and outer `}` — this is Cocoa's attachment anchor in the text stream; without it TextEdit renders the icon but silently drops all text after it
- **Apple-specific attributes** — `\appleattachmentpadding0 \appleembedtype0 \appleaqc`
- **`\noorient`** — prevents orientation changes on reflow
- **Width/height in twips at 72 DPI** — 128px × 20 twips/pt = 2560 twips
- **Pre-resize the image** — TextEdit ignores `\width`/`\height` for display scaling; the image renders at its native pixel size, so resize to 128×128 before placing it in the package

The `\*` ignorable destination prefix (formally correct per the RTF spec) causes TextEdit to drop content after the image — use bare `\NeXTGraphic` without it.

### Debugging trick: the TextEdit no-op save

When iterating on generated RTF syntax, a useful trick to see exactly what TextEdit expects:

1. Generate the file and open it in TextEdit
2. Make a trivial no-op edit (add a newline at the end, then delete it)
3. Save and close
4. Read the `TXT.rtf` file again and diff against the original

TextEdit rewrites the entire document in its preferred normalized form when saving. Comparing before/after reveals what Cocoa's RTF writer actually emits — the canonical format for that version of macOS. This is how we discovered the `\'ac` placeholder, the `\appleaqc` attribute, the correct `\width2560` value, and that `\noorient` should be included.

---

## Sample Cards

`content/dmg/Sample Cards/` contains four PDFs showing naming patterns the app handles:

| File | Content | Pattern |
|---|---|---|
| `Christmas Card - Morales Family.pdf` | Hispanic, Christmas | Named (named pattern) |
| `IMG_4102.pdf` | Slavic, Season's Greetings | Camera import |
| `Scan 2024-12-22 at 3.45 PM.pdf` | South Asian, Diwali | Scanner timestamp |
| `Photo Dec 25 2024, 9 15 AM.pdf` | West African, Kwanzaa | Apple Photos |

Three of four cards have "messy" generic filenames — the kind users actually have — showcasing how the app reads card content rather than relying on the filename.

---

## Volume Name

The DMG volume is named `"Greeting Cards - X.Y.Z"` (version injected at build time from `pyproject.toml`).

---

## Format & Compression

`UDBZ` (bzip2) — best compression for distribution.

---

## Gotchas & Lessons Learned

### General
- **Spaces in paths:** The output filename contains spaces (`Greeting Cards - X.Y.Z.dmg`). Use `str(output_path)` when passing to dmgbuild.
- **badge_icon path:** Constructed from `app_path` at runtime (`app_path + "/Contents/Resources/icon.icns"`). If the app bundle moves, this breaks — always pass the correct `app_path`.
- **`defines` F821:** ruff suppresses F821 for `scripts/dmg/dmgbuild_settings.py` only, not project-wide. pyright also excludes this file.
- **dmgbuild version:** Requires `>=1.6.1` for reliable Python-based config and UDBZ support.

### Background @2x handling (critical)
- **dmgbuild auto-discovers @2x files.** If `background.png` is in a directory, dmgbuild looks for `background@2x.png` in the same directory and combines both into a multi-page TIFF. If only one exists, it uses that single image.
- **Stale @2x files cause silent breakage.** If you regenerate `background.png` but a stale `background@2x.png` remains from a previous build, dmgbuild combines the new 1× with the old @2x — and Finder displays the old @2x on Retina screens. The fix: always regenerate both files together (which `background.generate()` now does).
- **Background not updating? Check for orphan files in `_build/dmg/`.** This was the root cause of extensive debugging — calibration images were correct in the 1× PNG but Finder always showed the stale @2x image.

### Icon positioning
- **Use an editable UDRW DMG** (`--editable` flag) to manually position icons in Finder, then extract coordinates from the `.DS_Store` binary. This is far more reliable than guessing coordinates.
- **DS_Store Iloc format:** 16 bytes per entry: x (4 bytes, big-endian uint32) + y (4 bytes) + 8 bytes padding. Parse with `struct.unpack('>II8x', data)`.
- **Iloc coordinates ≠ icon image centre.** Finder renders icon images above the Iloc point. The Iloc is the anchor point for the icon+label unit, not the image centre.
- **PIL and Finder use the same coordinate system.** Confirmed empirically: crosshairs drawn at Iloc positions in PIL appear directly under icon images in Finder.

### mac_alias and NSURL bookmarks
- **mac_alias generates old-style Alias records** for the background image reference in the DS_Store. Modern macOS (Sequoia+) uses NSURL bookmarks (starting with `book`). The old Alias format still works as of macOS Tahoe for background images.
- **If mac_alias breaks in a future macOS:** A monkey-patch approach was tested that replaces `mac_alias.Alias.for_file` with an NSURL bookmark shim using `Foundation.NSURL.bookmarkDataWithOptions_`. This was removed since it's not currently needed, but the approach is proven to work. See git history for the implementation.

### Applications symlink icon
- **The Applications folder alias icon (folder with arrow)** sometimes appears as a dashed-box placeholder. This is a Finder rendering bug, not an alias format issue. Relaunching Finder (`killall Finder`) fixes it. Plain symlinks (`/Applications`) work correctly — no need for NSURL bookmark aliases.
