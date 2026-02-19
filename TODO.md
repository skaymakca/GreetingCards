# TODO

- [ ] Update finish renaming behavior. Instead of clearing after rename: Only remove the filepaths that were succesfuly renamed.  If a card has no more paths left, remove it.  If there are no items left, then go back to the overlay drop screen
- [ ] Open dialog doesnt work quite correctly. Cannot choose a folder vs open it, which is the behavior seen in other apps.  Also looks off? What were our open dialog options again?
- [ ] Add commands to the file menu for the rest of teh toolbar buttons, AI analyze, Rename Files, Clear
- [ ] Dark mode detection and handling of ui changes
- [ ] Help navbar items should be pinned/always visible despite scrolling. Make just the right div scollable?  Woudld need to make sure the search results JS would work with this ok.  This path should let us also (hopefiully never need) a scrollable TOC as well
- [ ] Card in result table that changes its category due to editing isnt triggering a recount and disppearance from teh current view.  For example, had an error card then named it to an AI result, it still remained.

## Done
- [x] Card removal: Remove button in detail panel, right-click context menu on card rows (Open, Reveal in Finder, Remove) with SF Symbol icons
- [x] AI model selection: Settings dropdown (Haiku 4.5, Sonnet 4.6, Opus 4.6), plist persistence, stale model auto-migration, help page with cost table
- [x] Fix filter state desync bug and code quality cleanup
- [x] Fix 4 UI polish issues at first load
- [x] Flatten help directory and clean up Makefile
- [x] Fix API key dialog not saving and clean up settings code
- [x] Content-area drop overlay with background image and drag highlight on card table
- [x] Equal column sizing for review/preview panels at initial load
- [x] Preview controls layout cleanup (page nav left-aligned, zoom right-aligned)
- [x] Dialog table status column sizing fix and magic number cleanup (named constants)
- [x] Makefile: `lsregister -u` before build/clean to prevent "extensions in use" error
- [x] Bug fixes: AddPage return value, format_ai_error check order, candidate_id truthiness, UnboundLocalError in sequential processing
- [x] Code quality: paint highlight ordering, model public accessors, ProgressDialog native bg, deduplicated pil_to_bitmap and hex_to_colour
- [x] Typing fixes: Optional→X|None in card.py/utils.py, callable→Callable, on_select type, event handler params
- [x] Test gaps filled: format_ai_error timeout, card navigation, reprocess with OCR+AI (804 tests)
- [x] Help system: WebView viewer with 7 HTML pages, cross-page search with JS highlighting, architecture doc
- [x] Native macOS Preferences via `wx.PreferencesEditor` (Cmd+, / app menu)
- [x] Removed toolbar settings button (access via menu only)
- [x] Non-GUI test coverage boosted from 92% to 99% (753 tests, 0 warnings)
- [x] Suppressed wxPython SWIG and SQLAlchemy coverage warnings in pytest.ini
- [x] Delete `.wxmigration` file (migration complete)
- [x] Audit `docs/architecture/` for post-migration accuracy — all 5 docs are accurate
