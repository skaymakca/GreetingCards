"""Shared helpers for scripts in this directory."""

from __future__ import annotations

import contextlib
import shutil
from collections.abc import Generator
from datetime import datetime
from pathlib import Path

# All script output goes under this root directory.
SCRIPT_OUTPUT_ROOT = Path(__file__).resolve().parent.parent / "_build" / "script_output"


def _make_output_dir(folder_name: str) -> Path:
    """Create a timestamped output directory under _build/script_output/.

    Format: _build/script_output/YYYYMMDD_HHMM-folder_name/

    The directory is created immediately and the path is returned.
    """
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    dir_name = f"{stamp}-{folder_name}"
    output_dir = SCRIPT_OUTPUT_ROOT / dir_name
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


@contextlib.contextmanager
def script_output_dir(folder_name: str) -> Generator[Path]:
    """Context manager that creates a timestamped output directory.

    Yields the directory path for use inside the block.
    On exception: removes the directory if nothing was written to it.
    On success: directory is kept as-is.
    """
    path = _make_output_dir(folder_name)
    try:
        yield path
    except BaseException:
        if path.exists() and not any(path.iterdir()):
            shutil.rmtree(path)
        raise
