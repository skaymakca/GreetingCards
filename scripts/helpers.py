"""Shared helpers for scripts in this directory."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

# All script output goes under this root directory.
SCRIPT_OUTPUT_ROOT = Path(__file__).resolve().parent.parent / "_build" / "script_output"


def make_output_dir(folder_name: str) -> Path:
    """Create a timestamped output directory under _build/script_output/.

    Format: _build/script_output/YYYYMMDD_HHMM-folder_name/

    The directory is created immediately and the path is returned.
    """
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    dir_name = f"{stamp}-{folder_name}"
    output_dir = SCRIPT_OUTPUT_ROOT / dir_name
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir
