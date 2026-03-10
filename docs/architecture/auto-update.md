# Auto-Update (Sparkle 2)

Sparkle 2 provides native macOS auto-update functionality. The app checks for updates via an appcast (XML feed) hosted on GitHub Pages, downloads new versions from GitHub Releases, and installs them seamlessly.

**Key files:** `app/core/sparkle.py`, `scripts/appcast/`, `packaging/Greeting Cards.spec` (Info.plist keys), `packaging/entitlements.plist`

---

## Architecture Overview

```
┌─────────────────┐     HTTPS      ┌─────────────────────────────────────┐
│  Greeting Cards  │ ────────────► │  GitHub Pages (gh-pages branch)     │
│  (.app bundle)   │               │  └── appcast.xml                    │
│                  │               └─────────────────────────────────────┘
│  Sparkle.framework
│  └── SPUStandardUpdaterController       ┌───────────────────────────┐
│      ├── auto-check on schedule         │  GitHub Releases          │
│      └── user-initiated check  ────────►│  └── Greeting-Cards-X.Y.Z.dmg │
└─────────────────┘                       └───────────────────────────┘
```

1. **On launch:** `sparkle.init()` loads `Sparkle.framework` from `Contents/Frameworks/`
2. **After MainLoop:** `sparkle.start()` begins the automatic check schedule
3. **Periodically:** Sparkle fetches `appcast.xml` from GitHub Pages
4. **If update found:** Sparkle shows its native UI, downloads the DMG, and installs

---

## PyObjC Bridge (`app/core/sparkle.py`)

Module-level lifecycle following the `appearance.py` pattern:

| Function                   | Purpose                                      |
|----------------------------|----------------------------------------------|
| `init() -> bool`           | Load framework, create controller (no start) |
| `start()`                  | Begin automatic check schedule               |
| `check_for_updates()`      | User-initiated check (menu item)             |
| `is_available() -> bool`   | True if Sparkle loaded successfully          |
| `get_auto_check_enabled()` | Read Sparkle's auto-check preference         |
| `set_auto_check_enabled()` | Write Sparkle's auto-check preference        |
| `cleanup()`                | Release resources (called on window close)   |

**Graceful degradation:** All functions are safe no-ops when:
- Running from source (`not is_bundled()`)
- Framework not found in the bundle
- Framework fails to load for any reason

Errors are logged but never crash the app.

**Framework loading sequence:**
1. Resolve `Contents/Frameworks/Sparkle.framework` from `sys._MEIPASS`
2. Load via `NSBundle.bundleWithPath_().load()`
3. Get class: `objc.lookUpClass("SPUStandardUpdaterController")`
4. Init with deferred start: `.alloc().initWithStartingUpdater_updaterDelegate_userDriverDelegate_(False, None, None)`

---

## App Lifecycle Integration

```
main.py:
    app = wx.App()
    window = MainWindow()
    ...
    sparkle.init()                    # Load framework
    wx.CallAfter(sparkle.start)       # Deferred start after MainLoop
    ...

MainWindow._on_close():
    sparkle.cleanup()                 # Release resources
```

**Menu item:** "Check for Updates..." appears in the File menu (only when `sparkle.is_available()` is True — i.e., only in bundled mode).

**Settings toggle:** An "Automatically check for updates" checkbox appears in the General preferences page. It reads/writes via `sparkle.get_auto_check_enabled()` / `sparkle.set_auto_check_enabled()`. Sparkle manages its own preferences in `NSUserDefaults` — no changes to `app/core/config.py`.

---

## First-Launch Opt-In

On first launch, before Sparkle starts its automatic check schedule, a dialog asks the user whether to enable automatic update checks:

```
┌─────────────────────────────────────────────┐
│  Automatic Updates                          │
│                                             │
│  Would you like Greeting Cards to           │
│  automatically check for updates?           │
│                                             │
│  You can change this later in Settings.     │
│                                             │
│              [No]    [Yes]                   │
└─────────────────────────────────────────────┘
```

**Implementation:**
- `main.py` → `_startup_sparkle()` checks `has_prompted_auto_update()` from `app/core/config.py`
- The flag `AUTO_UPDATE_PROMPTED` is stored in our `preferences.plist` (not Sparkle's `NSUserDefaults`)
- The user's choice is written to Sparkle via `set_auto_check_enabled()`
- `set_prompted_auto_update()` records that the dialog has been shown
- The dialog appears only once, even across app restarts

**Existing users:** Users who upgrade to a version with this feature will see the dialog once on their next launch — a polite one-time ask consistent with standard macOS behavior when adding auto-update support.

---

## Build Pipeline

### Framework Acquisition

`make sparkle` downloads Sparkle 2 from GitHub Releases:
- Extracts `Sparkle.framework` to `packaging/Sparkle.framework/`
- Extracts CLI tools (`generate_keys`, `sign_update`, `generate_appcast`) to `packaging/sparkle-bin/`
- Both directories are gitignored

### Framework Embedding

`make app` (after PyInstaller):
```
mkdir -p "dist/Greeting Cards.app/Contents/Frameworks"
ditto packaging/Sparkle.framework "dist/Greeting Cards.app/Contents/Frameworks/Sparkle.framework"
```

`ditto` preserves symlinks, extended attributes, and framework structure. The signing script (`scripts/sign/`) automatically handles Sparkle framework binaries as Tier 1 (framework binaries are signed before the main executable).

### Info.plist Keys

Set in `packaging/Greeting Cards.spec`:

| Key               | Value                                                          |
|-------------------|----------------------------------------------------------------|
| `SUFeedURL`       | `https://skaymakca.github.io/GreetingCards/appcast.xml`        |
| `SUPublicEDKey`   | EdDSA public key (empty until key generation)                  |
| `CFBundleVersion` | Unix timestamp (monotonically increasing numeric build number) |

### Entitlements

`packaging/entitlements.plist` includes `com.apple.security.network.client` for outbound HTTPS access (appcast fetch and DMG download).

---

## Appcast Format

```xml
<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">
  <channel>
    <title>Greeting Cards</title>
    <item>
      <title>Version X.Y.Z</title>
      <sparkle:version>{build_number}</sparkle:version>
      <sparkle:shortVersionString>X.Y.Z</sparkle:shortVersionString>
      <sparkle:minimumSystemVersion>13.0</sparkle:minimumSystemVersion>
      <pubDate>{RFC 822 date}</pubDate>
      <enclosure url="https://github.com/.../Greeting-Cards-X.Y.Z.dmg"
                 sparkle:edSignature="..." length="..." type="application/octet-stream" />
    </item>
  </channel>
</rss>
```

Hosted on GitHub Pages via the `gh-pages` branch. The `gh-pages` branch also contains Hugo-generated website output — see `docs/architecture/project-website.md` for how appcast and website coexist.

---

## Appcast Generation (`scripts/appcast/`)

### Subcommands

| Command    | Purpose                                           |
|------------|---------------------------------------------------|
| `generate` | Sign DMG with `sign_update`, generate appcast.xml |
| `push`     | Push appcast.xml to gh-pages branch               |

### `generate` flow

1. Find DMG at `dist/Greeting-Cards-X.Y.Z.dmg`
2. Sign with `packaging/sparkle-bin/sign_update` → EdDSA signature + length
3. Load existing appcast from `gh-pages` branch (if any)
4. Prepend new `<item>` entry
5. Write to `dist/appcast.xml`

### `push` flow

1. Create a temporary git worktree for `gh-pages`
2. Copy `appcast.xml` into it
3. Commit and push
4. Clean up worktree

### CLI

```bash
uv run python -m scripts.appcast generate           # sign + generate
uv run python -m scripts.appcast push               # push to gh-pages
uv run python -m scripts.appcast --dry-run generate  # print commands only
```

---

## EdDSA Key Management

### One-Time Key Generation

```bash
# Generate EdDSA keypair
packaging/sparkle-bin/generate_keys
# → Private key saved to macOS Keychain
# → Public key printed — copy to SUPublicEDKey in spec file

# Backup private key
packaging/sparkle-bin/generate_keys -x /path/to/secure/backup
```

The private key lives in the macOS Keychain (never committed). The public key goes into `SUPublicEDKey` in `packaging/Greeting Cards.spec`.

---

## Release Pipeline Integration

The appcast step runs after `checksum`/`changelog` in the release pipeline (step 8). The push utility (`appcastpush`) runs after `publish` so the DMG URL is live before the appcast references it.

See `docs/architecture/release-pipeline.md` for the full pipeline.

---

## Testing Locally

1. Build with ad-hoc signing: `make app` then `uv run python -m scripts.sign --identity "-"`
2. Verify framework is embedded: `ls "dist/Greeting Cards.app/Contents/Frameworks/Sparkle.framework/"`
3. Launch the app — Sparkle loads, "Check for Updates..." appears
4. For actual update testing, set up a local HTTP server serving `appcast.xml`

---

## What Works Without EdDSA Keys

Everything except actual update delivery:
- Framework loading and UI integration work without keys
- Menu item and settings toggle are functional
- `scripts.appcast generate --dry-run` previews the appcast
- `scripts.appcast push --dry-run` previews the push

Actual update verification requires the EdDSA keypair to be generated and the public key set in `SUPublicEDKey`.
