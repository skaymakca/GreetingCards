"""Tests for wxPython context menu with SF Symbol icons."""

from unittest.mock import MagicMock, patch

import pytest
import wx

from app.gui.context_menu import _clear, _title_case, add_entry_context_menu


class TestContextMenuSetup:
    """Tests for context menu setup and binding."""

    def test_add_context_menu_binds_event(self, wx_frame):
        """Should bind context menu event to TextCtrl."""
        text_ctrl = wx.TextCtrl(wx_frame)

        # Initially should not have context menu icons
        assert not hasattr(text_ctrl, "_context_menu_icons")

        add_entry_context_menu(text_ctrl)

        # Should now have icons stored
        assert hasattr(text_ctrl, "_context_menu_icons")
        assert isinstance(text_ctrl._context_menu_icons, dict)

        text_ctrl.Destroy()

    def test_context_menu_loads_icons(self, wx_frame):
        """Should load SF Symbol icons for custom menu items."""
        text_ctrl = wx.TextCtrl(wx_frame)
        add_entry_context_menu(text_ctrl)

        # Should have loaded icons for custom items (title_case, clear)
        # Cut/Copy/Paste use native wx IDs and don't need custom icons
        icons = text_ctrl._context_menu_icons
        expected_keys = {"title_case", "clear"}

        # Icons dict should have the expected keys if any icons loaded
        if icons:
            for key in icons:
                assert key in expected_keys
                assert isinstance(icons[key], wx.Bitmap)
                assert icons[key].IsOk()

        text_ctrl.Destroy()


class TestClipboardOperations:
    """Tests for clipboard operations (Cut, Copy, Paste)."""

    def test_cut_with_selection(self, wx_frame):
        """Should be able to cut when text is selected."""
        text_ctrl = wx.TextCtrl(wx_frame, value="Hello World")
        text_ctrl.SetFocus()
        text_ctrl.SetSelection(0, 5)  # Select "Hello"

        # Should be able to cut with selection
        assert text_ctrl.CanCut()

        text_ctrl.Destroy()

    def test_cut_without_selection(self, wx_frame):
        """Should not be able to cut without selection."""
        text_ctrl = wx.TextCtrl(wx_frame, value="Hello World")
        text_ctrl.SetFocus()
        # No selection

        # Should not be able to cut without selection
        assert not text_ctrl.CanCut()

        text_ctrl.Destroy()

    def test_copy_with_selection(self, wx_frame):
        """Should be able to copy when text is selected."""
        text_ctrl = wx.TextCtrl(wx_frame, value="Hello World")
        text_ctrl.SetFocus()
        text_ctrl.SetSelection(0, 5)  # Select "Hello"

        # Should be able to copy with selection
        assert text_ctrl.CanCopy()

        text_ctrl.Destroy()

    def test_copy_without_selection(self, wx_frame):
        """Should not be able to copy without selection."""
        text_ctrl = wx.TextCtrl(wx_frame, value="Hello World")
        text_ctrl.SetFocus()
        # No selection

        # Should not be able to copy without selection
        assert not text_ctrl.CanCopy()

        text_ctrl.Destroy()

    def test_paste_check(self, wx_frame):
        """Should be able to check if paste is available."""
        text_ctrl = wx.TextCtrl(wx_frame, value="Hello")
        text_ctrl.SetFocus()

        # CanPaste returns bool (may vary by system clipboard state)
        can_paste = text_ctrl.CanPaste()
        assert isinstance(can_paste, bool)

        text_ctrl.Destroy()


class TestTextTransformations:
    """Tests for text transformation operations (Title Case, Clear)."""

    def test_title_case_converts_text(self, wx_frame):
        """Should convert text to Title Case."""
        text_ctrl = wx.TextCtrl(wx_frame, value="hello world")

        _title_case(text_ctrl)

        assert text_ctrl.GetValue() == "Hello World"
        text_ctrl.Destroy()

    def test_title_case_handles_mixed_case(self, wx_frame):
        """Should convert mixed case text to Title Case."""
        text_ctrl = wx.TextCtrl(wx_frame, value="hELLo WoRLd")

        _title_case(text_ctrl)

        assert text_ctrl.GetValue() == "Hello World"
        text_ctrl.Destroy()

    def test_title_case_handles_empty_text(self, wx_frame):
        """Should handle empty text gracefully."""
        text_ctrl = wx.TextCtrl(wx_frame, value="")

        _title_case(text_ctrl)

        assert text_ctrl.GetValue() == ""
        text_ctrl.Destroy()

    def test_title_case_handles_single_word(self, wx_frame):
        """Should handle single word correctly."""
        text_ctrl = wx.TextCtrl(wx_frame, value="hello")

        _title_case(text_ctrl)

        assert text_ctrl.GetValue() == "Hello"
        text_ctrl.Destroy()

    def test_clear_removes_all_text(self, wx_frame):
        """Should clear all text from field."""
        text_ctrl = wx.TextCtrl(wx_frame, value="Hello World")

        _clear(text_ctrl)

        assert text_ctrl.GetValue() == ""
        text_ctrl.Destroy()

    def test_clear_handles_empty_text(self, wx_frame):
        """Should handle already empty text gracefully."""
        text_ctrl = wx.TextCtrl(wx_frame, value="")

        _clear(text_ctrl)

        assert text_ctrl.GetValue() == ""
        text_ctrl.Destroy()


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_can_check_methods(self, wx_frame):
        """Should use CanCut, CanCopy, CanPaste for validation."""
        text_ctrl = wx.TextCtrl(wx_frame, value="Hello World")

        # Without selection, can't cut or copy
        assert not text_ctrl.CanCut()
        assert not text_ctrl.CanCopy()

        # With selection, can cut and copy
        text_ctrl.SetSelection(0, 5)
        assert text_ctrl.CanCut()
        assert text_ctrl.CanCopy()

        # Can paste if clipboard has text (may vary by system)
        # Just check it doesn't crash
        can_paste = text_ctrl.CanPaste()
        assert isinstance(can_paste, bool)

        text_ctrl.Destroy()

    def test_multiple_text_ctrls_independent(self, wx_frame):
        """Should be able to add context menus to multiple TextCtrls independently."""
        text1 = wx.TextCtrl(wx_frame, value="Field 1")
        text2 = wx.TextCtrl(wx_frame, value="Field 2")

        add_entry_context_menu(text1)
        add_entry_context_menu(text2)

        # Each should have its own icons
        assert hasattr(text1, "_context_menu_icons")
        assert hasattr(text2, "_context_menu_icons")

        # Operations on one shouldn't affect the other
        _clear(text1)
        assert text1.GetValue() == ""
        assert text2.GetValue() == "Field 2"

        text1.Destroy()
        text2.Destroy()

    def test_unicode_text_handling(self, wx_frame):
        """Should handle Unicode text correctly."""
        text_ctrl = wx.TextCtrl(wx_frame, value="こんにちは World 🎉")

        # Title case should work with Unicode
        _title_case(text_ctrl)
        # Note: title() on Unicode may behave differently
        assert text_ctrl.GetValue()  # Just check it doesn't crash

        # Clear should work with Unicode
        _clear(text_ctrl)
        assert text_ctrl.GetValue() == ""

        text_ctrl.Destroy()

    def test_very_long_text(self, wx_frame):
        """Should handle very long text without issues."""
        long_text = "hello " * 1000  # 6000 characters
        text_ctrl = wx.TextCtrl(wx_frame, value=long_text)

        # Should handle title case on long text
        _title_case(text_ctrl)
        assert text_ctrl.GetValue().startswith("Hello")

        # Should handle clear on long text
        _clear(text_ctrl)
        assert text_ctrl.GetValue() == ""

        text_ctrl.Destroy()


class TestContextMenuIntegration:
    """Level 3: Integration tests for context menu in real dialogs."""

    def test_context_menu_in_dialog(self, wx_app):
        """Should be able to add context menu to TextCtrl in a dialog."""
        dialog = wx.Dialog(None, title="Test Dialog", size=(300, 200))
        sizer = wx.BoxSizer(wx.VERTICAL)

        text_ctrl = wx.TextCtrl(dialog, value="Test text")
        add_entry_context_menu(text_ctrl)
        sizer.Add(text_ctrl, 0, wx.ALL, 10)

        dialog.SetSizer(sizer)

        # Verify the text control is functional
        assert text_ctrl.GetValue() == "Test text"
        assert hasattr(text_ctrl, "_context_menu_icons")

        # Verify context menu is bound
        text_ctrl.SetFocus()
        text_ctrl.SetSelection(0, 4)
        assert text_ctrl.CanCut()

        dialog.Destroy()

    def test_multiple_text_ctrls_in_dialog(self, wx_app):
        """Should be able to add context menus to multiple TextCtrls in same dialog."""
        dialog = wx.Dialog(None, title="Test Dialog", size=(300, 200))
        sizer = wx.BoxSizer(wx.VERTICAL)

        text1 = wx.TextCtrl(dialog, value="Field 1")
        text2 = wx.TextCtrl(dialog, value="Field 2")
        text3 = wx.TextCtrl(dialog, value="Field 3")

        add_entry_context_menu(text1)
        add_entry_context_menu(text2)
        add_entry_context_menu(text3)

        sizer.Add(text1, 0, wx.ALL, 5)
        sizer.Add(text2, 0, wx.ALL, 5)
        sizer.Add(text3, 0, wx.ALL, 5)

        dialog.SetSizer(sizer)

        # All should have context menus
        assert hasattr(text1, "_context_menu_icons")
        assert hasattr(text2, "_context_menu_icons")
        assert hasattr(text3, "_context_menu_icons")

        # Test operations on different fields
        _clear(text1)
        _title_case(text2)

        assert text1.GetValue() == ""
        assert text2.GetValue() == "Field 2"  # Title case doesn't change this
        assert text3.GetValue() == "Field 3"

        dialog.Destroy()


class TestOnContextMenu:
    """Tests for the on_context_menu handler and menu structure."""

    @staticmethod
    def _trigger_context_menu(text_ctrl):
        """Trigger context menu event and capture the menu before it is destroyed.

        Patches both PopupMenu (to intercept the menu) and Menu.Destroy (to prevent
        the C++ object from being deleted before we can inspect it).
        Returns the captured wx.Menu instance.
        """
        captured_menu = None

        def capture_menu(menu):
            nonlocal captured_menu
            captured_menu = menu

        with (
            patch.object(text_ctrl, "PopupMenu", side_effect=capture_menu),
            patch.object(wx.Menu, "Destroy"),
        ):
            event = wx.ContextMenuEvent(wx.wxEVT_CONTEXT_MENU)
            text_ctrl.ProcessEvent(event)

        assert captured_menu is not None
        return captured_menu

    def test_popup_menu_is_called_on_right_click(self, wx_frame):
        """Should call PopupMenu when the context menu event fires."""
        text_ctrl = wx.TextCtrl(wx_frame, value="Hello")
        add_entry_context_menu(text_ctrl)

        with patch.object(text_ctrl, "PopupMenu") as mock_popup:
            event = wx.ContextMenuEvent(wx.wxEVT_CONTEXT_MENU)
            text_ctrl.ProcessEvent(event)

            mock_popup.assert_called_once()

        text_ctrl.Destroy()

    def test_menu_contains_cut_copy_paste(self, wx_frame):
        """Should create menu with Cut, Copy, Paste items using native IDs."""
        text_ctrl = wx.TextCtrl(wx_frame, value="Hello")
        add_entry_context_menu(text_ctrl)

        menu = self._trigger_context_menu(text_ctrl)
        items = menu.GetMenuItems()

        # First three items should be Cut, Copy, Paste with native wx IDs
        assert items[0].GetId() == wx.ID_CUT
        assert items[0].GetItemLabelText() == "Cut"
        assert items[1].GetId() == wx.ID_COPY
        assert items[1].GetItemLabelText() == "Copy"
        assert items[2].GetId() == wx.ID_PASTE
        assert items[2].GetItemLabelText() == "Paste"

        text_ctrl.Destroy()

    def test_menu_has_separator_after_clipboard_items(self, wx_frame):
        """Should have a separator between clipboard items and custom items."""
        text_ctrl = wx.TextCtrl(wx_frame, value="Hello")
        add_entry_context_menu(text_ctrl)

        menu = self._trigger_context_menu(text_ctrl)
        items = menu.GetMenuItems()

        # Fourth item (index 3) should be a separator
        assert items[3].IsSeparator()

        text_ctrl.Destroy()

    def test_menu_contains_title_case_and_clear(self, wx_frame):
        """Should create menu with Title Case and Clear custom items after separator."""
        text_ctrl = wx.TextCtrl(wx_frame, value="Hello")
        add_entry_context_menu(text_ctrl)

        menu = self._trigger_context_menu(text_ctrl)
        items = menu.GetMenuItems()

        # Items after separator: Title Case (index 4), Clear (index 5)
        assert items[4].GetItemLabelText() == "Title Case"
        assert items[5].GetItemLabelText() == "Clear"

        text_ctrl.Destroy()

    def test_menu_has_exactly_six_items(self, wx_frame):
        """Should create menu with exactly 6 items: Cut, Copy, Paste, separator, Title Case, Clear."""
        text_ctrl = wx.TextCtrl(wx_frame, value="Hello")
        add_entry_context_menu(text_ctrl)

        menu = self._trigger_context_menu(text_ctrl)

        assert menu.GetMenuItemCount() == 6

        text_ctrl.Destroy()

    def test_title_case_menu_item_transforms_text(self, wx_frame):
        """Title Case menu item handler should transform the text field value."""
        text_ctrl = wx.TextCtrl(wx_frame, value="hello world")
        add_entry_context_menu(text_ctrl)

        menu = self._trigger_context_menu(text_ctrl)
        items = menu.GetMenuItems()

        # Simulate selecting the Title Case item
        title_item = items[4]
        menu_event = wx.CommandEvent(wx.wxEVT_MENU, title_item.GetId())
        menu.ProcessEvent(menu_event)

        assert text_ctrl.GetValue() == "Hello World"

        text_ctrl.Destroy()

    def test_clear_menu_item_clears_text(self, wx_frame):
        """Clear menu item handler should clear the text field value."""
        text_ctrl = wx.TextCtrl(wx_frame, value="some text")
        add_entry_context_menu(text_ctrl)

        menu = self._trigger_context_menu(text_ctrl)
        items = menu.GetMenuItems()

        # Simulate selecting the Clear item
        clear_item = items[5]
        menu_event = wx.CommandEvent(wx.wxEVT_MENU, clear_item.GetId())
        menu.ProcessEvent(menu_event)

        assert text_ctrl.GetValue() == ""

        text_ctrl.Destroy()
