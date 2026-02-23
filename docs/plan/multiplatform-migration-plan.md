# Multiplatform Migration Plan

A detailed analysis and plan for extending Greeting Cards to Windows and Linux while preserving the native macOS experience.

## Current State

The app runs on macOS with wxPython, PyMuPDF, pytesseract, and the Anthropic API. Most of the codebase is already cross-platform by virtue of using Python and wxPython. The macOS-specific surface area is concentrated in a few well-defined modules.

### Portability Scorecard

| Layer | Files | Status |
|-------|-------|--------|
| **Core logic** | ai_analyzer, database, name_extractor, name_formatting, pdf_renderer, renamer, constants | **Fully portable** — no changes needed |
| **Data model** | card.py | **Fully portable** |
| **Config storage** | config.py, paths.py | **macOS-only** — plist format + ~/Library paths |
| **OCR engine** | ocr_engine.py | **Needs abstraction** — hardcoded Homebrew paths |
| **GUI panels** | review_panel, preview_panel, filter_sidebar, dialogs | **Cross-platform** — standard wxPython widgets |
| **GUI infrastructure** | main_window, utils, context_menu, api_key_dialog | **Cross-platform** (minor text adaptations) |
| **Icons** | icons.py | **macOS-only** — SF Symbols via PyObjC |
| **Settings** | settings_dialog.py | **macOS-only** — wx.PreferencesEditor |
| **Help** | help_dialog.py | **Cross-platform** — WebView with icon fallbacks |
| **Build** | Makefile, .spec | **macOS-only** — .icns, lsregister, sips |

**Bottom line:** ~80% of the code works as-is on all platforms. The remaining ~20% is concentrated in 6 files that need platform abstraction.

---

## Architecture Options

### Option A: Platform Adapter Modules

Factor platform-specific code into adapter modules selected at startup.

```
app/
├── core/
│   ├── platform/
│   │   ├── __init__.py      # detect_platform(), export adapters
│   │   ├── base.py          # Abstract base classes (protocols)
│   │   ├── macos.py         # macOS implementations
│   │   ├── windows.py       # Windows implementations
│   │   └── linux.py         # Linux implementations
│   ├── config.py            # Uses platform.config_store()
│   ├── paths.py             # Uses platform.get_data_dir()
│   └── ocr_engine.py        # Uses platform.find_tesseract()
├── gui/
│   ├── icons.py             # Uses platform.load_icon()
│   ├── settings_dialog.py   # Uses platform.create_preferences()
│   └── ...                  # Everything else unchanged
```

**Pros:** Clean separation, each platform file is self-contained, easy to test in isolation.
**Cons:** More files, indirection for simple things like paths.

### Option B: Inline Platform Detection

Use `sys.platform` checks directly in the 6 affected files.

```python
# In paths.py
import sys

def get_data_dir() -> Path:
    if not is_bundled():
        return Path(__file__).resolve().parent.parent.parent
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    data_dir = base / "GreetingCards"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir
```

**Pros:** Simple, minimal new files, changes stay close to existing code.
**Cons:** Platform logic scattered across files, harder to find all platform-specific code.

### Option C: Inheritance-Based GUI Specialization

Use base classes for shared GUI logic with platform subclasses for native features.

```python
# Base class with all cross-platform logic
class MainWindowBase:
    def __init__(self):
        self._build_menu_bar()
        self._build_toolbar()
        self._build_panels()

    def _build_toolbar(self):
        """Build toolbar with platform-neutral icons."""
        ...

    def _get_icon(self, name: str) -> wx.Bitmap:
        """Override in platform subclass for native icons."""
        return wx.NullBitmap

    def _show_preferences(self):
        """Override in platform subclass for native preferences."""
        raise NotImplementedError

    def _open_file(self, path: Path):
        """Override in platform subclass for native file opening."""
        raise NotImplementedError

# macOS specialization
class MainWindowMac(MainWindowBase):
    def _get_icon(self, name: str) -> wx.Bitmap:
        return load_sf_symbol(name, ...)

    def _show_preferences(self):
        editor = wx.PreferencesEditor(...)
        editor.Show(self._frame)

    def _open_file(self, path: Path):
        subprocess.Popen(["open", str(path)])

# Windows specialization
class MainWindowWin(MainWindowBase):
    def _get_icon(self, name: str) -> wx.Bitmap:
        return load_png_icon(name, ...)

    def _show_preferences(self):
        dialog = PreferencesDialog(self._frame)
        dialog.ShowModal()

    def _open_file(self, path: Path):
        os.startfile(path)

# Factory
def create_main_window() -> MainWindowBase:
    if sys.platform == "darwin":
        return MainWindowMac()
    elif sys.platform == "win32":
        return MainWindowWin()
    return MainWindowLinux()
```

**Pros:** Platform logic is organized by platform, not by feature. Easy to see everything macOS does differently.
**Cons:** Deeper class hierarchy, harder to follow control flow, risk of "god base class" with too many abstract methods. Main window is already complex at 1600+ lines.

### Recommended: Option A + B Hybrid

Use **Option A** (adapter modules) for the two biggest platform boundaries — icons and preferences — where entire implementations differ. Use **Option B** (inline detection) for the smaller items (paths, config, OCR, file operations) where a simple `if/elif` is clearer than an adapter class.

This avoids the class hierarchy complexity of Option C while keeping the most complex platform-specific code properly isolated.

---

## Detailed Migration Plan

### Phase 1: Platform Detection Foundation

Create a minimal platform module used by all other code.

**New file: `app/core/platform.py`**

```python
import sys

MACOS = sys.platform == "darwin"
WINDOWS = sys.platform == "win32"
LINUX = sys.platform.startswith("linux")

def modifier_key_symbol() -> str:
    return "⌘" if MACOS else "Ctrl"

def option_key_symbol() -> str:
    return "⌥" if MACOS else "Alt"
```

**Files changed:** None yet — this is a new foundation module.

### Phase 2: Data Directory & Config Storage

**`app/core/paths.py`** — Inline platform detection:

```python
def get_data_dir() -> Path:
    if not is_bundled():
        return Path(__file__).resolve().parent.parent.parent
    if MACOS:
        base = Path.home() / "Library" / "Application Support"
    elif WINDOWS:
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:  # Linux
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    data_dir = base / "GreetingCards"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir
```

**`app/core/config.py`** — Replace plist with JSON (cross-platform):

| | macOS (current) | Cross-platform (proposed) |
|---|---|---|
| Format | Binary plist | JSON |
| Library | `plistlib` | `json` (stdlib) |
| File | `preferences.plist` | `preferences.json` |
| Read | `plistlib.load(f)` | `json.load(f)` |
| Write | `plistlib.dump(data, f)` | `json.dump(data, f, indent=2)` |

JSON is human-readable, cross-platform, and supported everywhere. The config data is simple key-value pairs (API key, AI model) that map naturally to JSON.

**Migration path:** On first run, if `preferences.plist` exists but `preferences.json` doesn't, migrate automatically.

### Phase 3: OCR Engine

**`app/core/ocr_engine.py`** — Platform-specific tesseract discovery:

```python
if is_bundled() and not shutil.which("tesseract"):
    if MACOS:
        search_paths = ["/opt/homebrew/bin/tesseract", "/usr/local/bin/tesseract"]
    elif WINDOWS:
        search_paths = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ]
    else:  # Linux
        search_paths = ["/usr/bin/tesseract", "/usr/local/bin/tesseract"]

    for p in search_paths:
        if Path(p).is_file():
            pytesseract.pytesseract.tesseract_cmd = p
            break
```

### Phase 4: File Operations

**`app/gui/review_panel.py`** — Replace `open` and `open -R` commands:

```python
def _open_file(path: Path) -> None:
    if MACOS:
        subprocess.Popen(["open", str(path)])
    elif WINDOWS:
        os.startfile(path)
    else:
        subprocess.Popen(["xdg-open", str(path)])

def _reveal_in_file_manager(path: Path) -> None:
    if MACOS:
        subprocess.Popen(["open", "-R", str(path)])
    elif WINDOWS:
        subprocess.Popen(["explorer", "/select,", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path.parent)])
```

Also rename "Reveal in Finder" menu text:

```python
label = "Reveal in Finder" if MACOS else "Show in Explorer" if WINDOWS else "Show in File Manager"
```

### Phase 5: Icons (Adapter Module)

This is the largest platform boundary. SF Symbols are macOS-only and deeply integrated.

**Strategy:** Keep `icons.py` as the public API. Internally dispatch to platform-specific loaders.

**Current SF Symbols used:**

| Context | Symbol Name | Meaning |
|---------|------------|---------|
| Toolbar | `folder.badge.plus` | Add files |
| Toolbar | `sparkles` | AI analyze |
| Toolbar | `pencil` | Rename |
| Toolbar | `xmark.circle` | Clear |
| Menu | `doc.text`, `folder`, `magnifyingglass` | File operations |
| Menu | `scissors`, `square.on.square` | Cut, copy |
| Context | `textformat.abc` | Title case |
| Preview | `plus.magnifyingglass`, `minus.magnifyingglass` | Zoom cursors |
| Help | `chevron.left`, `chevron.right`, `house` | Navigation |

**Windows/Linux approach:** Bundle PNG icons as resources. Use a consistent icon set (e.g., Feather Icons, Material Icons, or custom PNGs).

```
resources/
├── icons/
│   ├── folder-plus.png       # Add files
│   ├── sparkles.png          # AI analyze
│   ├── pencil.png            # Rename
│   ├── x-circle.png          # Clear
│   └── ...
```

**`app/gui/icons.py`** changes:

```python
def load_toolbar_icon(name: str, ...) -> wx.Bitmap | None:
    if MACOS:
        return _load_sf_symbol(name, ...)
    return _load_png_icon(_SF_TO_PNG[name], ...)

# Mapping table
_SF_TO_PNG = {
    "folder.badge.plus": "folder-plus",
    "sparkles": "sparkles",
    "pencil": "pencil",
    "xmark.circle": "x-circle",
    ...
}
```

### Phase 6: Settings Dialog

`wx.PreferencesEditor` and `wx.StockPreferencesPage` are macOS-native. On Windows/Linux, replace with a standard tabbed dialog.

**Strategy:** The General and Advanced page *contents* (API key field, model dropdown, reset button) are already standard wxPython widgets. Only the container (PreferencesEditor vs Dialog) differs.

```python
def create_preferences_editor(on_db_reset=None):
    if MACOS:
        # Native macOS Preferences window
        editor = wx.PreferencesEditor("Greeting Cards")
        editor.AddPage(GeneralPreferencesPage())
        editor.AddPage(AdvancedPreferencesPage(on_db_reset=on_db_reset))
        return editor
    else:
        # Cross-platform tabbed dialog
        return PreferencesDialog(on_db_reset=on_db_reset)

class PreferencesDialog(wx.Dialog):
    """Cross-platform preferences dialog with tabs."""
    def __init__(self, on_db_reset=None):
        super().__init__(None, title="Settings", style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        notebook = wx.Notebook(self)
        notebook.AddPage(GeneralPanel(notebook), "General")
        notebook.AddPage(AdvancedPanel(notebook, on_db_reset), "Advanced")
        ...
```

The page contents stay the same — only the container changes.

### Phase 7: Fonts & Keyboard Hints

**`app/gui/styles.py`** — Platform-adaptive font family:

```python
def _system_font_family() -> str:
    if MACOS:
        return "Helvetica Neue"
    elif WINDOWS:
        return "Segoe UI"
    return "sans-serif"  # Linux: wxPython resolves to system default

def _monospace_font_family() -> str:
    if MACOS:
        return "Menlo"
    elif WINDOWS:
        return "Consolas"
    return "monospace"  # Linux: wxPython resolves to system default
```

**UI text:** Replace hardcoded `⌘O` in drop overlay and `⌥-click` in sidebar tooltips:

```python
# Drop overlay
f"Drag PDFs here or press {modifier_key_symbol()}+O"

# Filter sidebar tooltip
f"{option_key_symbol()}-click to multi-select"
```

### Phase 8: Build System

Each platform needs its own build configuration.

**macOS** (existing):
- PyInstaller → `.app` bundle
- `icon.icns` via `iconutil`
- `lsregister` for cache management

**Windows** (new):
- PyInstaller → `.exe` (single file or directory)
- `icon.ico` converted from PNG via Pillow
- Optional: NSIS or Inno Setup installer
- Spec file: `Greeting Cards-win.spec`

**Linux** (new):
- PyInstaller → directory bundle or AppImage
- `.desktop` file for application menu entry
- PNG icon at standard sizes (48x48, 128x128, 256x256)
- Spec file: `Greeting Cards-linux.spec`

**Makefile** adaptation: Add platform targets or use separate build scripts per OS.

```makefile
build-macos:
    pyinstaller -y "Greeting Cards.spec"

build-windows:
    pyinstaller -y "Greeting Cards-win.spec"

build-linux:
    pyinstaller -y "Greeting Cards-linux.spec"
```

---

## What Does NOT Need to Change

These components work identically on all platforms with no modifications:

| Component | Why It's Portable |
|-----------|------------------|
| AI analyzer | Pure Python + Anthropic API |
| Database (SQLAlchemy/SQLite) | Paths abstracted via paths.py |
| Name extractor (regex) | Pure text processing |
| Name formatting | Pure text processing, already handles all OS invalid chars |
| PDF renderer (PyMuPDF) | Cross-platform C library |
| Renamer | Uses pathlib throughout |
| Card data model | Pure Python dataclasses |
| Review panel | Standard wx.DataViewCtrl |
| Preview panel | Standard wx.Panel + wx.GraphicsContext (cursor icons have fallback) |
| Filter sidebar | Standard wx.Panel + wx.CheckBox |
| All dialogs | Standard wx.Dialog + wx.DataViewCtrl |
| Help system (WebView) | wx.html2.WebView with platform-specific backend (API identical) |
| API key dialog | Standard wx.TextEntryDialog |
| Context menus | Standard wx.Menu (icons have fallback) |
| Drag & drop | Standard wx.FileDropTarget |
| All event handling | Standard wx.EVT_* bindings |
| Keyboard shortcuts | wxPython auto-maps Ctrl↔Cmd on macOS |

---

## Risk Assessment

### High Risk (test thoroughly)

| Area | Risk | Mitigation |
|------|------|------------|
| WebView on Windows | IE/Edge WebView2 may render help HTML differently | Test early; consider wx.html.HtmlWindow fallback |
| Tesseract availability | Users may not have tesseract installed | Clear error message with install instructions per platform |
| PyInstaller bundling | Platform-specific quirks with bundled dependencies | CI/CD testing on each OS |

### Medium Risk (likely works, verify)

| Area | Risk | Mitigation |
|------|------|------------|
| wxPython rendering | Toolbar, splitters, DataView may look different | Visual testing on each platform |
| File case sensitivity | Linux is case-sensitive, macOS/Windows are not | Renamer already uses `.lower()` for dedup |
| Path separators | Windows uses `\`, Unix uses `/` | Already using `pathlib.Path` everywhere |

### Low Risk (safe assumptions)

| Area | Notes |
|------|-------|
| SQLite | Works identically everywhere |
| PIL/Pillow | Cross-platform image library |
| Anthropic API | HTTP calls work everywhere |
| asyncio | Cross-platform event loop |

---

## Implementation Order

Suggested sequence that delivers working builds incrementally:

| Phase | Work | Enables |
|-------|------|---------|
| 1. Platform detection | New `platform.py` module | Foundation for all other phases |
| 2. Paths & config | JSON config, platform data dirs | App can store preferences on all platforms |
| 3. OCR engine | Platform-specific tesseract discovery | OCR works on all platforms |
| 4. File operations | Open/reveal abstractions | Context menu works on all platforms |
| 5. Icons | PNG fallback icon set | Toolbar and menus render on all platforms |
| 6. Settings dialog | Cross-platform preferences dialog | Settings accessible on all platforms |
| 7. Fonts & text | Platform-adaptive fonts and key labels | Native look on each platform |
| 8. Build system | Per-platform PyInstaller specs | Distributable builds |

After Phase 4, the app is **functional** on all platforms (with blank toolbar icons).
After Phase 5, the app is **visually complete**.
After Phase 8, the app is **distributable**.

---

## Dependency Changes

| Dependency | macOS | Windows | Linux |
|------------|-------|---------|-------|
| wxPython | ✅ | ✅ (pip install) | ✅ (pip install, may need GTK3 dev libs) |
| PyMuPDF | ✅ | ✅ | ✅ |
| pytesseract | ✅ | ✅ | ✅ |
| Tesseract binary | Homebrew | Installer from GitHub | `apt install tesseract-ocr` |
| anthropic | ✅ | ✅ | ✅ |
| Pillow | ✅ | ✅ | ✅ |
| SQLAlchemy | ✅ | ✅ | ✅ |
| PyObjC (AppKit) | ✅ (SF Symbols) | N/A | N/A |
| python-dotenv | ✅ | ✅ | ✅ |

**New dependency for Windows/Linux:** None required. The `platformdirs` package is optional (can inline the logic).

---

## Testing Strategy

### Unit Tests
All 949 existing tests should pass on all platforms without modification — they test core logic and mock GUI interactions. Run the full suite on each OS in CI.

### GUI Testing
Manual testing checklist per platform:

- [ ] App launches and shows drop overlay
- [ ] File dialog opens and selects PDFs
- [ ] Drag & drop works
- [ ] PDF preview renders correctly
- [ ] Toolbar icons render (not blank)
- [ ] Menu bar renders with correct shortcuts (Ctrl+ on Win/Linux, Cmd+ on macOS)
- [ ] Settings dialog opens with API key and model dropdown
- [ ] AI analysis runs and updates cards
- [ ] Rename workflow completes
- [ ] Help viewer renders HTML and search works
- [ ] Context menu shows Open, Reveal, Remove
- [ ] "Reveal in Finder/Explorer/File Manager" opens correct application
- [ ] Filter sidebar toggles work
- [ ] Keyboard shortcuts work (Ctrl+O, Ctrl+F, etc.)

### CI/CD
Use GitHub Actions with matrix builds:

```yaml
strategy:
  matrix:
    os: [macos-latest, windows-latest, ubuntu-latest]
```
