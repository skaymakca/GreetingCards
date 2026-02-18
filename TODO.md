# TODO

- [ ] Redo the help menu to have just the default macos help item open our help screen, remove teh button on main
- [ ] Save zoom/pan states while browsing with sane defaults for resetting


## Test Coverage Gaps

### Core Modules
- [x] `app/core/database.py` — persistence layer, schema management
- [x] `app/core/ai_analyzer.py` — AI analysis with Anthropic API
- [x] `app/core/name_extractor.py` — name extraction pipeline
- [x] `app/core/ocr_engine.py` — OCR processing
- [x] `app/core/pdf_renderer.py` — PDF rendering
- [x] `app/core/config.py` — configuration management
- [x] `app/core/paths.py` — path utilities

### Models
- [x] `app/models/card.py` — card data model

### GUI Modules
- [x] `app/gui/api_key_dialog.py`
- [x] `app/gui/help_dialog.py`
- [x] `app/gui/settings_dialog.py`
- [x] `app/gui/styles.py`

## Cleanup
- [x] Delete `.wxmigration` file (migration complete)
- [x] Audit `docs/architecture/` for post-migration accuracy — all 5 docs are accurate
