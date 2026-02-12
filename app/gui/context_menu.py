"""Context menu helper for text entry widgets."""
import tkinter as tk
from app.gui import styles
from app.gui.icons import load_sf_symbol


def add_entry_context_menu(entry: tk.Entry):
    """Add a native-style context menu to an Entry widget with Cut, Copy, Paste, Clear.

    Args:
        entry: The tk.Entry widget to attach the context menu to
    """
    menu = tk.Menu(entry, tearoff=0, font=styles.FONT_SMALL)

    # Load SF Symbol icons
    icons = {}
    icon_specs = {
        "cut": ("scissors", 12),
        "copy": ("doc.on.doc", 12),
        "paste": ("doc.on.clipboard", 12),
        "clear": ("xmark.circle", 12),
    }
    for key, (symbol, size) in icon_specs.items():
        icon = load_sf_symbol(symbol, size, styles.TEXT_PRIMARY)
        if icon:
            icons[key] = icon

    # Cut
    menu.add_command(
        label="Cut",
        command=lambda: _cut(entry),
        accelerator="⌘X",
        image=icons.get("cut"),
        compound="left",
    )

    # Copy
    menu.add_command(
        label="Copy",
        command=lambda: _copy(entry),
        accelerator="⌘C",
        image=icons.get("copy"),
        compound="left",
    )

    # Paste
    menu.add_command(
        label="Paste",
        command=lambda: _paste(entry),
        accelerator="⌘V",
        image=icons.get("paste"),
        compound="left",
    )

    menu.add_separator()

    # Clear
    menu.add_command(
        label="Clear",
        command=lambda: _clear(entry),
        image=icons.get("clear"),
        compound="left",
    )

    # Store menu reference to prevent garbage collection
    entry._context_menu = menu
    entry._context_menu_icons = icons

    # Bind right-click (Button-2 on macOS, Button-3 on others)
    def show_menu(event):
        try:
            menu.post(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    entry.bind("<Button-2>", show_menu)  # macOS right-click
    entry.bind("<Control-Button-1>", show_menu)  # macOS Ctrl+click


def _cut(entry: tk.Entry):
    """Cut selected text to clipboard."""
    if entry.selection_present():
        entry.event_generate("<<Cut>>")


def _copy(entry: tk.Entry):
    """Copy selected text to clipboard."""
    if entry.selection_present():
        entry.event_generate("<<Copy>>")


def _paste(entry: tk.Entry):
    """Paste from clipboard."""
    entry.event_generate("<<Paste>>")


def _clear(entry: tk.Entry):
    """Clear all text."""
    entry.delete(0, tk.END)
