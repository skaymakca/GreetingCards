"""Shared helpers for scripts in this directory."""

from __future__ import annotations

import contextlib
import plistlib
import shutil
import subprocess
import tomllib
from collections.abc import Generator
from datetime import datetime
from pathlib import Path

# Absolute path to the project root (parent of ``scripts/``).
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

# All script output goes under this root directory.
SCRIPT_OUTPUT_ROOT = PROJECT_ROOT / "_build" / "script_output"


def read_version() -> str:
    """Read the project version from ``pyproject.toml``."""
    with open(PROJECT_ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]["version"]


def app_path() -> Path:
    """Return the path to the built macOS ``.app`` bundle."""
    return PROJECT_ROOT / "dist" / "Greeting Cards.app"


def read_build_number() -> str:
    """Read ``CFBundleVersion`` from the built app's ``Info.plist``.

    Raises:
        FileNotFoundError: If the app bundle has not been built yet.
        ValueError: If ``CFBundleVersion`` is missing from the plist.
    """
    plist_path = app_path() / "Contents" / "Info.plist"
    if not plist_path.exists():
        raise FileNotFoundError(f"Info.plist not found: {plist_path}\n  Build the app first.")
    with open(plist_path, "rb") as f:
        info = plistlib.load(f)
    build = info.get("CFBundleVersion")
    if not build:
        raise ValueError(f"CFBundleVersion not found in {plist_path}")
    return str(build)


def dmg_path(version: str | None = None) -> Path:
    """Return the path to the DMG installer for *version*.

    If *version* is ``None``, :func:`read_version` is called automatically.
    """
    if version is None:
        version = read_version()
    return PROJECT_ROOT / "dist" / f"Greeting-Cards-{version}.dmg"


def _make_output_dir(folder_name: str) -> Path:
    """Create a timestamped output directory under _build/script_output/.

    Format: _build/script_output/YYYYMMDDThhmm-folder_name/

    The directory is created immediately and the path is returned.
    """
    stamp = datetime.now().strftime("%Y%m%dT%H%M")
    dir_name = f"{stamp}-{folder_name}"
    output_dir = SCRIPT_OUTPUT_ROOT / dir_name
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


# noinspection PyTypeChecker
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


def run_command(cmd: list[str], *, dry_run: bool = False, capture: bool = False) -> subprocess.CompletedProcess[str]:
    """Run a shell command, printing it first. In dry-run mode, skip execution."""
    print(f"  {'[dry-run] ' if dry_run else ''}{' '.join(cmd)}")
    if dry_run:
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
    return subprocess.run(cmd, check=True, text=True, capture_output=capture)
