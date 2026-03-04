# Coverage: excluded (macOS-interactive AppleScript toggle) — see [tool.coverage.run] omit in pyproject.toml
"""Toggle macOS dark/light mode every 5 seconds until Ctrl-C.

Usage::

    uv run python -m scripts.dark_mode_cycler
"""

from __future__ import annotations

import subprocess
import time

INTERVAL = 5


def _toggle() -> None:
    subprocess.run(
        [
            "osascript",
            "-e",
            'tell application "System Events" to tell appearance preferences to set dark mode to not dark mode',
        ],
        check=True,
    )


def main() -> None:
    print(f"Toggling appearance every {INTERVAL}s. Press Ctrl-C to stop.")
    try:
        while True:
            _toggle()
            time.sleep(INTERVAL)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
