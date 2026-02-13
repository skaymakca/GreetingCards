# TODO

## High Priority

## Medium Priority

### App Bundle Issues
- [ ] Debug button UI glitches in .app bundle (gray areas around buttons)
  - Possibly SF Symbols not loading in bundle
  - May need to bundle PyObjC frameworks

## Future / Research

### wxPython Port
- [ ] Create `wx` branch and port GUI to wxPython
  - Keep `app/core/` identical
  - Rewrite `app/gui/` with wxPython
  - Compare performance and code size
  - Use native widgets (DataViewListCtrl for cards table)

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
- [x] Handle bad/unreadable PDFs gracefully (error icon, disabled controls, error in preview)
- [x] Structured error handling for file rename (results table with success/error state)
- [x] AI error handling: auth abort, error collection, ErrorListDialog, clean messages
- [x] Semantic versioning (`app/version.py`, Makefile bump targets, PyInstaller bundle metadata)
- [x] About section in Settings with app icon, version, and git commit hash

---

## Contributing

When working on a task:
1. Create a branch if it's a large feature
2. Update this file to mark task as in progress (move to "In Progress" section)
3. Mark as completed with `[x]` when done
4. Include "Fixes #X" in commit message if closing an issue
