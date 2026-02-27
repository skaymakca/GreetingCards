"""License registry sync pipeline.

Reads content/licenses/ (config.toml, manual/) + uv.lock + .dist-info metadata
to produce generated output under _build/licenses/:
- _build/licenses/registry.toml  — resolved state of all packages
- _build/licenses/texts/         — extracted license texts

Entry point: sync_registry() — called by `make licenses-sync`.
"""

import hashlib
import logging
import re
import sys
import sysconfig
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import tomli_w

from app.core.content.license_models import (
    DiscoveredPackage,
    LicenseConfig,
    LicenseRegistry,
    PackageCategory,
    PackageOverride,
    SystemDep,
)
from app.core.paths import get_project_root as _get_project_root

logger = logging.getLogger(__name__)


def get_licenses_source_dir() -> Path:
    """Return content/licenses/ — committed source files (config.toml, manual/)."""
    return _get_project_root() / "content" / "licenses"


def get_licenses_build_dir() -> Path:
    """Return _build/licenses/ — generated files (registry.toml, texts/)."""
    return _get_project_root() / "_build" / "licenses"


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


# noinspection DuplicatedCode
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

_LICENSE_FILENAMES = ("LICENSE", "LICENSE.txt", "LICENSE.md", "LICENSE-MIT", "COPYING", "COPYING.txt")


def _find_dist_info(site_packages: Path, pkg_name: str) -> Path | None:
    """Find the .dist-info directory for a package."""
    normalized = pkg_name.lower().replace("-", "_").replace(".", "_")
    for d in site_packages.iterdir():
        if d.is_dir() and d.name.endswith(".dist-info"):
            stem = d.name[: -len(".dist-info")]
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

    lines = metadata_path.read_text(encoding="utf-8", errors="replace").splitlines()
    classifier_fallback: str | None = None
    for line in lines:
        if line.startswith("License:") and len(line) > 10:
            lic = line[8:].strip()
            if lic and lic.lower() != "unknown":
                return lic
        if classifier_fallback is None and "Classifier: License :: OSI Approved ::" in line:
            classifier_fallback = line.split("::")[-1].strip()
    return classifier_fallback or "See LICENSE file"


def _extract_homepage(dist_info: Path) -> str:
    """Extract homepage URL from METADATA."""
    metadata_path = dist_info / "METADATA"
    if not metadata_path.exists():
        return ""

    lines = metadata_path.read_text(encoding="utf-8", errors="replace").splitlines()
    home_page_fallback: str | None = None
    for line in lines:
        low = line.lower()
        # Check Project-URL fields first (modern format)
        if low.startswith("project-url:"):
            parts = line[12:].split(",", 1)
            if len(parts) == 2:
                label = parts[0].strip().lower()
                url = parts[1].strip()
                if label in ("homepage", "home", "repository", "source"):
                    return url
        # Capture Home-page field as fallback
        if home_page_fallback is None and line.startswith("Home-page:"):
            url = line[10:].strip()
            if url and url.lower() != "unknown":
                home_page_fallback = url
    return home_page_fallback or ""


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


# noinspection GrazieInspection
def _categorize_packages(
    packages: list[dict[str, Any]],
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


def _build_reverse_deps(packages: list[dict[str, Any]]) -> dict[str, set[str]]:
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
            project_root
            / ".venv"
            / "lib"
            / f"python{sys.version_info.major}.{sys.version_info.minor}"
            / "site-packages"
        )
    return site_packages


# noinspection PyUnusedLocal,GrazieInspection
def sync_registry() -> LicenseRegistry:
    """Full discovery pipeline: config + uv.lock + .dist-info -> registry.toml + texts/.

    Entry point for `make licenses-sync`.
    """
    project_root = _get_project_root()
    source_dir = get_licenses_source_dir()
    build_dir = get_licenses_build_dir()
    lock_path = project_root / "uv.lock"

    config = load_config(source_dir)
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
    pyproject = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))
    dev_names: set[str] = set()
    for dep_str in pyproject.get("dependency-groups", {}).get("dev", []):
        from packaging.requirements import Requirement

        req = Requirement(dep_str)
        dev_names.add(req.name.lower())

    # Categorize
    categories = _categorize_packages(packages, dev_names, config, runtime_deps)
    reverse_deps = _build_reverse_deps(packages)

    # Read existing registry for version comparison
    existing_versions = _read_existing_versions(build_dir)

    # Ensure texts/ directory exists
    texts_dir = build_dir / "texts"
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
            text_path = build_dir / text_file
            if not text_path.exists() or existing_versions.get(name) != pkg["version"]:
                license_text = _find_license_file(dist_info) or ""
                if license_text:
                    text_path.write_text(license_text, encoding="utf-8")
                else:
                    logger.warning("No license text found for %s", name)
            # If file exists and version unchanged, keep it
        else:
            logger.warning("No .dist-info found for %s", name)

        # Fall back to manual license file if no extracted text exists
        if not (build_dir / text_file).exists():
            manual_path = source_dir / "manual" / f"{pkg_slug}.txt"
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
            required_by=_required_by_text(name, category, reverse_deps, config.package_overrides),
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
    discovered.sort(key=lambda p: (category_order.get(p.category, 9), p.display.lower()))

    registry = LicenseRegistry(
        uv_lock_hash=uv_lock_hash,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        system_deps=config.system_deps,
        packages=discovered,
    )

    _write_registry_toml(build_dir, registry)
    logger.info(
        "Synced registry: %d packages, %d system deps",
        len(discovered),
        len(config.system_deps),
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
