# TODO

- [ ] Open dialog doesnt work quite correctly. Cannot choose a folder vs open it, which is the behavior seen in other apps.  Also looks off? What were our open dialog options again?
- [ ] Dark mode detection and handling of ui changes
- [ ] Check what happens when tesseract not in path.  Investigate options from either bundling the app (is license OK?) vs globally erroring out vs not getting candidates made and giving an error popup with instructions to donwload via homebrew or a link to the tessearct website.
- [ ] Redo the name of the rebuild DB label to better represent everything being reset.
- [ ] Add a menu item in file to clear the AI results (but not manual settings and OCR)


## Done
- [x] AI Analyze scoped to visible/selected cards: unified single-card and batch paths, dynamic menu labels ("Visible (N)" / "Selected (N)"), static toolbar tooltip, API key cancel fix, code quality audit fixes (949 tests)
- [x] File menu: AI Analyze All (Cmd+Shift+I), Rename Files (Cmd+R), Clear All with icons and EVT_UPDATE_UI state sync
- [x] Confidence legend: colored hover popup replacing plain-text tooltip (native tooltips can't show colors)
- [x] Card in result table that changes its category due to AI analyze isnt triggering a recount and disppearance from teh current view.  Editing the cards or manually selecting an AI candiate results in teh corerct behavior but AI analyze (eihter singly or all of them) does not.
- [x] Multiselect in cards table with Shift+Up/Down, Cmd+A/Cmd+Shift+A, detail panel clears on multi-select, context menu adapts (Open N Cards / Remove N Cards, no Reveal), shared `_build_context_menu` constructor
- [x] Code quality: extract magic constants to `Layout.*` in styles.py, fix unused import, hardcoded color, lambda list-comp side effects, redundant branches, silent ValueError, missing return type annotations (950 tests)
- [x] Post-rename selective removal: only remove successfully renamed paths from cards, keep failed/skipped cards visible, show drop overlay only when all cards are gone
- [x] Help navbar items pinned during scroll, right div scrollable, search results JS compatible
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
