# TODO

## Completed ✅

- [x] Fix preview not matching sort order after filename sorting
- [x] Remove Process button and auto-process on folder load
- [x] Fix multiprocessing for app bundle
- [x] Add File menu with Open (⌘O), Close Window (⌘W), Quit (⌘Q)
- [x] Change main window title to "Greeting Cards"

## High Priority

### Core
- [x] Better candidates handling
  - Create a seperate table or tables for the "raw" OCR and AI results to ensure updated code w/o schema changes gets new processing updates, link with proper foreign keys and constraints
  - Create a seperate table candidates, linked with foreign keys, and store each candidate's family_name, method and confidence. Populate the dropdown in a sort with highest confidence at top
  - Update the indicator tooltip to have $METHOD - $CONFIDENCE or just "Manual Entry" for those types
  - The main file_names should be renamed to cards and store the current family_name and a reference to the candidates table if it is an OCR/AI result instead of duplicating the source and confidence fields from the other table.  Probably could be if the family_name is filled in it's manual.  If the candidate reference is filled and no family_name set, use that candidate and if neither is present the file doesnt have a name yet.  Flag this as missing in the rename window as status and skip these from renaming.  Turn indicator for missing in the indicator icon for the main card views as a red X or stop sign or other warning symbol.
- [x] Smart Title Case (Like O'Brian) as part of processing after raw_ai and raw_ocr when creating alternates
- [x] Make sure raw_ai results actually populated
- [x] When files loaded for each file if alternates exist, be sure to clear them to get the "new"/"current code" ocr->candidates ai->candidates processing is used.  To ensure a selected alternate remains, if the cards table has a reference to it, prevent that row from deleted.  When the processing happens again make sure that we arent duplicating, ie dont insert second copy of the same alternate.
- [x] When DB refresh/schema change detected, drop all the tables to make sure old tables go away.
- [ ] Check for dupes that are only different by case sensitivity Macintosh vs MacIntosh shouldn't trigger a dupe and (x) appending

### UI/UX Improvements
- [ ] Add Help > About menu with version number and git commit hash

### Name Extraction
- [x] Add "Remove Family" option to candidates as checkmark.
  - Persist in the db
  - In this case the file name is just "Holiday Cards - $RESULT.pdf"

### Error Handling
- [ ] Handle PDFs that can't be opened (corrupted/encrypted/wrongformat)
  - Show error icon/message in cards list
  - Indicate in preview pane with a centered message and bad file icon
- [ ] Review file permissions issues and handle
- [ ] Review API issues and handle - seperate handling for auth issues (reprompt) and network/other/load issues (stop)

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
