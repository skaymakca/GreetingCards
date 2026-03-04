"""Code signing entry point. Run with: uv run python -m scripts.sign"""

import subprocess
import sys

from scripts.sign.cli import main

try:
    main()
except subprocess.CalledProcessError as exc:
    print(f"Error: command failed (exit {exc.returncode}): {' '.join(exc.cmd)}", file=sys.stderr)
    raise SystemExit(1) from None
