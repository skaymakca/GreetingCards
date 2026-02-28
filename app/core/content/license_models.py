"""Dataclasses for the license discovery and generation pipeline."""

from dataclasses import dataclass, field
from enum import Enum


class PackageCategory(Enum):
    RUNTIME = "Runtime"  # app imports these
    DEVELOPMENT = "Development"  # dev/build tools
    TRANSITIVE = "Transitive"  # pulled in by others


@dataclass
class SystemDep:
    slug: str
    display: str
    version: str
    license_type: str
    notes: str
    url: str = ""


@dataclass
class PackageOverride:
    """Partial package entry from config.toml — overrides auto-discovered values."""

    name: str
    display: str = ""
    category: str = ""  # PackageCategory value string, or empty for auto
    license_type: str = ""
    homepage: str = ""
    notes: str = ""


@dataclass
class LicenseConfig:
    system_deps: list[SystemDep]
    package_overrides: dict[str, PackageOverride] = field(default_factory=dict)
    exclude: set[str] = field(default_factory=set)


@dataclass
class DiscoveredPackage:
    name: str
    slug: str
    display: str
    version: str
    license_type: str
    category: PackageCategory
    required_by: str
    text_file: str  # relative path: "texts/anyio.txt" or "manual/python.txt"
    homepage: str = ""
    license_text: str = ""  # populated at discovery, written to text_file


@dataclass
class LicenseRegistry:
    uv_lock_hash: str
    generated_at: str
    system_deps: list[SystemDep]
    packages: list[DiscoveredPackage]
