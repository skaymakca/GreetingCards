"""Notarization entry point. Run with: uv run python -m scripts.notarize"""

import subprocess
import sys

from scripts.notarize.cli import main

try:
    main()
except subprocess.CalledProcessError as exc:
    print(f"Error: command failed (exit {exc.returncode}): {' '.join(exc.cmd)}", file=sys.stderr)
    raise SystemExit(1) from None
