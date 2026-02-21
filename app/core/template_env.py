"""Shared Jinja2 template environment and utilities.

All HTML generators (help, changelog, licenses) use the same template
directory and environment settings.  This module provides the shared
``jinja_env`` instance and a common ``get_page_order()`` reader.
"""

from pathlib import Path

import jinja2

_TEMPLATES_DIR = (
    Path(__file__).resolve().parent.parent.parent / "content" / "html" / "templates"
)

jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=True,
    trim_blocks=True,
    lstrip_blocks=True,
)


def get_page_order(base_path: Path) -> list[str]:
    """Read page order from a generated ``page_order.txt`` manifest.

    Each HTML generator writes this file alongside its output.  The
    viewer toolbar reads it at runtime for Prev/Next navigation.

    Returns a list of relative HTML paths (e.g. ``["index.html",
    "pages/getting-started.html", ...]``).  Falls back to
    ``["index.html"]`` if the manifest is missing.
    """
    manifest = base_path / "page_order.txt"
    if manifest.exists():
        return [
            line
            for line in manifest.read_text(encoding="utf-8").splitlines()
            if line
        ]
    return ["index.html"]
