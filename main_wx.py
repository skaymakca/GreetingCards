#!/usr/bin/env python3
"""wxPython test harness for Greeting Cards App.

This is a minimal test application to verify wxPython is working correctly.
As we migrate components, we'll build up this file to become the main entry point.
"""

import wx
import time
from pathlib import Path
from app.gui import wx_styles
from app.gui import wx_utils
from app.gui.wx_api_key_dialog import show_api_key_dialog
from app.gui.wx_dialogs import ProgressDialog, CompletionDialog, RenameConfirmDialog, ErrorListDialog
from app.gui.wx_help_dialog import show_help_dialog
from app.gui.wx_settings_dialog import show_settings_dialog
from app.models.card import RenameResult, RenamePlanItem


class TestFrame(wx.Frame):
    """Simple test window to verify wxPython setup."""

    def __init__(self):
        super().__init__(
            parent=None,
            title="Greeting Cards - wxPython Test",
            size=(wx_styles.Layout.WINDOW_WIDTH, wx_styles.Layout.WINDOW_HEIGHT)
        )

        # Set icon (use app icon if available)
        # TODO: Set app icon when we migrate icons

        # Create main panel
        panel = wx.Panel(self)
        panel.SetBackgroundColour(wx_styles.Color.BG_PRIMARY)

        # Create sizer for layout
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Title label
        title = wx_utils.create_static_text(
            panel,
            "wxPython Migration Test",
            font=wx_styles.Font.TITLE(),
            colour=wx_styles.Color.ACCENT
        )
        sizer.Add(title, 0, wx.ALL | wx.CENTER, wx_styles.Layout.PAD * 3)

        # Status message
        status = wx_utils.create_static_text(
            panel,
            "✓ wxPython is working correctly!",
            font=wx_styles.Font.HEADING(),
            colour=wx_styles.Color.SUCCESS
        )
        sizer.Add(status, 0, wx.ALL | wx.CENTER, wx_styles.Layout.PAD)

        # Info text
        info = wx_utils.create_static_text(
            panel,
            "This is a test harness for the wxPython migration.\n"
            "As we migrate components, they will be integrated here.",
            font=wx_styles.Font.BODY(),
            colour=wx_styles.Color.TEXT_SECONDARY
        )
        sizer.Add(info, 0, wx.ALL | wx.CENTER, wx_styles.Layout.PAD * 2)

        # Add some spacing
        sizer.AddStretchSpacer()

        # Test buttons to verify styles
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)

        btn_info = wx_utils.create_button(
            panel,
            "Show Info",
            lambda: wx_utils.show_info(self, "This is an info message!", "Info Test")
        )
        button_sizer.Add(btn_info, 0, wx.ALL, wx_styles.Layout.PAD)

        btn_warning = wx_utils.create_button(
            panel,
            "Show Warning",
            lambda: wx_utils.show_warning(self, "This is a warning!", "Warning Test")
        )
        button_sizer.Add(btn_warning, 0, wx.ALL, wx_styles.Layout.PAD)

        btn_error = wx_utils.create_button(
            panel,
            "Show Error",
            lambda: wx_utils.show_error(self, "This is an error!", "Error Test")
        )
        button_sizer.Add(btn_error, 0, wx.ALL, wx_styles.Layout.PAD)

        btn_confirm = wx_utils.create_button(
            panel,
            "Show Confirm",
            lambda: wx_utils.show_info(
                self,
                f"You clicked: {'Yes' if wx_utils.confirm(self, 'Are you sure?', 'Confirm Test') else 'No'}",
                "Result"
            )
        )
        button_sizer.Add(btn_confirm, 0, wx.ALL, wx_styles.Layout.PAD)

        sizer.Add(button_sizer, 0, wx.ALL | wx.CENTER, wx_styles.Layout.PAD)

        # Phase 2 dialog tests
        dialog_sizer = wx.BoxSizer(wx.HORIZONTAL)

        btn_api_key = wx_utils.create_button(
            panel,
            "API Key Dialog",
            self._test_api_key
        )
        dialog_sizer.Add(btn_api_key, 0, wx.ALL, wx_styles.Layout.PAD)

        btn_progress = wx_utils.create_button(
            panel,
            "Progress Dialog",
            self._test_progress
        )
        dialog_sizer.Add(btn_progress, 0, wx.ALL, wx_styles.Layout.PAD)

        btn_completion = wx_utils.create_button(
            panel,
            "Completion Dialog",
            self._test_completion
        )
        dialog_sizer.Add(btn_completion, 0, wx.ALL, wx_styles.Layout.PAD)

        sizer.Add(dialog_sizer, 0, wx.ALL | wx.CENTER, wx_styles.Layout.PAD)

        # Phase 3 dialog tests
        dialog_sizer2 = wx.BoxSizer(wx.HORIZONTAL)

        btn_help = wx_utils.create_button(
            panel,
            "Help Dialog",
            self._test_help
        )
        dialog_sizer2.Add(btn_help, 0, wx.ALL, wx_styles.Layout.PAD)

        btn_settings = wx_utils.create_button(
            panel,
            "Settings Dialog",
            self._test_settings
        )
        dialog_sizer2.Add(btn_settings, 0, wx.ALL, wx_styles.Layout.PAD)

        btn_rename_confirm = wx_utils.create_button(
            panel,
            "Rename Confirm",
            self._test_rename_confirm
        )
        dialog_sizer2.Add(btn_rename_confirm, 0, wx.ALL, wx_styles.Layout.PAD)

        btn_error_list = wx_utils.create_button(
            panel,
            "Error List",
            self._test_error_list
        )
        dialog_sizer2.Add(btn_error_list, 0, wx.ALL, wx_styles.Layout.PAD)

        sizer.Add(dialog_sizer2, 0, wx.ALL | wx.CENTER, wx_styles.Layout.PAD)

        # Phase 4 icon and context menu tests
        phase4_sizer = wx.BoxSizer(wx.HORIZONTAL)

        btn_icons = wx_utils.create_button(
            panel,
            "SF Symbols Test",
            self._test_icons
        )
        phase4_sizer.Add(btn_icons, 0, wx.ALL, wx_styles.Layout.PAD)

        btn_context = wx_utils.create_button(
            panel,
            "Context Menu Test",
            self._test_context_menu
        )
        phase4_sizer.Add(btn_context, 0, wx.ALL, wx_styles.Layout.PAD)

        sizer.Add(phase4_sizer, 0, wx.ALL | wx.CENTER, wx_styles.Layout.PAD)

        # Phase 5 preview panel test
        phase5_sizer = wx.BoxSizer(wx.HORIZONTAL)

        btn_preview = wx_utils.create_button(
            panel,
            "Preview Panel Test",
            self._test_preview_panel
        )
        phase5_sizer.Add(btn_preview, 0, wx.ALL, wx_styles.Layout.PAD)

        sizer.Add(phase5_sizer, 0, wx.ALL | wx.CENTER, wx_styles.Layout.PAD)

        # Phase 6 review panel test
        phase6_sizer = wx.BoxSizer(wx.HORIZONTAL)

        btn_master_detail = wx_utils.create_button(
            panel,
            "Master-Detail Test",
            self._test_master_detail
        )
        phase6_sizer.Add(btn_master_detail, 0, wx.ALL, wx_styles.Layout.PAD)

        sizer.Add(phase6_sizer, 0, wx.ALL | wx.CENTER, wx_styles.Layout.PAD)

        # More spacing
        sizer.AddStretchSpacer()

        # Version info
        version_text = wx_utils.create_static_text(
            panel,
            f"wxPython {wx.version()}",
            font=wx_styles.Font.SMALL(),
            colour=wx_styles.Color.TEXT_SECONDARY
        )
        sizer.Add(version_text, 0, wx.ALL | wx.CENTER, wx_styles.Layout.PAD)

        # Set sizer
        panel.SetSizer(sizer)

        # Center window on screen
        wx_utils.center_window(self)

        # Bind close event
        self.Bind(wx.EVT_CLOSE, self.on_close)

    def on_close(self, event):
        """Handle window close event."""
        self.Destroy()

    def _test_api_key(self):
        """Test API key dialog."""
        api_key = show_api_key_dialog(self)

        if api_key:
            wx_utils.show_info(self, f"API Key entered: {api_key[:10]}...", "Success")
        else:
            wx_utils.show_info(self, "API Key dialog cancelled", "Cancelled")

    def _test_progress(self):
        """Test progress dialog."""
        total = 10
        progress = ProgressDialog(self, "Processing Test", total)
        progress.Show()

        # Simulate work
        for i in range(1, total + 1):
            wx.MilliSleep(300)  # Simulate work
            progress.update_progress(i, f"Processing item {i}...")

        progress.finish()
        wx_utils.show_info(self, "Progress test complete!", "Done")

    def _test_completion(self):
        """Test completion dialog."""
        # Create mock results
        results = [
            RenameResult(
                Path("card1.pdf"),
                Path("Holiday Cards 2024 - Smith Family.pdf"),
                True,
                "Renamed"
            ),
            RenameResult(
                Path("card2.pdf"),
                Path("Holiday Cards 2024 - Johnson Family.pdf"),
                True,
                "Renamed"
            ),
            RenameResult(
                Path("card3.pdf"),
                Path("card3.pdf"),
                True,
                "Already named correctly"
            ),
            RenameResult(
                Path("card4.pdf"),
                Path("Holiday Cards 2024 - Brown Family.pdf"),
                False,
                "Permission denied"
            ),
        ]

        dialog = CompletionDialog(self, "Rename Complete", results)
        dialog.ShowModal()
        dialog.Destroy()

    def _test_help(self):
        """Test help dialog."""
        show_help_dialog(self)

    def _test_settings(self):
        """Test settings dialog."""
        show_settings_dialog(self)

    def _test_rename_confirm(self):
        """Test rename confirm dialog."""
        # Create mock rename plan
        plan = [
            RenamePlanItem(
                Path("card1.pdf"),
                Path("Holiday Cards 2024 - Smith Family.pdf"),
                "ok"
            ),
            RenamePlanItem(
                Path("card2.pdf"),
                Path("Holiday Cards 2024 - Johnson Family.pdf"),
                "ok"
            ),
            RenamePlanItem(
                Path("card3.pdf"),
                Path("Holiday Cards 2024 - Smith Family.pdf"),
                "duplicate"
            ),
            RenamePlanItem(
                Path("card4.pdf"),
                Path("card4.pdf"),
                "skip_same"
            ),
            RenamePlanItem(
                Path("card5.pdf"),
                Path("card5.pdf"),
                "skip_no_name"
            ),
            RenamePlanItem(
                Path("card6.pdf"),
                Path("card6.pdf"),
                "skip_error"
            ),
        ]

        dialog = RenameConfirmDialog(self, plan, "2024")
        result = dialog.ShowModal()
        dialog.Destroy()

        if result == wx.ID_OK:
            wx_utils.show_info(self, "User clicked Rename All", "Result")
        else:
            wx_utils.show_info(self, "User clicked Cancel", "Result")

    def _test_error_list(self):
        """Test error list dialog."""
        # Create mock errors
        errors = [
            ("card1.pdf", "Authentication failed"),
            ("card2.pdf", "Timeout exceeded"),
            ("card3.pdf", "Invalid response format"),
            ("card4.pdf", "Permission denied"),
        ]

        dialog = ErrorListDialog(self, "AI Analysis Errors", errors, auth_aborted=True)
        dialog.ShowModal()
        dialog.Destroy()

    def _test_icons(self):
        """Test SF Symbol icon loading at various sizes."""
        from app.gui import wx_icons

        # Create a dialog to show various icons and sizes
        dialog = wx.Dialog(self, title="SF Symbol Icons Test", size=(550, 550))
        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.AddSpacer(wx_styles.Layout.PAD * 2)

        # Title
        title = wx_utils.create_static_text(
            dialog,
            "SF Symbol Icon Test",
            font=wx_styles.Font.TITLE(),
            colour=wx_styles.Color.ACCENT
        )
        sizer.Add(title, 0, wx.ALL | wx.CENTER, wx_styles.Layout.PAD)

        sizer.AddSpacer(wx_styles.Layout.PAD)

        # Test various icons at different sizes
        test_configs = [
            ("scissors", "Cut (12pt)", 12),
            ("doc.on.doc", "Copy (12pt)", 12),
            ("textformat.abc", "Title Case (12pt)", 12),
            ("xmark.circle", "Clear (12pt)", 12),
            ("scissors", "Cut (16pt)", 16),
            ("textformat.abc", "Title Case (20pt)", 20),
        ]

        for symbol_name, label, pt_size in test_configs:
            row = wx.BoxSizer(wx.HORIZONTAL)

            # Load icon at specified size
            bitmap = wx_icons.load_sf_symbol(symbol_name, pt_size, "#1D1D1F")

            if bitmap:
                icon_ctrl = wx.StaticBitmap(dialog, bitmap=bitmap)
                row.Add(icon_ctrl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, wx_styles.Layout.PAD)
                status = "✓"
            else:
                # Show placeholder if icon failed to load
                placeholder = wx_utils.create_static_text(dialog, "[?]")
                row.Add(placeholder, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, wx_styles.Layout.PAD)
                status = "✗"

            # Label
            text = wx_utils.create_static_text(
                dialog,
                f"{label} {status}",
                font=wx_styles.Font.BODY()
            )
            row.Add(text, 0, wx.ALIGN_CENTER_VERTICAL)

            sizer.Add(row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, wx_styles.Layout.PAD * 2)

        sizer.AddSpacer(wx_styles.Layout.PAD * 3)

        # OK button
        ok_btn = wx.Button(dialog, wx.ID_OK, "OK")
        ok_btn.SetMinSize((120, 32))
        ok_btn.Bind(wx.EVT_BUTTON, lambda evt: dialog.EndModal(wx.ID_OK))
        sizer.Add(ok_btn, 0, wx.ALIGN_CENTER | wx.ALL, wx_styles.Layout.PAD * 2)

        dialog.SetSizer(sizer)
        dialog.CenterOnParent()
        dialog.ShowModal()
        dialog.Destroy()

    def _test_context_menu(self):
        """Test context menu with SF Symbol icons."""
        from app.gui import wx_context_menu

        # Create a dialog with a text field that has the context menu
        dialog = wx.Dialog(self, title="Context Menu Test", size=(400, 250))
        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.AddSpacer(20)

        # Title
        title = wx.StaticText(dialog, label="Context Menu Test")
        title.SetFont(wx_styles.Font.TITLE())
        sizer.Add(title, 0, wx.LEFT | wx.RIGHT, 20)

        sizer.AddSpacer(10)

        # Instructions
        instructions = wx.StaticText(
            dialog,
            label="Right-click the text field below to see the context menu\n"
                  "with SF Symbol icons (Cut, Copy, Paste, Title Case, Clear)."
        )
        instructions.SetFont(wx_styles.Font.BODY())
        sizer.Add(instructions, 0, wx.LEFT | wx.RIGHT, 20)

        sizer.AddSpacer(20)

        # Text field with context menu
        text_ctrl = wx.TextCtrl(
            dialog,
            value="hello world - right click me!",
            size=(360, -1)
        )
        text_ctrl.SetFont(wx_styles.Font.BODY())
        wx_context_menu.add_entry_context_menu(text_ctrl)
        sizer.Add(text_ctrl, 0, wx.LEFT | wx.RIGHT, 20)

        sizer.AddStretchSpacer()

        # OK button
        ok_btn = wx.Button(dialog, wx.ID_OK, "OK")
        ok_btn.Bind(wx.EVT_BUTTON, lambda evt: dialog.EndModal(wx.ID_OK))
        sizer.Add(ok_btn, 0, wx.ALIGN_CENTER | wx.BOTTOM, 20)

        dialog.SetSizer(sizer)
        dialog.CenterOnParent()
        dialog.ShowModal()
        dialog.Destroy()

    def _test_preview_panel(self):
        """Test preview panel with sample PDFs."""
        from app.gui.wx_preview_panel import PreviewPanel
        from PIL import Image

        dialog = wx.Dialog(
            self,
            title="Preview Panel Test",
            size=(800, 600),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.MAXIMIZE_BOX
        )
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Instructions
        instructions = wx_utils.create_static_text(
            dialog,
            "Controls: Scroll wheel = zoom | Shift+Click = zoom in | Option+Click = zoom out | Drag = pan",
            font=wx_styles.Font.SMALL(),
            colour=wx_styles.Color.TEXT_SECONDARY
        )
        sizer.Add(instructions, 0, wx.ALL | wx.EXPAND, 10)

        # Create preview panel
        preview = PreviewPanel(dialog)
        sizer.Add(preview, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Control buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Load sample image button
        load_btn = wx_utils.create_button(
            dialog, "Load Sample Image",
            lambda: self._load_sample_image(preview)
        )
        btn_sizer.Add(load_btn, 0, wx.RIGHT, 5)

        # Load multi-page button
        multi_btn = wx_utils.create_button(
            dialog, "Load Multi-Page",
            lambda: self._load_multi_page(preview)
        )
        btn_sizer.Add(multi_btn, 0, wx.RIGHT, 5)

        # Show error button
        error_btn = wx_utils.create_button(
            dialog, "Show Error",
            lambda: preview.show_error("This is a test error message!", "test.pdf")
        )
        btn_sizer.Add(error_btn, 0, wx.RIGHT, 5)

        # Clear button
        clear_btn = wx_utils.create_button(
            dialog, "Clear",
            lambda: preview.clear()
        )
        btn_sizer.Add(clear_btn, 0)

        sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.BOTTOM, 10)

        dialog.SetSizer(sizer)
        dialog.CenterOnParent()
        dialog.ShowModal()
        dialog.Destroy()

    def _load_sample_image(self, preview):
        """Load a sample image into preview panel."""
        from PIL import Image, ImageDraw

        # Create a simple test image
        img = Image.new('RGB', (400, 600), color='white')
        draw = ImageDraw.Draw(img)

        # Draw border
        draw.rectangle([10, 10, 390, 590], outline='black', width=3)

        # Draw some shapes
        draw.ellipse([100, 150, 300, 250], outline='blue', width=2)
        draw.rectangle([120, 300, 280, 400], fill='lightblue', outline='blue', width=2)
        draw.line([50, 450, 350, 450], fill='red', width=3)

        # Draw text (centered manually)
        try:
            text = "Sample PDF Page"
            bbox = draw.textbbox((0, 0), text)
            text_width = bbox[2] - bbox[0]
            draw.text((200 - text_width // 2, 280), text, fill='black')
        except:
            # Fallback if textbbox not available
            draw.text((150, 280), "Sample PDF Page", fill='black')

        preview.show_image(img, "sample.pdf")

    def _load_multi_page(self, preview):
        """Load multiple sample pages into preview panel."""
        from PIL import Image, ImageDraw

        images = []

        # Create 3 sample pages
        colors = ['lightblue', 'lightgreen', 'lightyellow']
        for i in range(1, 4):
            img = Image.new('RGB', (400, 600), color='white')
            draw = ImageDraw.Draw(img)

            # Draw border
            draw.rectangle([10, 10, 390, 590], outline='black', width=3)

            # Draw page-specific colored rectangle
            draw.rectangle([50, 100, 350, 500], fill=colors[i-1], outline='black', width=2)

            # Draw page number (large)
            page_text = f"PAGE {i}"
            try:
                bbox = draw.textbbox((0, 0), page_text)
                text_width = bbox[2] - bbox[0]
                draw.text((200 - text_width // 2, 280), page_text, fill='black')
            except:
                draw.text((150, 280), page_text, fill='black')

            # Draw shapes unique to each page
            if i == 1:
                draw.ellipse([150, 350, 250, 450], outline='red', width=3)
            elif i == 2:
                draw.polygon([(200, 350), (150, 450), (250, 450)], outline='blue', width=3)
            else:
                draw.rectangle([150, 350, 250, 450], outline='green', width=3)

            images.append(img)

        preview.show_images(images, "multi-page.pdf")

    def _test_master_detail(self):
        """Test master-detail review panel (prototype)."""
        from app.gui.wx_review_panel_master_detail import ReviewPanelMasterDetail
        from app.models.card import CardResult, Confidence, CandidateInfo

        dialog = wx.Dialog(
            self,
            title="Master-Detail Review Panel (Prototype)",
            size=(900, 700),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.MAXIMIZE_BOX
        )
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Instructions
        instructions = wx_utils.create_static_text(
            dialog,
            "Mac-native master-detail pattern: Select card in list (top), edit in detail panel (bottom). " +
            "Use Up/Down arrows or click to navigate.",
            font=wx_styles.Font.SMALL(),
            colour=wx_styles.Color.TEXT_SECONDARY
        )
        sizer.Add(instructions, 0, wx.ALL | wx.EXPAND, 10)

        # Callbacks
        def on_select(card_id):
            print(f"Selected card ID: {card_id}")

        def on_ai_request(card_id):
            wx_utils.show_info(dialog, f"AI request for card {card_id}", "AI Request")

        def on_name_change(card_id, new_name):
            print(f"Name changed for card {card_id}: {new_name}")

        # Create master-detail review panel
        review = ReviewPanelMasterDetail(dialog, on_select, on_ai_request, on_name_change)

        # Use same mock cards as original test
        from pathlib import Path
        cards = []

        # Card 1: High confidence OCR with candidates
        card1 = CardResult(
            id=1,
            pdf_path=Path("holiday-card-001.pdf"),
            family_name="Smith",
            confidence=Confidence.HIGH,
            method="ocr",
            original_confidence=Confidence.HIGH,
            remove_family=True
        )
        card1.candidates = [
            CandidateInfo(id=101, family_name="Smith", confidence="high", method="ocr"),
            CandidateInfo(id=102, family_name="Smyth", confidence="medium", method="ai"),
            CandidateInfo(id=103, family_name="Schmidt", confidence="low", method="ai"),
        ]
        cards.append(card1)

        # Card 2: Medium confidence AI
        card2 = CardResult(
            id=2,
            pdf_path=Path("holiday-card-002.pdf"),
            family_name="Johnson",
            confidence=Confidence.MEDIUM,
            method="ai",
            original_confidence=Confidence.MEDIUM,
            remove_family=False
        )
        card2.candidates = [
            CandidateInfo(id=201, family_name="Johnson", confidence="medium", method="ai"),
            CandidateInfo(id=202, family_name="Johnston", confidence="low", method="ai"),
        ]
        cards.append(card2)

        # Card 3: Low confidence
        card3 = CardResult(
            id=3,
            pdf_path=Path("holiday-card-003.pdf"),
            family_name="Williams",
            confidence=Confidence.LOW,
            method="ocr",
            original_confidence=Confidence.LOW,
            remove_family=True
        )
        card3.candidates = [
            CandidateInfo(id=301, family_name="Williams", confidence="low", method="ocr"),
            CandidateInfo(id=302, family_name="Wilson", confidence="low", method="ai"),
        ]
        cards.append(card3)

        # Card 4: No name extracted
        card4 = CardResult(
            id=4,
            pdf_path=Path("holiday-card-004.pdf"),
            family_name="",
            confidence=Confidence.NONE,
            method="missing",
            original_confidence=Confidence.NONE,
            remove_family=False
        )
        cards.append(card4)

        # Card 5: Manual entry
        card5 = CardResult(
            id=5,
            pdf_path=Path("holiday-card-005.pdf"),
            family_name="Brown",
            confidence=Confidence.MANUAL,
            method="manual",
            original_confidence=Confidence.HIGH,
            remove_family=True
        )
        cards.append(card5)

        # Card 6: Error card
        card6 = CardResult(
            id=6,
            pdf_path=Path("holiday-card-006.pdf"),
            family_name="",
            confidence=Confidence.NONE,
            method="missing",
            original_confidence=Confidence.NONE,
            remove_family=False
        )
        card6.error = "Failed to process: timeout"
        cards.append(card6)

        # Load cards
        review.load_cards(cards)

        sizer.Add(review, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # OK button
        ok_btn = wx.Button(dialog, wx.ID_OK, "OK")
        ok_btn.Bind(wx.EVT_BUTTON, lambda evt: dialog.EndModal(wx.ID_OK))
        sizer.Add(ok_btn, 0, wx.ALIGN_CENTER | wx.BOTTOM, 10)

        dialog.SetSizer(sizer)
        dialog.Layout()
        dialog.CenterOnParent()
        dialog.ShowModal()
        dialog.Destroy()


class TestApp(wx.App):
    """Test wxPython application."""

    def OnInit(self):
        """Initialize the application."""
        self.frame = TestFrame()
        self.frame.Show()
        return True


def main():
    """Main entry point for wxPython test."""
    app = TestApp()
    app.MainLoop()


if __name__ == "__main__":
    main()
