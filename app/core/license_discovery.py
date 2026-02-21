"""License discovery and HTML generation pipeline.

Reads config.toml + uv.lock + .dist-info metadata to produce:
- registry.toml  — resolved state of all packages
- texts/         — extracted license texts (committed)
- html/          — generated HTML output (gitignored, bundled)
"""

import hashlib
import logging
import re
import shutil
import sys
import sysconfig
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tomli_w
from markupsafe import Markup, escape

from app.core.license_models import (
    DiscoveredPackage,
    LicenseConfig,
    LicenseRegistry,
    PackageCategory,
    PackageOverride,
    SystemDep,
)
from app.core.template_env import jinja_env as _jinja_env
from app.core.template_env import get_page_order as _get_page_order

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


def _get_project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _get_licenses_dir() -> Path:
    return _get_project_root() / "content" / "licenses"


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_config(licenses_dir: Path) -> LicenseConfig:
    """Parse config.toml into a LicenseConfig."""
    config_path = licenses_dir / "config.toml"
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))

    system_deps = [
        SystemDep(
            slug=sd["slug"],
            display=sd["display"],
            version=sd.get("version", ""),
            license_type=sd["license_type"],
            notes=sd.get("notes", ""),
            url=sd.get("url", ""),
        )
        for sd in data.get("system", [])
    ]

    package_overrides: dict[str, PackageOverride] = {}
    for pkg in data.get("package", []):
        name = pkg["name"]
        package_overrides[name] = PackageOverride(
            name=name,
            display=pkg.get("display", ""),
            category=pkg.get("category", ""),
            license_type=pkg.get("license_type", ""),
            homepage=pkg.get("homepage", ""),
            notes=pkg.get("notes", ""),
        )

    exclude = set(data.get("exclude", []))

    return LicenseConfig(
        system_deps=system_deps,
        package_overrides=package_overrides,
        exclude=exclude,
    )


# ---------------------------------------------------------------------------
# uv.lock parsing
# ---------------------------------------------------------------------------

def _parse_uv_lock(lock_path: Path) -> list[dict[str, Any]]:
    """Parse uv.lock, return list of package dicts with name, version, deps."""
    data = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    packages = []
    for pkg in data.get("package", []):
        name = pkg["name"]
        version = pkg["version"]
        deps = [d["name"] for d in pkg.get("dependencies", [])]
        packages.append({"name": name, "version": version, "deps": deps})
    return packages


def _compute_lock_hash(lock_path: Path) -> str:
    """Compute SHA-256 hash of uv.lock contents."""
    content = lock_path.read_bytes()
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


# ---------------------------------------------------------------------------
# .dist-info discovery
# ---------------------------------------------------------------------------

_LICENSE_FILENAMES = ("LICENSE", "LICENSE.txt", "LICENSE.md", "LICENSE-MIT",
                      "COPYING", "COPYING.txt")


def _find_dist_info(site_packages: Path, pkg_name: str) -> Path | None:
    """Find the .dist-info directory for a package."""
    normalized = pkg_name.lower().replace("-", "_").replace(".", "_")
    for d in site_packages.iterdir():
        if d.is_dir() and d.name.endswith(".dist-info"):
            stem = d.name[:-len(".dist-info")]
            m = re.match(r"^(.+?)-\d", stem)
            if m:
                dist_name = m.group(1).lower().replace("-", "_").replace(".", "_")
            else:
                dist_name = stem.lower().replace("-", "_").replace(".", "_")
            if dist_name == normalized:
                return d
    return None


def _find_license_file(dist_info: Path) -> str | None:
    """Find and read the license text from a .dist-info directory."""
    licenses_dir = dist_info / "licenses"
    if licenses_dir.is_dir():
        for name in _LICENSE_FILENAMES:
            candidate = licenses_dir / name
            if candidate.exists():
                return candidate.read_text(encoding="utf-8", errors="replace")
        for f in sorted(licenses_dir.iterdir()):
            if f.is_file() and f.suffix not in (".pyc", ".pyi"):
                return f.read_text(encoding="utf-8", errors="replace")

    for name in _LICENSE_FILENAMES:
        candidate = dist_info / name
        if candidate.exists():
            return candidate.read_text(encoding="utf-8", errors="replace")

    return None


def _extract_license_type(dist_info: Path) -> str:
    """Extract license type string from METADATA."""
    metadata_path = dist_info / "METADATA"
    if not metadata_path.exists():
        return "Unknown"

    text = metadata_path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        if line.startswith("License:") and len(line) > 10:
            lic = line[8:].strip()
            if lic and lic.lower() != "unknown":
                return lic
    for line in text.splitlines():
        if "Classifier: License :: OSI Approved ::" in line:
            return line.split("::")[-1].strip()
    return "See LICENSE file"


def _extract_homepage(dist_info: Path) -> str:
    """Extract homepage URL from METADATA."""
    metadata_path = dist_info / "METADATA"
    if not metadata_path.exists():
        return ""

    text = metadata_path.read_text(encoding="utf-8", errors="replace")
    # Check Project-URL fields first (modern format)
    for line in text.splitlines():
        low = line.lower()
        if low.startswith("project-url:"):
            parts = line[12:].split(",", 1)
            if len(parts) == 2:
                label = parts[0].strip().lower()
                url = parts[1].strip()
                if label in ("homepage", "home", "repository", "source"):
                    return url
    # Fall back to Home-page field
    for line in text.splitlines():
        if line.startswith("Home-page:"):
            url = line[10:].strip()
            if url and url.lower() != "unknown":
                return url
    return ""


# ---------------------------------------------------------------------------
# Categorization
# ---------------------------------------------------------------------------

def _slug(name: str) -> str:
    """Convert package name to filename slug."""
    return name.lower().replace("_", "-").replace(".", "-")


def _display_name(name: str, overrides: dict[str, PackageOverride]) -> str:
    """Get display name for a package."""
    override = overrides.get(name)
    if override and override.display:
        return override.display
    return name


def _categorize_packages(
    packages: list[dict],
    dev_deps: set[str],
    config: LicenseConfig,
    runtime_deps: set[str],
) -> dict[str, PackageCategory]:
    """Return name -> PackageCategory mapping.

    - Runtime: packages in greeting-cards' direct deps from uv.lock
    - Development: packages in pyproject.toml [dependency-groups] dev
    - Transitive: everything else
    - Config overrides can force a category
    """
    categories: dict[str, PackageCategory] = {}
    for pkg in packages:
        name = pkg["name"]
        if name == "greeting-cards":
            continue
        if name in runtime_deps:
            categories[name] = PackageCategory.RUNTIME
        elif name in dev_deps:
            categories[name] = PackageCategory.DEVELOPMENT
        else:
            categories[name] = PackageCategory.TRANSITIVE

    # Apply config overrides
    for name, override in config.package_overrides.items():
        if override.category and name in categories:
            categories[name] = PackageCategory(override.category)

    return categories


def _build_reverse_deps(packages: list[dict]) -> dict[str, set[str]]:
    """Build reverse dependency map: package -> set of packages that require it."""
    reverse: dict[str, set[str]] = {}
    for pkg in packages:
        for dep in pkg["deps"]:
            reverse.setdefault(dep, set()).add(pkg["name"])
    return reverse


def _required_by_text(
    name: str,
    category: PackageCategory,
    reverse_deps: dict[str, set[str]],
    overrides: dict[str, PackageOverride],
) -> str:
    """Return human-readable 'Required By' text."""
    if category in (PackageCategory.RUNTIME, PackageCategory.DEVELOPMENT):
        return "\u2014"

    parents = reverse_deps.get(name, set()) - {"greeting-cards"}
    if not parents:
        return "\u2014"

    return ", ".join(sorted(_display_name(p, overrides) for p in parents))


# ---------------------------------------------------------------------------
# Registry sync
# ---------------------------------------------------------------------------

def _get_site_packages() -> Path:
    """Find the site-packages directory."""
    site_packages = Path(sysconfig.get_path("purelib"))
    if not site_packages.exists():
        project_root = _get_project_root()
        site_packages = (
            project_root / ".venv" / "lib"
            / f"python{sys.version_info.major}.{sys.version_info.minor}"
            / "site-packages"
        )
    return site_packages


def sync_registry() -> LicenseRegistry:
    """Full discovery pipeline: config + uv.lock + .dist-info -> registry.toml + texts/.

    Entry point for `make licenses-sync`.
    """
    project_root = _get_project_root()
    licenses_dir = _get_licenses_dir()
    lock_path = project_root / "uv.lock"

    config = load_config(licenses_dir)
    uv_lock_hash = _compute_lock_hash(lock_path)
    site_packages = _get_site_packages()

    # Parse uv.lock
    packages = _parse_uv_lock(lock_path)

    # Find greeting-cards' direct deps from uv.lock (= Runtime)
    runtime_deps: set[str] = set()
    for pkg in packages:
        if pkg["name"] == "greeting-cards":
            runtime_deps = set(pkg["deps"])
            break

    # Dev deps from pyproject.toml
    pyproject = tomllib.loads(
        (project_root / "pyproject.toml").read_text(encoding="utf-8")
    )
    dev_names: set[str] = set()
    for dep_str in pyproject.get("dependency-groups", {}).get("dev", []):
        name = dep_str.split(">=")[0].split("==")[0].split("<")[0].strip().lower()
        dev_names.add(name)

    # Categorize
    categories = _categorize_packages(packages, dev_names, config, runtime_deps)
    reverse_deps = _build_reverse_deps(packages)

    # Read existing registry for version comparison
    existing_versions = _read_existing_versions(licenses_dir)

    # Ensure texts/ directory exists
    texts_dir = licenses_dir / "texts"
    texts_dir.mkdir(parents=True, exist_ok=True)

    # Discover packages
    discovered: list[DiscoveredPackage] = []
    for pkg in packages:
        name = pkg["name"]
        if name == "greeting-cards" or name in config.exclude:
            continue

        category = categories.get(name, PackageCategory.TRANSITIVE)
        pkg_slug = _slug(name)
        text_file = f"texts/{pkg_slug}.txt"

        dist_info = _find_dist_info(site_packages, name)
        license_text = ""
        license_type = "Unknown"
        homepage = ""

        if dist_info:
            license_type = _extract_license_type(dist_info)
            homepage = _extract_homepage(dist_info)
            # Only re-extract text if version changed or file missing
            text_path = licenses_dir / text_file
            if (not text_path.exists()
                    or existing_versions.get(name) != pkg["version"]):
                license_text = _find_license_file(dist_info) or ""
                if license_text:
                    text_path.write_text(license_text, encoding="utf-8")
                else:
                    logger.warning("No license text found for %s", name)
            # If file exists and version unchanged, keep it
        else:
            logger.warning("No .dist-info found for %s", name)

        # Fall back to manual license file if no extracted text exists
        if not (licenses_dir / text_file).exists():
            manual_path = licenses_dir / "manual" / f"{pkg_slug}.txt"
            if manual_path.exists():
                text_file = f"manual/{pkg_slug}.txt"

        # Apply config overrides
        override = config.package_overrides.get(name)
        display = _display_name(name, config.package_overrides)
        if override:
            if override.license_type:
                license_type = override.license_type
            if override.homepage:
                homepage = override.homepage

        dp = DiscoveredPackage(
            name=name,
            slug=pkg_slug,
            display=display,
            version=pkg["version"],
            license_type=license_type,
            category=category,
            required_by=_required_by_text(
                name, category, reverse_deps, config.package_overrides
            ),
            text_file=text_file,
            homepage=homepage,
        )
        discovered.append(dp)

    # Sort: Runtime, Development, Transitive; alpha within each
    category_order = {
        PackageCategory.RUNTIME: 0,
        PackageCategory.DEVELOPMENT: 1,
        PackageCategory.TRANSITIVE: 2,
    }
    discovered.sort(
        key=lambda p: (category_order.get(p.category, 9), p.display.lower())
    )

    registry = LicenseRegistry(
        uv_lock_hash=uv_lock_hash,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        system_deps=config.system_deps,
        packages=discovered,
    )

    _write_registry_toml(licenses_dir, registry)
    logger.info(
        "Synced registry: %d packages, %d system deps",
        len(discovered), len(config.system_deps),
    )
    return registry


def _read_existing_versions(licenses_dir: Path) -> dict[str, str]:
    """Read package versions from existing registry.toml for change detection."""
    registry_path = licenses_dir / "registry.toml"
    if not registry_path.exists():
        return {}
    data = tomllib.loads(registry_path.read_text(encoding="utf-8"))
    return {pkg["name"]: pkg["version"] for pkg in data.get("package", [])}


def _write_registry_toml(licenses_dir: Path, registry: LicenseRegistry) -> None:
    """Serialize LicenseRegistry to registry.toml."""
    data: dict = {
        "meta": {
            "uv_lock_hash": registry.uv_lock_hash,
            "generated_at": registry.generated_at,
        },
        "system": [
            {
                "slug": sd.slug,
                "display": sd.display,
                "version": sd.version,
                "license_type": sd.license_type,
                "notes": sd.notes,
                "url": sd.url,
                "text_file": f"manual/{sd.slug}.txt",
            }
            for sd in registry.system_deps
        ],
        "package": [
            {
                "name": pkg.name,
                "slug": pkg.slug,
                "display": pkg.display,
                "version": pkg.version,
                "license_type": pkg.license_type,
                "category": pkg.category.value,
                "required_by": pkg.required_by,
                "text_file": pkg.text_file,
                "homepage": pkg.homepage,
            }
            for pkg in registry.packages
        ],
    }

    registry_path = licenses_dir / "registry.toml"
    registry_path.write_bytes(tomli_w.dumps(data).encode("utf-8"))


def _read_registry_toml(licenses_dir: Path) -> LicenseRegistry:
    """Deserialize registry.toml into a LicenseRegistry."""
    registry_path = licenses_dir / "registry.toml"
    data = tomllib.loads(registry_path.read_text(encoding="utf-8"))

    system_deps = [
        SystemDep(
            slug=sd["slug"],
            display=sd["display"],
            version=sd.get("version", ""),
            license_type=sd["license_type"],
            notes=sd.get("notes", ""),
            url=sd.get("url", ""),
        )
        for sd in data.get("system", [])
    ]

    packages = [
        DiscoveredPackage(
            name=pkg["name"],
            slug=pkg["slug"],
            display=pkg["display"],
            version=pkg["version"],
            license_type=pkg["license_type"],
            category=PackageCategory(pkg["category"]),
            required_by=pkg["required_by"],
            text_file=pkg["text_file"],
            homepage=pkg.get("homepage", ""),
        )
        for pkg in data.get("package", [])
    ]

    meta = data.get("meta", {})
    return LicenseRegistry(
        uv_lock_hash=meta.get("uv_lock_hash", ""),
        generated_at=meta.get("generated_at", ""),
        system_deps=system_deps,
        packages=packages,
    )


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
        {"slug": "greeting-cards", "display": "Greeting Cards",
         "href": "greeting-cards.html"},
        {"slug": "system", "display": "System", "href": "system.html"},
        {"slug": "runtime", "display": "Runtime", "href": "runtime.html"},
        {"slug": "development", "display": "Development",
         "href": "development.html"},
        {"slug": "transitive", "display": "Transitive",
         "href": "transitive.html"},
    ]
    return items


def generate_licenses_html() -> None:
    """Generate licenses HTML from registry.toml + text files.

    Entry point for `make licenses`. Calls sync_registry() first,
    then generates HTML output to _runtime_content/html/licenses/.
    """
    licenses_dir = _get_licenses_dir()
    project_root = _get_project_root()

    # Always sync first to ensure registry is up to date
    registry = sync_registry()

    # Generate HTML
    html_dir = project_root / "_runtime_content" / "html" / "licenses"
    _write_html(html_dir, licenses_dir, registry)

    # Write page_order.txt manifest for runtime navigation
    page_order = [item["href"] for item in _build_nav_items()]
    (html_dir / "page_order.txt").write_text(
        "\n".join(page_order), encoding="utf-8"
    )

    logger.info(
        "Generated %d license entries across %d pages in %s",
        len(registry.packages),
        len(_CATEGORY_PAGES) + 3,  # +3 for index, greeting-cards, system
        html_dir,
    )


def _write_html(
    html_dir: Path,
    licenses_dir: Path,
    registry: LicenseRegistry,
) -> None:
    """Write all HTML files to html_dir (flat structure, no pages/ subdir)."""
    if html_dir.exists():
        shutil.rmtree(html_dir)
    html_dir.mkdir(parents=True)

    css_path = "../common/css/viewer.css"
    js_path = "../common/js/search.js"
    nav_items = _build_nav_items()

    # Read app license from repo root LICENSE file
    project_root = _get_project_root()
    app_license_text = (project_root / "LICENSE").read_text(
        encoding="utf-8"
    ).strip()

    # --- Index page ---
    pkg_dicts = [
        {
            "slug": pkg.slug, "display": pkg.display,
            "version": pkg.version, "license_type": pkg.license_type,
            "category": pkg.category.value, "required_by": pkg.required_by,
            "homepage": pkg.homepage,
            "page": _category_page_for(pkg.category),
        }
        for pkg in registry.packages
    ]
    system_dicts = [
        {
            "slug": dep.slug, "display": dep.display,
            "version": dep.version, "license": dep.license_type,
            "notes": dep.notes, "url": dep.url,
        }
        for dep in registry.system_deps
    ]

    index_template = _jinja_env.get_template("licenses_index.html.j2")
    index_html = index_template.render(
        title="Open-Source Licenses", css_path=css_path, js_path=js_path,
        nav_items=nav_items, active_slug="index",
        system_deps=system_dicts, pkg_infos=pkg_dicts,
    )
    (html_dir / "index.html").write_text(index_html, encoding="utf-8")

    page_template = _jinja_env.get_template("licenses_page.html.j2")

    # --- Greeting Cards page ---
    gc_html = page_template.render(
        title="Greeting Cards — License", css_path=css_path, js_path=js_path,
        nav_items=nav_items, active_slug="greeting-cards",
        page_title="Greeting Cards",
        entries=[{
            "slug": "greeting-cards", "display": "Greeting Cards",
            "version": "", "license_type": "BSD 3-Clause",
            "license_text": app_license_text,
            "homepage": "https://github.com/skaymakca/GreetingCards",
            "notes": "",
        }],
    )
    (html_dir / "greeting-cards.html").write_text(gc_html, encoding="utf-8")

    # --- System page ---
    system_entries = []
    for dep in registry.system_deps:
        text_path = licenses_dir / "manual" / f"{dep.slug}.txt"
        dep_text = (text_path.read_text(encoding="utf-8").strip()
                    if text_path.exists() else "License text not available.")
        system_entries.append({
            "slug": dep.slug, "display": dep.display,
            "version": dep.version, "license_type": dep.license_type,
            "license_text": dep_text, "homepage": dep.url,
            "notes": dep.notes,
        })

    sys_html = page_template.render(
        title="System Dependencies — Licenses", css_path=css_path,
        js_path=js_path,
        nav_items=nav_items, active_slug="system",
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
            text_path = licenses_dir / pkg.text_file
            pkg_text = ""
            if text_path.exists():
                pkg_text = text_path.read_text(encoding="utf-8").strip()
            if not pkg_text:
                pkg_text = "License text not available."
            entries.append({
                "slug": pkg.slug, "display": pkg.display,
                "version": pkg.version, "license_type": pkg.license_type,
                "license_text": pkg_text, "homepage": pkg.homepage,
                "notes": "",
            })

        slug = filename.replace(".html", "")
        cat_html = page_template.render(
            title=f"{page_title} — Licenses", css_path=css_path,
            js_path=js_path,
            nav_items=nav_items, active_slug=slug,
            page_title=page_title,
            entries=entries,
        )
        (html_dir / filename).write_text(cat_html, encoding="utf-8")
