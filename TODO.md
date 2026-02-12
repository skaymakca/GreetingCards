# TODO

## Completed ✅

- [x] Fix preview not matching sort order after filename sorting
- [x] Remove Process button and auto-process on folder load
- [x] Fix multiprocessing for app bundle

## High Priority

### UI/UX Improvements
- [ ] Add "Open..." to File menu with ⌘O keyboard shortcut
- [ ] Change main window title (currently "Greeting Card Analyzer")
- [ ] Add Help > About menu with version number and git commit hash

### Name Extraction
- [ ] Add "Remove Family" option to candidates dropdown
  - If name is "Smith Family", add "Smith" as a candidate
  - If name is "Family Smith", add "Smith" as a candidate

### Error Handling
- [ ] Handle PDFs that can't be opened (corrupted/encrypted)
  - Show error icon/message in cards list
  - Don't crash on bad PDFs

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

## Contributing

When working on a task:
1. Create a branch if it's a large feature
2. Update this file to mark task as in progress (move to "In Progress" section)
3. Mark as completed with `[x]` when done
4. Include "Fixes #X" in commit message if closing an issue
