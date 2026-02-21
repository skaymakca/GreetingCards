# Bundling Tesseract in the App Bundle: Technical & Legal Analysis

*Created: 2026-02-20*

## Context

When Tesseract OCR is not installed, the app degrades gracefully (see #4). However, requiring users to install Tesseract via Homebrew is not ideal for a polished app. This document analyzes bundling Tesseract directly into the `.app` bundle.

---

## Legal / Copyright

### Licenses

| Component | License | Commercial Use |
|---|---|---|
| Tesseract OCR | Apache 2.0 | Yes |
| Leptonica | BSD 2-Clause | Yes |
| libpng | libpng/zlib | Yes |
| libjpeg-turbo | BSD-3-Clause + IJG | Yes |
| giflib | MIT | Yes |
| libtiff | BSD-like | Yes |
| libwebp | BSD-3-Clause | Yes |
| openjpeg | BSD-2-Clause | Yes |
| libarchive | BSD-2-Clause | Yes |
| tessdata (all variants) | Apache 2.0 | Yes |

**All licenses are permissive. No GPL, no copyleft, no source disclosure required.**

### Obligations for Binary Redistribution

1. **Include license texts + copyright notices** — e.g., a `THIRD_PARTY_LICENSES` file in the bundle or an Acknowledgments section in the app
2. **Retain original copyright headers** — do not remove or obscure them
3. **State changes** — if modifying Tesseract source, note the changes (not needed for unmodified binaries)
4. No need to redistribute source code
5. No need to open-source the app

### Patent Concerns

None. Apache 2.0 Section 3 includes an explicit patent grant from all contributors (including Google). The LSTM algorithms used by Tesseract are well-established academic work with no outstanding patent claims.

---

## Technical

### What to Bundle (~12-15 MB)

**Dylibs (~7.5 MB):**

| Library | Size | Purpose |
|---|---|---|
| `libtesseract.5.dylib` | 2.7 MB | OCR engine |
| `libleptonica.6.dylib` | 2.1 MB | Image processing |
| `libarchive.13.dylib` | 687 KB | Archive handling |
| `libpng16.16.dylib` | 203 KB | PNG support |
| `libjpeg.8.dylib` | 475 KB | JPEG support |
| `libgif.7.dylib` | 71 KB | GIF support |
| `libtiff.6.dylib` | 527 KB | TIFF support |
| `libwebp.7.dylib` | 344 KB | WebP support |
| `libwebpmux.3.dylib` | 71 KB | WebP muxing |
| `libopenjp2.7.dylib` | 317 KB | JPEG 2000 support |

**Trained data (~4 MB):**

| Data File | Size | Notes |
|---|---|---|
| `eng.traineddata` (tessdata_fast) | ~4 MB | Integer LSTM, fastest — sufficient for printed card text |
| `eng.traineddata` (tessdata_best) | ~15 MB | Float LSTM, most accurate — overkill for this use case |
| `osd.traineddata` | 10 MB | Orientation/script detection — likely not needed |

**Recommendation:** Use `tessdata_fast/eng.traineddata` for smallest size with good accuracy on printed text.

### Bundle Layout

```
Greeting Cards.app/
  Contents/
    MacOS/
      tesseract                 # CLI binary
    Frameworks/
      libtesseract.5.dylib
      libleptonica.6.dylib
      libarchive.13.dylib
      libpng16.16.dylib
      libjpeg.8.dylib
      libgif.7.dylib
      libtiff.6.dylib
      libwebp.7.dylib
      libwebpmux.3.dylib
      libopenjp2.7.dylib
    Resources/
      tessdata/
        eng.traineddata
      THIRD_PARTY_LICENSES
```

### Dylib Path Rewriting

Homebrew dylibs use absolute paths (e.g., `/opt/homebrew/opt/tesseract/lib/libtesseract.5.dylib`). Each must be rewritten with `install_name_tool`:

```bash
# Change a dylib's own identity
install_name_tool -id @loader_path/../Frameworks/libtesseract.5.dylib \
  "Greeting Cards.app/Contents/Frameworks/libtesseract.5.dylib"

# Rewrite cross-references (e.g., libtesseract -> leptonica)
install_name_tool -change \
  /opt/homebrew/opt/leptonica/lib/libleptonica.6.dylib \
  @loader_path/libleptonica.6.dylib \
  "Greeting Cards.app/Contents/Frameworks/libtesseract.5.dylib"
```

This must be done for every cross-reference between the ~10 bundled dylibs.

### Runtime Configuration

In `app/core/ocr_engine.py`, when bundled:
- Set `pytesseract.pytesseract.tesseract_cmd` to the bundled binary path
- Set `TESSDATA_PREFIX` environment variable to `Contents/Resources/`

### Code Signing & Notarization

- Every bundled `.dylib` and the `tesseract` binary must be individually code-signed with hardened runtime
- Sign from inside out: dylibs first, then executables, then the `.app` bundle
- Existing entitlements (`disable-library-validation` for wxPython) should cover loading bundled dylibs
- All Mach-O binaries must have `--options runtime` and a timestamp for notarization

```bash
find "dist/Greeting Cards.app/Contents/Frameworks" -name "*.dylib" | while read lib; do
    codesign --force --sign "$IDENTITY" --timestamp --options runtime "$lib"
done
```

### Architecture

Homebrew on Apple Silicon builds arm64-only. Options:

1. **ARM64 only (recommended)** — Apple Silicon is current/future, Intel Macs are EOL
2. **Universal binary** — build each library twice, merge with `lipo -create` (doubles dylib sizes to ~15 MB)

Given Python 3.14 and the project scope, arm64-only is reasonable.

### Build Process Changes

A new Makefile target would need to:

1. Copy `tesseract` binary from Homebrew into `Contents/MacOS/`
2. Copy ~10 dylibs into `Contents/Frameworks/`
3. Run `install_name_tool -change` on every cross-reference
4. Copy `eng.traineddata` into `Contents/Resources/tessdata/`
5. Code-sign each Mach-O binary individually
6. Create `THIRD_PARTY_LICENSES` file

### Alternative Approaches

| Approach | Pros | Cons |
|---|---|---|
| **Bundle CLI binary** (recommended) | Works with pytesseract as-is, simplest | Must rewrite dylib paths |
| **Use tesserocr** (C++ bindings) | No subprocess overhead | Different API, harder to bundle |
| **Static linking** | No dylib path issues | Requires building from source |
| **Require Homebrew install** (current) | No bundle complexity | Poor UX, requires CLI knowledge |

---

## Recommendation

Bundling is **legally safe** (all permissive licenses) and **technically feasible** (~12-15 MB size impact). The main complexity is dylib path rewriting and per-library code signing.

The current approach — graceful degradation with a `brew install tesseract` prompt (#4) — is a good interim solution. Bundling Tesseract would be the right move for a polished release where zero-dependency install matters.
