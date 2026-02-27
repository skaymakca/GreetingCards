"""Changelog parsing and HTML generation.

Parses CHANGELOG.md and generates HTML pages grouped by MAJOR.MINOR version.
"""

import html
import logging
import re
from pathlib import Path

from app.core.content.changelog_models import ChangelogGroup, ChangelogVersion
from app.core.content.template_env import jinja_env as _jinja_env

logger = logging.getLogger(__name__)


def _parse_changelog(md_text: str) -> list[ChangelogVersion]:
    """Parse CHANGELOG.md into a list of ChangelogVersion entries.

    Handles ## headings, paragraphs, bullet lists, **bold**, and *italic*.
    """
    versions: list[ChangelogVersion] = []
    current_version: str | None = None
    current_title: str | None = None
    current_date: str = ""
    body_lines: list[str] = []
    in_list = False

    def _flush() -> None:
        nonlocal current_version, current_title, current_date, in_list
        if current_version is None:
            return
        if in_list:
            body_lines.append("</ul>")
            in_list = False
        body_html = "\n".join(body_lines)
        versions.append(
            ChangelogVersion(
                version=current_version,
                title=current_title or current_version,
                date=current_date,
                body_html=body_html,
            )
        )
        body_lines.clear()
        current_version = None
        current_title = None
        current_date = ""

    def _inline(text: str) -> str:
        """Apply inline formatting: **bold** and *italic*."""
        escaped = html.escape(text)
        escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
        escaped = re.sub(r"\*(.+?)\*", r"<em>\1</em>", escaped)
        return escaped

    for raw_line in md_text.splitlines():
        line = raw_line.rstrip()

        # ## heading — new version
        if line.startswith("## "):
            _flush()
            heading = line[3:].strip()
            # Extract version tag (e.g. "0.8.0" from "0.8.0 — Title (date)")
            version_match = re.match(r"([\d.]+)", heading)
            current_version = version_match.group(1) if version_match else heading

            # Extract date/status from parentheses at end
            date_match = re.search(r"\(([^)]+)\)\s*$", heading)
            if date_match:
                current_date = date_match.group(1)
                current_title = heading[: date_match.start()].rstrip()
            else:
                current_date = ""
                current_title = heading
            continue

        # Skip top-level heading and blank lines before first version
        if current_version is None:
            continue

        # Bullet item
        if line.startswith("- "):
            if not in_list:
                body_lines.append("<ul>")
                in_list = True
            body_lines.append(f"<li>{_inline(line[2:])}</li>")
            continue

        # Blank line
        if not line:
            if in_list:
                body_lines.append("</ul>")
                in_list = False
            continue

        # Paragraph text
        if in_list:
            body_lines.append("</ul>")
            in_list = False
        body_lines.append(f"<p>{_inline(line)}</p>")

    _flush()
    return versions


def _minor_key(version: str) -> str:
    """Extract MAJOR.MINOR from a version string like '0.9.1'."""
    parts = version.split(".")
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[1]}"
    return version


def _group_by_minor(versions: list[ChangelogVersion]) -> list[ChangelogGroup]:
    """Group versions by MAJOR.MINOR, preserving order of first appearance."""
    groups: dict[str, ChangelogGroup] = {}
    order: list[str] = []
    for v in versions:
        key = _minor_key(v.version)
        if key not in groups:
            groups[key] = ChangelogGroup(label=f"{key}.x", slug=key, versions=[])
            order.append(key)
        groups[key].versions.append(v)
    return [groups[k] for k in order]


def _generate_changelog_html(versions: list[ChangelogVersion], output_dir: Path) -> list[str]:
    """Write HTML files to output_dir. Returns page_order list.

    Versions are grouped by MAJOR.MINOR — one page per group.
    index.html is a copy of the latest group's page.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    pages_dir = output_dir / "pages"
    pages_dir.mkdir(exist_ok=True)

    groups = _group_by_minor(versions)

    page_files: list[tuple[str, ChangelogGroup]] = []

    for g in groups:
        filename = f"pages/{g.slug}.html"
        page_files.append((filename, g))

    # page_order: group pages only (index.html is an alias for the latest)
    page_order = [fname for fname, _ in page_files]

    template = _jinja_env.get_template("changelog_page.html.j2")

    # Template data for sidebar groups
    sidebar_groups = [{"filename": fname, "basename": Path(fname).name, "label": g.label} for fname, g in page_files]

    def _render_page(group: ChangelogGroup, active_page: str, css_path: str, js_path: str, *, from_index: bool) -> str:
        title = group.versions[0].title if group.versions else group.label
        version_data = [{"title": v.title, "date": v.date, "body_html": v.body_html} for v in group.versions]
        return template.render(
            title=title,
            css_path=css_path,
            js_path=js_path,
            groups=sidebar_groups,
            active_page=active_page,
            from_index=from_index,
            versions=version_data,
        )

    # Write group pages (pages/ subdir — CSS/JS at ../../common/)
    for filename, g in page_files:
        (output_dir / filename).write_text(
            _render_page(g, filename, "../../common/css/viewer.css", "../../common/js/search.js", from_index=False),
            encoding="utf-8",
        )

    # index.html — same as latest group but with correct relative paths
    if groups:
        latest_group = groups[0]
        latest_page = page_files[0][0]
        (output_dir / "index.html").write_text(
            _render_page(
                latest_group, latest_page, "../common/css/viewer.css", "../common/js/search.js", from_index=True
            ),
            encoding="utf-8",
        )

    # Write page_order.txt manifest for runtime navigation
    (output_dir / "page_order.txt").write_text("\n".join(page_order), encoding="utf-8")

    return page_order


# noinspection PyUnusedImports
# Re-export for consumers that import from here
from app.core.content.template_env import get_page_order  # noqa: E402


def _get_project_root() -> Path:
    """Return project root directory."""
    return Path(__file__).resolve().parent.parent.parent.parent


def generate_changelog_html() -> None:
    """Entry point for Makefile — generate changelog HTML from CHANGELOG.md."""
    project_root = _get_project_root()
    md_path = project_root / "CHANGELOG.md"
    output_dir = project_root / "_build" / "runtime_content" / "html" / "changelog"

    md_text = md_path.read_text(encoding="utf-8")
    versions = _parse_changelog(md_text)
    page_order = _generate_changelog_html(versions, output_dir)
    logger.info("Generated %d changelog pages in %s", len(page_order), output_dir)
