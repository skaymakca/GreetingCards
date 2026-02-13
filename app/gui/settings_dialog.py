import subprocess
import tkinter as tk
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

from app.gui import styles
from app.gui.icons import load_sf_symbol
from app.gui.context_menu import add_entry_context_menu
from app.core.config import get_api_key, save_api_key
from app.core.database import reset_database
from app.version import __version__


class ApiKeyPrompt(tk.Toplevel):
    """Simple prompt for API key when needed for AI features."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("API Key Required")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        w, h = 500, 200
        x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.configure(bg=styles.BG_PRIMARY)

        self.result = None

        # Message
        tk.Label(
            self, text="AI analysis requires an Anthropic API key.",
            font=styles.FONT_BODY, bg=styles.BG_PRIMARY, fg=styles.TEXT_PRIMARY,
        ).pack(pady=(20, 4), padx=20)

        tk.Label(
            self, text="Get one at: console.anthropic.com",
            font=styles.FONT_SMALL, bg=styles.BG_PRIMARY, fg=styles.TEXT_SECONDARY,
        ).pack(padx=20, pady=(0, 12))

        # Key entry
        key_frame = tk.Frame(self, bg=styles.BG_PRIMARY)
        key_frame.pack(fill="x", padx=20, pady=8)

        tk.Label(
            key_frame, text="API Key:", font=styles.FONT_BODY,
            bg=styles.BG_PRIMARY, fg=styles.TEXT_PRIMARY,
        ).pack(side="left", padx=(0, 8))

        self._key_entry = tk.Entry(key_frame, font=styles.FONT_BODY, show="*", width=30)
        self._key_entry.pack(side="left", fill="x", expand=True)
        self._key_entry.focus_set()
        self._key_entry.bind("<Return>", lambda e: self._save())
        add_entry_context_menu(self._key_entry)

        # Buttons
        btn_frame = tk.Frame(self, bg=styles.BG_PRIMARY)
        btn_frame.pack(pady=(16, 24))

        ttk.Button(
            btn_frame, text="Cancel",
            command=self._cancel,
        ).pack(side="left", padx=6)

        ttk.Button(
            btn_frame, text="Save",
            command=self._save,
        ).pack(side="left", padx=6)

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", lambda e: self._cancel())

    def _save(self):
        key = self._key_entry.get().strip()
        if key:
            save_api_key(key)
            self.result = True
            self.grab_release()
            self.destroy()
        else:
            messagebox.showwarning("Empty Key", "Please enter an API key.", parent=self)

    def _cancel(self):
        self.result = False
        self.grab_release()
        self.destroy()


class SettingsDialog(tk.Toplevel):
    """Settings window with API key management and database controls."""

    def __init__(self, parent, on_db_reset=None):
        super().__init__(parent)
        self.title("Settings")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        w, h = 420, 330
        x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.configure(bg=styles.BG_PRIMARY)

        self._on_db_reset = on_db_reset

        # --- About section ---
        about_frame = tk.Frame(self, bg=styles.BG_PRIMARY)
        about_frame.pack(fill="x", padx=20, pady=(16, 0))

        # App icon
        self._app_icon = self._load_app_icon(48)
        if self._app_icon:
            tk.Label(
                about_frame, image=self._app_icon,
                bg=styles.BG_PRIMARY,
            ).pack(side="left", padx=(0, 12))

        # Name and version info
        info_frame = tk.Frame(about_frame, bg=styles.BG_PRIMARY)
        info_frame.pack(side="left", anchor="w")

        tk.Label(
            info_frame, text="Greeting Cards", font=styles.FONT_TITLE,
            bg=styles.BG_PRIMARY, fg=styles.TEXT_PRIMARY,
        ).pack(anchor="w")

        commit = self._get_commit_hash()
        version_text = f"Version {__version__}"
        if commit:
            version_text += f" ({commit})"
        tk.Label(
            info_frame, text=version_text, font=styles.FONT_SMALL,
            bg=styles.BG_PRIMARY, fg=styles.TEXT_SECONDARY,
        ).pack(anchor="w")

        # --- Separator ---
        tk.Frame(self, height=1, bg=styles.TEXT_SECONDARY).pack(
            fill="x", padx=20, pady=(12, 0)
        )

        # --- API Key section ---
        tk.Label(
            self, text="API Key", font=styles.FONT_HEADING,
            bg=styles.BG_PRIMARY, fg=styles.TEXT_PRIMARY,
        ).pack(pady=(16, 4), padx=20, anchor="w")

        key_frame = tk.Frame(self, bg=styles.BG_PRIMARY)
        key_frame.pack(fill="x", padx=20)

        self._key_entry = tk.Entry(key_frame, font=styles.FONT_BODY, show="*")
        self._key_entry.pack(side="left", fill="x", expand=True)

        current_key = get_api_key()
        if current_key:
            self._key_entry.insert(0, current_key)

        add_entry_context_menu(self._key_entry)

        self._save_key_btn = ttk.Button(
            key_frame, text="Save",
            command=self._save_api_key,
        )
        self._save_key_btn.pack(side="left", padx=(8, 0))

        # Status label
        self._key_status = tk.Label(
            self, text="", font=styles.FONT_SMALL,
            bg=styles.BG_PRIMARY, fg=styles.SUCCESS,
        )
        self._key_status.pack(padx=20, anchor="w")

        # --- Separator ---
        tk.Frame(self, height=1, bg=styles.TEXT_SECONDARY).pack(
            fill="x", padx=20, pady=(12, 0)
        )

        # --- Database section ---
        tk.Label(
            self, text="Database", font=styles.FONT_HEADING,
            bg=styles.BG_PRIMARY, fg=styles.TEXT_PRIMARY,
        ).pack(pady=(12, 4), padx=20, anchor="w")

        db_frame = tk.Frame(self, bg=styles.BG_PRIMARY)
        db_frame.pack(fill="x", padx=20)

        tk.Label(
            db_frame, text="Clear all cached OCR/AI results and rebuild.",
            font=styles.FONT_SMALL, bg=styles.BG_PRIMARY, fg=styles.TEXT_SECONDARY,
        ).pack(side="left")

        self._rebuild_btn = ttk.Button(
            db_frame, text="Rebuild",
            command=self._rebuild_db,
        )
        self._rebuild_btn.pack(side="right")

        # --- Close ---
        close_btn = tk.Button(
            self, text="Close", font=styles.FONT_BODY,
            command=self._close, width=8,
        )
        close_btn.pack(pady=(16, 16))

        # Apply SF Symbol icons
        self._icons = {}
        for key, symbol, btn in [
            ("save", "checkmark", self._save_key_btn),
            ("rebuild", "arrow.triangle.2.circlepath", self._rebuild_btn),
        ]:
            icon = load_sf_symbol(symbol, 6, styles.TEXT_PRIMARY)
            if icon:
                self._icons[key] = icon
                btn.config(image=icon, compound="left")

        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Escape>", lambda e: self._close())

    @staticmethod
    def _load_app_icon(size: int):
        """Load the app icon as a PhotoImage, resized to size x size."""
        import sys
        from pathlib import Path

        if getattr(sys, "_MEIPASS", None):
            icon_path = Path(sys._MEIPASS) / "icon.png"
        else:
            icon_path = Path(__file__).resolve().parent.parent.parent / "icon.png"

        if not icon_path.exists():
            return None

        try:
            img = Image.open(icon_path).resize((size, size), Image.LANCZOS)
            return ImageTk.PhotoImage(img)
        except Exception:
            return None

    @staticmethod
    def _get_commit_hash() -> str:
        """Get short git commit hash, or empty string if unavailable."""
        try:
            return subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL,
            ).decode().strip()
        except Exception:
            return ""

    def _save_api_key(self):
        key = self._key_entry.get().strip()
        if key:
            save_api_key(key)
            self._key_status.config(text="Saved", fg=styles.SUCCESS)
        else:
            self._key_status.config(text="Key cannot be empty", fg=styles.ERROR)

    def _rebuild_db(self):
        confirm = messagebox.askyesno(
            "Rebuild Database",
            "This will delete all cached OCR results, AI results, and manual edits.\n\nContinue?",
            parent=self,
        )
        if not confirm:
            return
        reset_database()
        messagebox.showinfo("Database Rebuilt", "The cache has been cleared.", parent=self)
        if self._on_db_reset:
            self._on_db_reset()

    def _close(self):
        self.grab_release()
        self.destroy()
