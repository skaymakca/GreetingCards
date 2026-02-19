# TODO

- [ ] Handle removing cards from the cards table.
	- Will need to add a button to the details editor.  A remove button with an icon right next to the AI Analyze and before the remove family name checkbox
	- Will need to add a right click menu in the main table's row, with Open (use the default system mechanism), Reveal in finder (open window with the file selected) and remove.  Include appropriate icons (and consistent with the new button for the remove command)
- [ ] Update finish renaming behavior. Instead of clearing after rename: Only remove the filepaths that were succesfuly renamed.  If a card has no more paths left, remove it.  If there are no items left, then go back to the overlay drop screen
## Done
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
