"""Appcast generation entry point. Run with: uv run python -m scripts.appcast <subcommand>"""

import subprocess
import sys

from scripts.appcast.cli import AppcastError, main

try:
    main()
except (FileNotFoundError, AppcastError) as exc:
    print(f"Error: {exc}", file=sys.stderr)
    raise SystemExit(1) from None
except subprocess.CalledProcessError as exc:
    print(f"Error: command failed (exit {exc.returncode}): {' '.join(exc.cmd)}", file=sys.stderr)
    raise SystemExit(1) from None
