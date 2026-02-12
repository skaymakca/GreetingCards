# TODO

## Completed ✅

- [x] Fix preview not matching sort order after filename sorting
- [x] Remove Process button and auto-process on folder load
- [x] Fix multiprocessing for app bundle
- [x] Add File menu with Open (⌘O), Close Window (⌘W), Quit (⌘Q)
- [x] Change main window title to "Greeting Cards"

## High Priority

### UI/UX Improvements
- [ ] Add Help > About menu with version number and git commit hash

### Name Extraction
- [ ] Add "Remove Family" option to candidates as checkmark.  
  - Persist in the db
  - In this case the file name is just "Holiday Cards - $RESULT.pdf"

### Error Handling
- [ ] Handle PDFs that can't be opened (corrupted/encrypted)
  - Show error icon/message in cards list
  - Don't crash on bad PDFs
- [ ] Review file permissions issues and handle
- [ ] Review API issues and handle

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
