"""Help dialog showing app instructions and keyboard shortcuts."""
import wx
import wx.html


def show_help_dialog(parent):
    """Show help dialog with workflow instructions and shortcuts.

    Args:
        parent: Parent window
    """
    dialog = HelpDialog(parent)
    dialog.ShowModal()
    dialog.Destroy()


class HelpDialog(wx.Dialog):
    """Help window with workflow instructions and keyboard shortcuts."""

    def __init__(self, parent):
        super().__init__(
            parent,
            title="Help",
            size=(600, 650),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        )

        # Main sizer
        sizer = wx.BoxSizer(wx.VERTICAL)

        # HTML window for content
        html = wx.html.HtmlWindow(self, style=wx.html.HW_SCROLLBAR_AUTO)
        html.SetPage(self._generate_html())
        sizer.Add(html, 1, wx.EXPAND | wx.ALL, 15)

        # Close button
        close_btn = wx.Button(self, wx.ID_CLOSE, "Close")
        close_btn.Bind(wx.EVT_BUTTON, lambda evt: self.EndModal(wx.ID_CLOSE))
        sizer.Add(close_btn, 0, wx.ALIGN_CENTER | wx.BOTTOM, 15)

        self.SetSizer(sizer)
        self.CenterOnParent()

        # Keyboard shortcuts
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key)

    def _on_key(self, event):
        """Handle keyboard shortcuts."""
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CLOSE)
        else:
            event.Skip()

    def _generate_html(self) -> str:
        """Generate HTML content for help dialog."""
        return """
        <html>
        <body>

        <h3>Workflow</h3>
        <ol>
            <li>Browse or drag-drop a folder containing greeting card PDFs</li>
            <li>Click Process to extract family names using OCR</li>
            <li>Review extracted names in the cards list</li>
            <li>Click AI button (per card or AI All) for better accuracy</li>
            <li>Edit names manually or select from Candidates dropdown</li>
            <li>Click Rename All to rename files with extracted names</li>
        </ol>

        <h3>Toolbar Buttons</h3>
        <ul>
            <li><b>Browse</b> — Select a folder of PDF files</li>
            <li><b>Process</b> — Extract names from all cards using OCR</li>
            <li><b>AI All</b> — Analyze all cards with Claude AI (requires API key)</li>
            <li><b>Rename All</b> — Rename files based on extracted names</li>
            <li><b>Clear</b> — Remove all cards and start over</li>
            <li><b>Settings</b> — Configure API key and database</li>
        </ul>

        <h3>Card List Features</h3>
        <ul>
            <li>Confidence dots show extraction quality (green=high, yellow=medium, red=low, blue=manual)</li>
            <li>Click a row to view the card in the preview panel</li>
            <li>Edit family name directly in the text field</li>
            <li>Checkbox to remove 'Family' suffix from filename (e.g., 'Smith.pdf' instead of 'Smith Family.pdf')</li>
            <li>Candidates dropdown shows alternate name suggestions</li>
            <li>AI button analyzes a single card with Claude AI</li>
            <li>Right-click text fields for Cut, Copy, Paste, Clear</li>
        </ul>

        <h3>Preview Panel</h3>
        <ul>
            <li>View all pages of the selected card</li>
            <li>Navigate pages with ◀ and ▶ buttons</li>
            <li>Click and drag to pan when zoomed in</li>
            <li>Scroll wheel to zoom in/out</li>
        </ul>

        <h3>Keyboard Shortcuts</h3>
        <ul>
            <li><b>↑  ↓</b> — Navigate cards in list (select previous/next)</li>
            <li><b>←  →</b> — Navigate pages in preview</li>
            <li><b>Esc</b> — Defocus text entries</li>
            <li><b>⌘X, ⌘C, ⌘V</b> — Cut, Copy, Paste (in text fields)</li>
        </ul>

        <h3>Zoom Controls</h3>
        <ul>
            <li><b>Shift + Click</b> — Zoom in (cursor shows ✚)</li>
            <li><b>Ctrl/⌘ + Click</b> — Zoom out (cursor shows ✖)</li>
            <li><b>Scroll Wheel</b> — Zoom in/out at cursor</li>
            <li><b>Fit button</b> — Reset to fit window</li>
        </ul>

        <h3>Tips</h3>
        <ul>
            <li>Cards are cached in the database for faster reprocessing</li>
            <li>AI analysis gives more accurate results than OCR alone</li>
            <li>Manual edits override all automatic extractions</li>
            <li>Rebuild database in Settings to clear all cached results</li>
        </ul>

        </body>
        </html>
        """
