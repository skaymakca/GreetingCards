"""Release automation entry point. Run with: uv run python -m scripts.release <subcommand>"""

import subprocess
import sys

from scripts.release.cli import ReleaseError, main

try:
    main()
except (FileNotFoundError, ReleaseError) as exc:
    print(f"Error: {exc}", file=sys.stderr)
    raise SystemExit(1) from None
except subprocess.CalledProcessError as exc:
    print(f"Error: command failed (exit {exc.returncode}): {' '.join(exc.cmd)}", file=sys.stderr)
    raise SystemExit(1) from None
