import tkinter as tk
from app.gui import styles


class ApiKeyDialog(tk.Toplevel):
    """Modal dialog for entering the Anthropic API key."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("API Key")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        w, h = 420, 160
        x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.configure(bg=styles.Color.BG_PRIMARY)

        self.result: str | None = None

        tk.Label(
            self, text="Enter your Anthropic API key:", font=styles.Font.BODY,
            bg=styles.Color.BG_PRIMARY, fg=styles.Color.TEXT_PRIMARY,
        ).pack(pady=(20, 8), padx=20, anchor="w")

        self._entry = tk.Entry(
            self, font=styles.Font.BODY, show="*", width=44,
        )
        self._entry.pack(padx=20)
        self._entry.focus_set()

        btn_frame = tk.Frame(self, bg=styles.Color.BG_PRIMARY)
        btn_frame.pack(fill="x", padx=20, pady=(16, 20))

        cancel_btn = tk.Button(
            btn_frame, text="Cancel", font=styles.Font.BODY,
            command=self._cancel, width=8,
        )
        cancel_btn.pack(side="right", padx=(8, 0))

        save_btn = tk.Button(
            btn_frame, text="Save", font=styles.Font.HEADING,
            command=self._save, width=8,
        )
        save_btn.pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Return>", lambda e: self._save())
        self.bind("<Escape>", lambda e: self._cancel())

    def _save(self):
        key = self._entry.get().strip()
        if key:
            self.result = key
        self.grab_release()
        self.destroy()

    def _cancel(self):
        self.result = None
        self.grab_release()
        self.destroy()
