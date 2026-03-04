# Pre-Release Checklist

Step-by-step checklist for preparing and publishing a release. Work through each phase in order; every item should be checked before moving to the next phase.

**Related:** [`docs/architecture/release-pipeline.md`](docs/architecture/release-pipeline.md) for pipeline internals and troubleshooting.

---

## Phase 1: Code Quality

- [ ] `make check` — 0 errors (pyright + mypy + ruff lint + ruff format + bandit)
- [ ] `make test-everything` — all tests pass (including integration)
- [ ] `make docker-test` — cross-platform tests pass on Linux
- [ ] PyCharm inspections (if MCP available) — 0 errors/warnings

## Phase 2: Version & Changelog

- [ ] Version bumped in `pyproject.toml` (`make bump-patch`, `make bump-minor`, or `make bump-major`)
- [ ] `CHANGELOG.md` has entry for the new version with correct format (`## X.Y.Z — Title (Date)`)
- [ ] Version in `CHANGELOG.md` matches `pyproject.toml` (verify with `make version`)
- [ ] Release date is correct (not a placeholder)

## Phase 3: User-Facing Documentation

- [ ] `README.md` test count matches actual pytest output (search for "tests** covering")
- [ ] `README.md` Make commands table is current (no stale or missing targets)
- [ ] Help pages (`content/html/help/*.md`) reflect current features; numbering contiguous 1..N
- [ ] Architecture docs updated if code changes altered documented behavior (see CLAUDE.md table)

## Phase 4: Content & Licenses

- [ ] `make licenses-sync` if dependencies changed (check `uv.lock` diff)
- [ ] `make content` succeeds with no warnings
- [ ] `content/licenses/config.toml` has entries for any new bundled dependencies

## Phase 5: Git & GitHub

- [ ] Working tree clean (`git status`)
- [ ] Branch up to date with `main` (rebase or merge)
- [ ] CI checks green on the PR
- [ ] PR description summarizes user-facing changes
- [ ] Commit messages reference issue numbers (`Fixes #N`) where applicable

## Phase 6: Merge, Tag & Build

- [ ] Merge PR to `main`
- [ ] `make tag` — creates `vX.Y.Z` locally
- [ ] `make tag-push` — pushes tag to origin
- [ ] `make configure-release` — ensure `release-local.sh` exists (one-time setup)
- [ ] `./release-local.sh build-draft` — full pipeline: build, sign, DMG, submit, staple, checksum, changelog, appcast, draft

## Phase 7: Notarization (Async)

- [ ] `./release-local.sh status` — poll until "Accepted" (typically 5-30 min)
- [ ] `./release-local.sh log` — check for warnings if needed
- [ ] `./release-local.sh staple` — staple ticket to `.app` and `.dmg`, verify with `spctl`

## Phase 8: Publish & Post-Release

- [ ] Review draft release on GitHub (title, notes, assets)
- [ ] `./release-local.sh publish` — publish the draft
- [ ] `./release-local.sh appcastpush` — push appcast.xml to gh-pages (after publish, so DMG URL is live)
- [ ] Verify download link works
- [ ] Verify app launches from DMG on a clean machine (quarantine/Gatekeeper check)
- [ ] Optionally bump version for next dev cycle (`make bump-patch`)
