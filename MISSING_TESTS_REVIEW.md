# Missing Test Coverage Review

## Summary
Review of cursor and preview panel code to identify gaps in test coverage after implementing custom SF Symbol cursors.

---

## 1. Custom Cursor Functionality (NEW - No Tests Yet)

### `wx_icons.py` - `load_cursor_from_symbol()`

**Priority: HIGH** - This is a brand new feature with zero test coverage.

#### Basic Functionality Tests
- [ ] **test_load_cursor_from_symbol_returns_cursor**
  - Load valid SF Symbol as cursor
  - Assert returns wx.Cursor object
  - Assert cursor is not None

- [ ] **test_load_cursor_invalid_symbol_returns_none**
  - Load invalid/nonexistent symbol name
  - Assert returns None (graceful fallback)

- [ ] **test_load_cursor_with_default_hotspot**
  - Load cursor without explicit hotspot
  - Verify hotspot defaults to center (width//2, height//2)
  - Note: May need to check wx.Image options before conversion

- [ ] **test_load_cursor_with_custom_hotspot**
  - Load cursor with explicit hotspot_x, hotspot_y
  - Verify custom hotspot is set correctly
  - Test edge cases (0,0), (max,max)

- [ ] **test_load_cursor_different_sizes**
  - Load cursor at 6pt, 7pt, 12pt, 20pt
  - Verify cursors have different dimensions
  - Verify all are valid wx.Cursor objects

- [ ] **test_load_cursor_different_colors**
  - Load cursor in black (#000000), white (#FFFFFF), red (#FF0000)
  - Verify all cursors load successfully
  - Note: Visual appearance not tested, just loading

#### Error Handling Tests
- [ ] **test_load_cursor_pyobjc_unavailable**
  - Mock ImportError from AppKit
  - Verify returns None gracefully
  - Verify prints warning message

- [ ] **test_load_cursor_nsimage_returns_none**
  - Mock NSImage.imageWithSystemSymbolName returning None
  - Verify function returns None

- [ ] **test_load_cursor_zero_dimensions**
  - Mock styled image with 0 width or height
  - Verify returns None

- [ ] **test_load_cursor_png_conversion_fails**
  - Mock PNG data conversion returning None
  - Verify returns None

- [ ] **test_load_cursor_wx_image_not_ok**
  - Mock wx.Image.IsOk() returning False
  - Verify returns None

#### Integration Tests
- [ ] **test_cursor_can_be_set_on_panel**
  - Load cursor from symbol
  - Create wx.Panel
  - Call panel.SetCursor(cursor)
  - Verify no crashes

- [ ] **test_cursor_survives_panel_operations**
  - Set cursor on panel
  - Trigger layout, resize, etc.
  - Verify cursor still valid

---

## 2. Preview Panel Cursor Behavior

### `wx_preview_panel.py` - Cursor Management

**Priority: HIGH** - Critical user-facing feature with no direct tests.

#### Cursor State Tests
- [ ] **test_custom_cursors_loaded_on_init**
  - Create PreviewPanel
  - Assert _zoom_in_cursor is not None
  - Assert _zoom_out_cursor is not None
  - Verify they are wx.Cursor instances

- [ ] **test_cursor_fallback_when_sf_symbols_unavailable**
  - Mock load_cursor_from_symbol to return None
  - Create PreviewPanel
  - Assert cursors fall back to wx.CURSOR_MAGNIFIER
  - Verify no crashes

- [ ] **test_cursor_fallback_on_import_error**
  - Mock import error for wx_icons
  - Create PreviewPanel
  - Assert cursors fall back to wx.CURSOR_MAGNIFIER

#### Cursor Update Tests
- [ ] **test_update_cursor_shift_sets_zoom_in**
  - Load images in preview panel
  - Mock wx.GetMouseState() with MOD_SHIFT
  - Call _update_cursor()
  - Verify canvas cursor set to _zoom_in_cursor

- [ ] **test_update_cursor_alt_sets_zoom_out**
  - Load images in preview panel
  - Mock wx.GetMouseState() with MOD_ALT
  - Call _update_cursor()
  - Verify canvas cursor set to _zoom_out_cursor

- [ ] **test_update_cursor_no_modifiers_clears**
  - Load images in preview panel
  - Mock wx.GetMouseState() with no modifiers
  - Call _update_cursor()
  - Verify canvas cursor set to wx.NullCursor

- [ ] **test_update_cursor_both_modifiers_clears**
  - Load images in preview panel
  - Mock wx.GetMouseState() with MOD_SHIFT | MOD_ALT
  - Call _update_cursor()
  - Verify canvas cursor set to wx.NullCursor (ambiguous state)

- [ ] **test_update_cursor_skips_when_no_images**
  - Clear preview panel
  - Call _update_cursor()
  - Verify no cursor changes (no crash)

- [ ] **test_update_cursor_skips_during_drag**
  - Load images
  - Set _drag_start to simulate panning
  - Call _update_cursor()
  - Verify cursor not changed (drag cursor takes priority)

#### Event Handler Tests
- [ ] **test_on_enter_starts_modifier_timer**
  - Load images
  - Simulate EVT_ENTER_WINDOW
  - Assert _modifier_timer is running

- [ ] **test_on_leave_stops_modifier_timer**
  - Load images, start timer
  - Simulate EVT_LEAVE_WINDOW
  - Assert _modifier_timer is stopped

- [ ] **test_on_modifier_timer_calls_update_cursor**
  - Load images
  - Mock _update_cursor
  - Trigger timer event
  - Assert _update_cursor was called

---

## 3. Mouse Event Interactions

### `wx_preview_panel.py` - Mouse Events

**Priority: MEDIUM** - Existing behavior, but new cursor interactions.

#### Modifier Click Tests
- [ ] **test_left_click_with_shift_zooms_in**
  - Load images
  - Simulate left click with MOD_SHIFT
  - Assert zoom increased by ZOOM_STEP
  - Verify _is_fit is False

- [ ] **test_left_click_with_alt_zooms_out**
  - Load images
  - Simulate left click with MOD_ALT
  - Assert zoom decreased by 1/ZOOM_STEP
  - Verify _is_fit is False

- [ ] **test_left_click_no_modifier_starts_pan**
  - Load images
  - Simulate left click with no modifiers
  - Assert _drag_start is set
  - Assert cursor changed to CURSOR_SIZING

- [ ] **test_left_click_both_modifiers_starts_pan**
  - Load images
  - Simulate left click with MOD_SHIFT | MOD_ALT
  - Assert _drag_start is set (ambiguous zoom = pan)

- [ ] **test_double_click_with_shift_zooms_twice**
  - Load images
  - Simulate left double-click with MOD_SHIFT
  - Verify zoom applied twice (double-click handled)

- [ ] **test_modifier_timer_restarts_after_click**
  - Load images, start timer
  - Simulate modifier click
  - Assert timer stops during click
  - Assert timer restarts after click

#### Pan Event Tests
- [ ] **test_on_motion_updates_cursor_when_not_panning**
  - Load images
  - Simulate mouse motion with no drag
  - Verify _update_cursor called

- [ ] **test_on_motion_pans_during_drag**
  - Load images, start pan
  - Simulate mouse motion during drag
  - Verify _pan_x, _pan_y updated

- [ ] **test_on_pan_end_clears_drag_state**
  - Load images, start pan
  - Simulate EVT_LEFT_UP
  - Assert _drag_start is None
  - Assert cursor reset to NullCursor

#### Scroll Zoom Tests
- [ ] **test_scroll_up_zooms_in**
  - Load images
  - Simulate scroll wheel up (positive rotation)
  - Assert zoom increased

- [ ] **test_scroll_down_zooms_out**
  - Load images
  - Simulate scroll wheel down (negative rotation)
  - Assert zoom decreased

- [ ] **test_scroll_with_no_images_no_crash**
  - Clear preview panel
  - Simulate scroll wheel
  - Verify no crashes

---

## 4. Additional wx_icons.py Coverage

### Missing Wrapper Function Tests

**Priority: LOW** - Simple wrappers, but should have basic coverage.

- [ ] **test_load_menu_icon_calls_load_sf_symbol**
  - Call load_menu_icon("scissors")
  - Verify calls load_sf_symbol with point_size=6, scale=1

- [ ] **test_load_menu_icon_returns_bitmap**
  - Call load_menu_icon("scissors")
  - Assert returns wx.Bitmap or None

### _hex_to_rgb() Tests

**Priority: LOW** - Simple utility, but untested.

- [ ] **test_hex_to_rgb_black**
  - Convert "#000000"
  - Assert (0.0, 0.0, 0.0)

- [ ] **test_hex_to_rgb_white**
  - Convert "#FFFFFF"
  - Assert (1.0, 1.0, 1.0)

- [ ] **test_hex_to_rgb_half**
  - Convert "#808080"
  - Assert approximately (0.502, 0.502, 0.502)

- [ ] **test_hex_to_rgb_colors**
  - Convert "#FF0000" (red), "#00FF00" (green), "#0000FF" (blue)
  - Verify correct RGB tuples

---

## 5. Edge Cases and Robustness

### Preview Panel Edge Cases

**Priority: LOW** - Unlikely scenarios, but good for robustness.

- [ ] **test_rapid_page_changes**
  - Load multi-page document
  - Rapidly call _next_page(), _prev_page()
  - Verify no crashes, state consistent

- [ ] **test_zoom_at_extreme_limits**
  - Zoom to MAX_ZOOM (10.0)
  - Attempt to zoom in more
  - Verify clamped at MAX_ZOOM

- [ ] **test_pan_with_very_large_offsets**
  - Set _pan_x, _pan_y to 10000
  - Render
  - Verify no crashes

- [ ] **test_show_images_while_panning**
  - Start pan operation
  - Call show_images() mid-pan
  - Verify pan state reset, no crashes

- [ ] **test_clear_while_modifier_timer_running**
  - Load images, start timer
  - Call clear()
  - Verify timer continues or stops gracefully

- [ ] **test_show_error_while_panning**
  - Start pan operation
  - Call show_error()
  - Verify pan state cleared

---

## 6. Suggested Test Organization

### New Test Files to Create

1. **`tests/gui/test_wx_cursors.py`** (HIGH PRIORITY)
   - All `load_cursor_from_symbol()` tests
   - Cursor loading, hotspot, fallback
   - Integration with wx.Panel

2. **`tests/gui/test_wx_preview_cursor_behavior.py`** (HIGH PRIORITY)
   - Cursor state management in PreviewPanel
   - Modifier key detection
   - Timer behavior
   - Event handler coordination

3. **Update `tests/gui/test_wx_preview_panel.py`** (MEDIUM PRIORITY)
   - Add modifier click tests
   - Add scroll zoom tests
   - Add edge case tests

4. **Update `tests/gui/test_wx_icons.py`** (LOW PRIORITY)
   - Add _hex_to_rgb tests
   - Add load_menu_icon tests

---

## 7. Testing Challenges & Notes

### Known Limitations

1. **Cursor Appearance**: Can't easily test visual appearance of cursors (would need screenshot comparison)
2. **Hotspot Accuracy**: Hard to verify hotspot position without actual click testing
3. **Modifier Keys**: Mocking wx.GetMouseState() may be tricky
4. **Timer Behavior**: Need to be careful with wx.Timer in tests (may need wx.CallAfter)
5. **PyObjC Mocking**: Mocking AppKit imports is complex, may need fixtures

### Testing Strategy

- **Unit Tests**: Test individual functions in isolation
- **Integration Tests**: Test cursor + panel interaction
- **Structural Tests**: Verify objects exist and have correct types (not pixel-perfect)
- **Mock Appropriately**: Mock external dependencies (PyObjC, wx.GetMouseState)
- **Avoid Flakiness**: Use deterministic tests, avoid timing-dependent tests where possible

---

## 8. Priority Ranking

### Must Have (Before Merge/Release)
1. Basic cursor loading tests (load_cursor_from_symbol)
2. Cursor fallback mechanism tests
3. Modifier key detection tests
4. Timer start/stop tests

### Should Have (For Solid Coverage)
1. Hotspot positioning tests
2. Modifier click zoom tests
3. Cursor state during pan tests
4. Error handling tests

### Nice to Have (For Comprehensive Coverage)
1. Edge case tests (rapid clicks, extreme values)
2. _hex_to_rgb tests
3. load_menu_icon wrapper tests
4. Integration tests with real mouse events

---

## 9. Estimated Effort

- **High Priority Tests (Cursors)**: ~2-3 hours
- **Medium Priority Tests (Mouse Events)**: ~1-2 hours
- **Low Priority Tests (Edge Cases)**: ~1 hour
- **Total**: ~4-6 hours for comprehensive coverage

---

## 10. Next Steps

1. Review this document with team/user
2. Prioritize which tests to implement
3. Create test files (start with `test_wx_cursors.py`)
4. Implement high-priority tests first
5. Run coverage report to verify improvements
6. Add remaining tests iteratively

---

**Generated**: 2026-02-13
**Context**: After implementing custom SF Symbol cursors (7pt) for preview panel zoom functionality
