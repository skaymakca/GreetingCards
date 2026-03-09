# GreetingCards — Private Local Files

This repo tracks machine-specific artifacts from the [GreetingCards](https://github.com/skaymakca/GreetingCards) project that are gitignored in the main (public) repo.

Synced via `make sync-private` from the main project directory.

## What's here

| Directory / File                        | Contents                                      |
|-----------------------------------------|-----------------------------------------------|
| `.local/TODO.md`                        | Personal notes                                |
| `.local/comms_research_etc/`            | Correspondence, support cases                 |
| `.local/gh_issues/`                     | Issue tracking notes                          |
| `_build/audit/*.md`                     | Code quality audit reports                    |
| `_build/coverage/*/`                    | Full coverage runs (HTML, lcov, analysis MDs) |
| `_build/release/release-notes.md`       | Release notes                                 |
| `_build/release/submission-id.txt`      | Notarization submission ID                    |
| `_build/script_output/*-profiling/`     | Profiling runs (HTML + JSON + TSV)            |
| `_build/script_output/census_names/`    | Derived census name data                      |
| `.claude/settings.local.json`           | Claude Code permissions + MCP config          |
| `release-local.sh`                      | Machine-specific signing credentials          |

## What's excluded

- `_build/release/*.dmg` — large binaries, not worth versioning
- `_build/coverage/latest` — symlink, only valid inside the main repo
- `_build/script_output/*-generate_sample_cards/` — regenerable PDFs
- `_build/script_output/*-diagnostic_cards/` — regenerable PDFs
- `_build/{pyinstaller_build,dmg,script_cache,runtime_content,licenses}/` — build artifacts
- `.claude/memory/`, `.claude/worktrees/` — session-specific
- `dist/`, `.venv/`, `app/`, `tests/`, `scripts/`, `content/` — in the public repo

## Important

**This repo MUST stay private.** It contains `release-local.sh` with signing credentials and other machine-specific secrets.
