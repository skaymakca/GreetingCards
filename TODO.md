# TODO

## High Priority
- [ ] Icons look terrible
- [ ] Mac Info.app style help menus
- [ ] **Manual test: filter auto-reset behavior** — Load cards from 2+ folders, test these scenarios:
  - Select "High Confidence", edit last high card's name → card disappears, filter resets to "All Cards", all cards shown
  - Select "Manual Entry", pick a candidate → filter resets to "All Cards"
  - Search "xyz" (no match) → shows 0 cards, checkboxes NOT reset, search preserved
  - Select folder + category combo that yields 0 → auto-resets checkboxes, cards appear
  - Verify no stale/duplicate table states (re-entrancy bug was here)

## Medium Priority
- [ ] Autogenerate screenshots for help system?
- [ ] Create architecture/notes subdocs for subsystems (reduce LLM context window usage)
- [ ] Preview panel: Add help button/info icon showing keyboard/mouse shortcuts

---

## Completed ✅

- [x] Fix preview not matching sort order after filename sorting
- [x] Remove Process button and auto-process on folder load
- [x] Fix multiprocessing for app bundle
- [x] Add File menu with Open (⌘O), Close Window (⌘W), Quit (⌘Q)
- [x] Change main window title to "Greeting Cards"
- [x] Candidates system: raw OCR/AI tables, candidates table with method/confidence, dropdown sorted by confidence, indicator tooltips
- [x] Smart title case for family names (O'Brien, etc.)
- [x] Reprocess candidates from raw data on load, dedup, preserve selected candidate
- [x] Auto-drop and rebuild DB on schema change
- [x] "Remove Family" suffix option per card, persisted in DB
- [x] Fix case-insensitive duplicate detection for rename
- [x] Fix duplicate numbering when source files already have correct numbered names (multiple Walsh problem)
- [x] Handle bad/unreadable PDFs gracefully (error icon, disabled controls, error in preview)
- [x] Structured error handling for file rename (results table with success/error state)
- [x] AI error handling: auth abort, error collection, ErrorListDialog, clean messages
- [x] Semantic versioning (`app/version.py`, Makefile bump targets, PyInstaller bundle metadata)
- [x] About section in Settings with app icon, version, and git commit hash
- [x] Fix app bundle UI glitches: refactor tk widgets to ttk for native macOS backgrounds
- [x] Search filtering: search → category counts → category filter → cards table. Zero-count filters disabled. Finder-style clicks (regular=exclusive, Option=multi-select).
- [x] Dynamic folder filters with cross-filtered counts in sidebar
- [x] Fix re-entrant `_refresh_display()` and auto-reset empty filters

---

## Contributing

When working on a task:
1. Create a branch if it's a large feature
2. Update this file to mark task as in progress (move to "In Progress" section)
3. Mark as completed with `[x]` when done
4. Include "Fixes #X" in commit message if closing an issue
