# Release Pipeline

Full pipeline for building, signing, notarizing, and publishing a release of Greeting Cards.

**Key files:** `packaging/entitlements.plist`, `scripts/sign/`, `scripts/notarize/`, `scripts/release/`

---

## Pipeline Overview

```
make release-draft
  ├── make release
  │     ├── make notarize
  │     │     ├── make sign
  │     │     │     ├── make app          (icon → content → tessdata → PyInstaller)
  │     │     │     └── scripts.sign      (inside-out codesign)
  │     │     ├── make dmg               (dmgbuild → dist/Greeting-Cards-X.Y.Z.dmg)
  │     │     └── scripts.notarize       (notarytool submit → staple)
  │     └── scripts.release checksum     (SHA256 → dist/Greeting-Cards-X.Y.Z.sha256)
  ├── scripts.release changelog          (extract → _build/release/release-notes.md)
  └── scripts.release draft              (gh release create --draft)
```

---

## Entitlements

`packaging/entitlements.plist` grants three entitlements required for Python/PyInstaller hardened runtime:

| Entitlement                                              | Why                                                     |
|----------------------------------------------------------|---------------------------------------------------------|
| `com.apple.security.cs.allow-unsigned-executable-memory` | Python `mmap` with executable pages                     |
| `com.apple.security.cs.disable-library-validation`       | Bundled third-party `.so` files not signed by Apple      |
| `com.apple.security.cs.allow-jit`                        | ctypes/cffi in C extensions (wxPython, tesserocr, etc.) |

---

## Inside-Out Signing (`scripts/sign/`)

Code signing must proceed from innermost binaries outward so that outer signatures cover already-signed inner content.

### Tier Classification

| Tier | Files                      | Signed |
|------|----------------------------|--------|
| 0    | `.so` and `.dylib` files    | First  |
| 1    | Framework binaries          | Second |
| 2    | Main executable + `.app`    | Last   |

### Mach-O Detection

Binaries are identified by their 4-byte magic number (not file extension), supporting:
- 32-bit and 64-bit Mach-O (both endiannesses)
- Universal (fat) binaries

### Signing Command

Each binary is signed with:
```
codesign --force --options runtime --timestamp --entitlements packaging/entitlements.plist --sign IDENTITY <path>
```

After all binaries: the `.app` bundle itself is signed, then verified with `codesign --verify --deep --strict`.

### CLI

```bash
uv run python -m scripts.sign                    # uses $CODESIGN_IDENTITY
uv run python -m scripts.sign --identity "-"     # ad-hoc signing (testing)
uv run python -m scripts.sign --dry-run          # print commands only
uv run python -m scripts.sign --verbose          # print each command as it runs
```

---

## Notarization (`scripts/notarize/`)

Submits the signed DMG to Apple's notary service, waits for approval, and staples the ticket.

### Process

1. `xcrun notarytool submit <dmg> --keychain-profile <profile> --wait`
2. On failure: fetches the notarization log via `xcrun notarytool log` and prints reasons
3. On success: `xcrun stapler staple` on both `.app` and `.dmg`
4. Verification: `spctl --assess --type execute --verbose` on the `.app`

### One-Time Credential Setup

Store notarization credentials in the keychain (run once):
```bash
xcrun notarytool store-credentials GreetingCards \
  --apple-id your@email.com \
  --team-id TEAMID \
  --password app-specific-password
```

### CLI

```bash
uv run python -m scripts.notarize                              # default profile
uv run python -m scripts.notarize --keychain-profile MyProfile # custom profile
uv run python -m scripts.notarize --dry-run                    # print commands only
```

---

## Release Automation (`scripts/release/`)

Four subcommands for changelog extraction, checksums, and GitHub Release management.

### Changelog Extraction

Parses `CHANGELOG.md` for the heading `## X.Y.Z` and extracts the body until the next `## ` heading. The version heading itself is omitted (GitHub Release title already has it). Output: `_build/release/release-notes.md`.

### Checksum

Generates `dist/Greeting-Cards-X.Y.Z.sha256` containing `sha256hash  filename` (BSD format, two-space separator).

### GitHub Release

Uses `gh release create` with `--draft` to create a draft release containing the DMG and checksum file. `gh release edit --draft=false` publishes it.

### CLI

```bash
uv run python -m scripts.release changelog   # extract release notes
uv run python -m scripts.release checksum    # SHA256 checksum
uv run python -m scripts.release draft       # draft GitHub release
uv run python -m scripts.release publish     # publish the draft
```

---

## Makefile Targets

| Target           | Description                                              |
|------------------|----------------------------------------------------------|
| `make sign`      | Build app + sign (requires `$CODESIGN_IDENTITY`)         |
| `make notarize`  | Sign + DMG + notarize (requires Apple Developer creds)   |
| `make release`   | Full pipeline: sign → DMG → notarize → checksum          |
| `make release-draft` | Full pipeline + extract changelog + create draft release |
| `make release-publish` | Publish the latest draft release                     |

---

## UPX Disabled

UPX compression is disabled in both `packaging/Greeting Cards.spec` and `packaging/Visual Test.spec` (`upx=False`). UPX-compressed binaries have invalid code signatures since the compression modifies the binary content after signing. The size savings are negligible compared to DMG bzip2 compression.

---

## DMG Filename

The DMG output filename uses hyphens (`Greeting-Cards-X.Y.Z.dmg`) for URL-friendliness in GitHub Releases and download links. The volume name shown in Finder retains spaces (`Greeting Cards - X.Y.Z`).

---

## What Works Without Apple Developer Account

Everything can be developed and tested without a certificate:

- Signing supports `--identity "-"` for ad-hoc signing and `--dry-run` for command preview
- Notarization supports `--dry-run`
- Release subcommands (changelog, checksum) work without any credentials
- All scripts have comprehensive tests with mocked `subprocess.run` calls

Actually signing and notarizing requires a Developer ID Application certificate and stored notarization credentials.

---

## Troubleshooting

| Problem                                    | Cause                                       | Fix                                                              |
|--------------------------------------------|---------------------------------------------|------------------------------------------------------------------|
| `errSecInternalComponent` during signing    | Keychain locked or cert not found            | Unlock keychain; verify cert in Keychain Access                  |
| Notarization "invalid signature"            | Binary not signed or UPX compressed          | Check `upx=False` in spec; re-run `make sign`                    |
| Notarization "The signature is invalid"     | Inner binary unsigned                        | Inside-out signing missed a file; check `find_binaries()`        |
| Notarization "hardened runtime not enabled" | Missing `--options runtime`                  | Verify `sign_binary()` includes `--options runtime`              |
| `spctl` rejects after stapling             | Ticket not stapled or wrong bundle           | Re-run `xcrun stapler staple` on both `.app` and `.dmg`          |
| "app is damaged" on user's machine          | Not notarized or quarantine attr set          | Notarize properly; user can remove quarantine with `xattr -cr`   |
| `gh: command not found`                     | GitHub CLI not installed                     | `brew install gh` and `gh auth login`                            |
