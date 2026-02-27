"""Help page generation — converts Markdown help pages to HTML.

Reads .md files from content/html/help/, derives navigation order from the
filename prefix (e.g. ``1 - index.md``), renders Markdown to HTML, and
writes to _build/runtime_content/html/help/ via Jinja2 templates.

Filename convention::

    <order> - <slug>.md

Where ``<order>`` is a positive integer and ``<slug>`` becomes the HTML
filename (e.g. ``getting-started.html``).  The pipeline will error out if
any filename doesn't match the pattern, or if there are gaps or duplicates
in the numbering.
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import markdown

from app.core.content.template_env import jinja_env as _jinja_env

logger = logging.getLogger(__name__)

# Pattern: "<number> - <slug>.md"
_FILENAME_RE = re.compile(r"^(\d+) - (.+)\.md$")


@dataclass
class _HelpPage:
    """A parsed help page with frontmatter metadata."""

    slug: str  # e.g. "getting-started"
    title: str  # e.g. "Getting Started"
    nav_order: int  # sorting key from filename prefix
    body_html: str  # rendered HTML content


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Parse YAML frontmatter from a Markdown file.

    Simple parser: splits on --- delimiters, extracts key: value pairs.
    Returns (metadata_dict, remaining_body).
    """
    if not text.startswith("---"):
        return {}, text

    # Find the closing ---
    end = text.find("---", 3)
    if end == -1:
        return {}, text

    front = text[3:end].strip()
    body = text[end + 3 :].strip()

    metadata: dict[str, str] = {}
    for line in front.splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^(\w+)\s*:\s*(.+)$", line)
        if match:
            metadata[match.group(1)] = match.group(2).strip()

    return metadata, body


# noinspection GrazieInspection
def _validate_numbering(numbers: list[int], filenames: list[str]) -> None:
    """Validate that file numbers form a contiguous 1..N sequence.

    Raises ValueError on duplicates, gaps, or numbers not starting at 1.
    """
    if not numbers:
        return

    # Check for duplicates
    seen: dict[int, str] = {}
    for num, fname in zip(numbers, filenames, strict=False):
        if num in seen:
            raise ValueError(f"Duplicate help page number {num}: '{fname}' and '{seen[num]}'")
        seen[num] = fname

    sorted_nums = sorted(numbers)

    # Must start at 1
    if sorted_nums[0] != 1:
        raise ValueError(
            f"Help page numbering must start at 1, but lowest is {sorted_nums[0]} ('{seen[sorted_nums[0]]}')"
        )

    # Check for gaps
    for i in range(1, len(sorted_nums)):
        expected = sorted_nums[i - 1] + 1
        actual = sorted_nums[i]
        if actual != expected:
            raise ValueError(
                f"Gap in help page numbering: expected {expected} "
                f"after '{seen[sorted_nums[i - 1]]}', "
                f"but next is {actual} ('{seen[actual]}')"
            )


def _read_help_pages(content_dir: Path) -> list[_HelpPage]:
    """Read all .md files from the help directory and parse them.

    Filenames must follow the ``<order> - <slug>.md`` convention.
    Raises ValueError if any filename is malformed or numbering is invalid.
    """
    help_dir = content_dir / "help"
    pages: list[_HelpPage] = []
    numbers: list[int] = []
    filenames: list[str] = []

    md_converter = markdown.Markdown(extensions=["tables"])

    for md_file in sorted(help_dir.glob("*.md")):
        match = _FILENAME_RE.match(md_file.name)
        if not match:
            raise ValueError(
                f"Help page filename '{md_file.name}' doesn't match expected pattern '<number> - <slug>.md'"
            )

        nav_order = int(match.group(1))
        slug = match.group(2)
        numbers.append(nav_order)
        filenames.append(md_file.name)

        text = md_file.read_text(encoding="utf-8")
        metadata, body = _parse_frontmatter(text)

        title = metadata.get("title", slug.replace("-", " ").title())

        md_converter.reset()
        body_html = md_converter.convert(body)

        pages.append(
            _HelpPage(
                slug=slug,
                title=title,
                nav_order=nav_order,
                body_html=body_html,
            )
        )

    _validate_numbering(numbers, filenames)
    pages.sort(key=lambda p: p.nav_order)
    return pages


def generate_help_html() -> None:
    """Entry point for Makefile — generate help HTML from Markdown pages."""
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    content_dir = project_root / "content" / "html"
    output_dir = project_root / "_build" / "runtime_content" / "html" / "help"

    pages = _read_help_pages(content_dir)
    if not pages:
        logger.warning("No help pages found in %s", content_dir / "help")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    pages_dir = output_dir / "pages"
    pages_dir.mkdir(exist_ok=True)

    template = _jinja_env.get_template("help_page.html.j2")

    # Build nav list for sidebar
    # Index page is at help/index.html, other pages at help/pages/<slug>.html
    nav_items = []
    for page in pages:
        if page.slug == "index":
            nav_items.append(
                {
                    "slug": page.slug,
                    "title": page.title,
                    "href": "index.html",
                    "href_from_pages": "../index.html",
                }
            )
        else:
            nav_items.append(
                {
                    "slug": page.slug,
                    "title": page.title,
                    "href": f"pages/{page.slug}.html",
                    "href_from_pages": f"{page.slug}.html",
                }
            )

    # Render each page
    for page in pages:
        if page.slug == "index":
            # Index page: nav hrefs are child-relative
            nav = [{"slug": n["slug"], "title": n["title"], "href": n["href"]} for n in nav_items]
            css_path = "../common/css/viewer.css"
            js_path = "../common/js/search.js"
            out_path = output_dir / "index.html"
        else:
            # Sub-pages: nav hrefs are sibling-relative
            nav = [{"slug": n["slug"], "title": n["title"], "href": n["href_from_pages"]} for n in nav_items]
            css_path = "../../common/css/viewer.css"
            js_path = "../../common/js/search.js"
            out_path = pages_dir / f"{page.slug}.html"

        html = template.render(
            title=page.title,
            css_path=css_path,
            js_path=js_path,
            nav=nav,
            active_slug=page.slug,
            body_html=page.body_html,
        )
        out_path.write_text(html, encoding="utf-8")

    # Write page_order.txt manifest for runtime navigation
    order: list[str] = []
    for page in pages:
        if page.slug == "index":
            order.append("index.html")
        else:
            order.append(f"pages/{page.slug}.html")
    (output_dir / "page_order.txt").write_text("\n".join(order), encoding="utf-8")

    logger.info("Generated %d help pages in %s", len(pages), output_dir)


# noinspection PyUnusedImports
# Re-export for consumers that import from here
from app.core.content.template_env import get_page_order  # noqa: E402
