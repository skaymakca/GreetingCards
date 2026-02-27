"""License HTML generation pipeline.

Reads _build/licenses/registry.toml → generates HTML via Jinja2.
Entry point: generate_licenses_html() — called by `make licenses` and `make content`.
"""

import logging
import re
import shutil
from pathlib import Path

from markupsafe import Markup, escape

from app.core.config import GITHUB_URL
from app.core.content.license_models import LicenseRegistry, PackageCategory
from app.core.content.license_sync import (
    _get_licenses_build_dir,
    _get_licenses_source_dir,
    _get_project_root,
    sync_registry,
)
from app.core.content.template_env import get_page_order as _get_page_order
from app.core.content.template_env import jinja_env as _jinja_env

logger = logging.getLogger(__name__)


def _linkify(text: str) -> Markup:
    """Convert plain-text URLs to clickable links."""
    escaped = str(escape(text))

    def _make_link(m: re.Match) -> str:
        url_escaped = m.group(1)
        url_raw = url_escaped.replace("&amp;", "&")
        return f'<a href="{url_raw}">{url_escaped}</a>'

    result = re.sub(
        r'(https?://[^\s<>"\')\]]+)',
        _make_link,
        escaped,
    )
    return Markup(result)


_jinja_env.filters["linkify"] = _linkify

# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

# Category pages: maps category enum(s) to (filename, display title)
_CATEGORY_PAGES: list[tuple[tuple[PackageCategory, ...], str, str]] = [
    ((PackageCategory.RUNTIME,), "runtime.html", "Runtime Dependencies"),
    ((PackageCategory.DEVELOPMENT,), "development.html", "Development Dependencies"),
    ((PackageCategory.TRANSITIVE,), "transitive.html", "Transitive Dependencies"),
]


def _category_page_for(category: PackageCategory) -> str:
    """Return the HTML filename for a given category."""
    for cats, filename, _ in _CATEGORY_PAGES:
        if category in cats:
            return filename
    return "transitive.html"


def get_page_order(base_path: Path) -> list[str]:
    """Read page order from the generated manifest file."""
    order = _get_page_order(base_path)
    if order != ["index.html"]:
        return order
    # Fallback to hardcoded nav order when manifest is missing
    return [item["href"] for item in _build_nav_items()]


def _build_nav_items() -> list[dict[str, str]]:
    """Build flat sidebar navigation items."""
    items = [
        {"slug": "index", "display": "Home", "href": "index.html"},
        {"slug": "greeting-cards", "display": "Greeting Cards", "href": "greeting-cards.html"},
        {"slug": "system", "display": "System", "href": "system.html"},
        {"slug": "runtime", "display": "Runtime", "href": "runtime.html"},
        {"slug": "development", "display": "Development", "href": "development.html"},
        {"slug": "transitive", "display": "Transitive", "href": "transitive.html"},
    ]
    return items


def generate_licenses_html() -> None:
    """Generate licenses HTML from registry.toml + text files.

    Entry point for `make licenses`. Calls sync_registry() first,
    then generates HTML output to _build/runtime_content/html/licenses/.
    """
    source_dir = _get_licenses_source_dir()
    build_dir = _get_licenses_build_dir()
    project_root = _get_project_root()

    # Always sync first to ensure registry is up to date
    registry = sync_registry()

    # Generate HTML
    html_dir = project_root / "_build" / "runtime_content" / "html" / "licenses"
    _write_html(html_dir, source_dir, build_dir, registry)

    # Write page_order.txt manifest for runtime navigation
    page_order = [item["href"] for item in _build_nav_items()]
    (html_dir / "page_order.txt").write_text("\n".join(page_order), encoding="utf-8")

    logger.info(
        "Generated %d license entries across %d pages in %s",
        len(registry.packages),
        len(_CATEGORY_PAGES) + 3,  # +3 for index, greeting-cards, system
        html_dir,
    )


def _write_html(
    html_dir: Path,
    source_dir: Path,
    build_dir: Path,
    registry: LicenseRegistry,
) -> None:
    """Write all HTML files to html_dir (flat structure, no pages/ subdir).

    source_dir: content/licenses/ (config.toml, manual/)
    build_dir:  _build/licenses/ (registry.toml, texts/)
    """
    if html_dir.exists():
        shutil.rmtree(html_dir)
    html_dir.mkdir(parents=True)

    css_path = "../common/css/viewer.css"
    js_path = "../common/js/search.js"
    nav_items = _build_nav_items()

    # Read app license from repo root LICENSE file
    project_root = _get_project_root()
    app_license_text = (project_root / "LICENSE").read_text(encoding="utf-8").strip()

    # --- Index page ---
    pkg_dicts = [
        {
            "slug": pkg.slug,
            "display": pkg.display,
            "version": pkg.version,
            "license_type": pkg.license_type,
            "category": pkg.category.value,
            "required_by": pkg.required_by,
            "homepage": pkg.homepage,
            "page": _category_page_for(pkg.category),
        }
        for pkg in registry.packages
    ]
    system_dicts = [
        {
            "slug": dep.slug,
            "display": dep.display,
            "version": dep.version,
            "license": dep.license_type,
            "notes": dep.notes,
            "url": dep.url,
        }
        for dep in registry.system_deps
    ]

    index_template = _jinja_env.get_template("licenses_index.html.j2")
    index_html = index_template.render(
        title="Open-Source Licenses",
        css_path=css_path,
        js_path=js_path,
        nav_items=nav_items,
        active_slug="index",
        system_deps=system_dicts,
        pkg_infos=pkg_dicts,
    )
    (html_dir / "index.html").write_text(index_html, encoding="utf-8")

    page_template = _jinja_env.get_template("licenses_page.html.j2")

    # --- Greeting Cards page ---
    gc_html = page_template.render(
        title="Greeting Cards — License",
        css_path=css_path,
        js_path=js_path,
        nav_items=nav_items,
        active_slug="greeting-cards",
        page_title="Greeting Cards",
        entries=[
            {
                "slug": "greeting-cards",
                "display": "Greeting Cards",
                "version": "",
                "license_type": "BSD 3-Clause",
                "license_text": app_license_text,
                "homepage": GITHUB_URL,
                "notes": "",
            }
        ],
    )
    (html_dir / "greeting-cards.html").write_text(gc_html, encoding="utf-8")

    # --- System page ---
    system_entries = []
    for dep in registry.system_deps:
        text_path = source_dir / "manual" / f"{dep.slug}.txt"
        dep_text = (
            text_path.read_text(encoding="utf-8").strip() if text_path.exists() else "License text not available."
        )
        system_entries.append(
            {
                "slug": dep.slug,
                "display": dep.display,
                "version": dep.version,
                "license_type": dep.license_type,
                "license_text": dep_text,
                "homepage": dep.url,
                "notes": dep.notes,
            }
        )

    sys_html = page_template.render(
        title="System Dependencies — Licenses",
        css_path=css_path,
        js_path=js_path,
        nav_items=nav_items,
        active_slug="system",
        page_title="System Dependencies",
        entries=system_entries,
    )
    (html_dir / "system.html").write_text(sys_html, encoding="utf-8")

    # --- Category pages ---
    for cats, filename, page_title in _CATEGORY_PAGES:
        entries = []
        for pkg in registry.packages:
            if pkg.category not in cats:
                continue
            # text_file is either "texts/slug.txt" (build_dir) or "manual/slug.txt" (source_dir)
            if pkg.text_file.startswith("manual/"):
                text_path = source_dir / pkg.text_file
            else:
                text_path = build_dir / pkg.text_file
            pkg_text = ""
            if text_path.exists():
                pkg_text = text_path.read_text(encoding="utf-8").strip()
            if not pkg_text:
                pkg_text = "License text not available."
            entries.append(
                {
                    "slug": pkg.slug,
                    "display": pkg.display,
                    "version": pkg.version,
                    "license_type": pkg.license_type,
                    "license_text": pkg_text,
                    "homepage": pkg.homepage,
                    "notes": "",
                }
            )

        slug = filename.replace(".html", "")
        cat_html = page_template.render(
            title=f"{page_title} — Licenses",
            css_path=css_path,
            js_path=js_path,
            nav_items=nav_items,
            active_slug=slug,
            page_title=page_title,
            entries=entries,
        )
        (html_dir / filename).write_text(cat_html, encoding="utf-8")
