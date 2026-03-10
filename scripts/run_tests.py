"""Test runner script — unified interface for running pytest with scopes and options.

Usage via Makefile:
    make test                       # show help
    make test T=default             # core + gui + scripts (no integration)
    make test T="core --cov"        # core tests with coverage
    make test T="gui scripts -x"   # gui + scripts, stop on first failure

Direct invocation:
    uv run python scripts/run_tests.py default
    uv run python scripts/run_tests.py core --cov --open
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
COV_DIR = PROJECT_ROOT / "_build" / "coverage"

SCOPES: dict[str, list[str]] = {
    "core": ["tests/core/"],
    "gui": ["tests/gui/"],
    "scripts": ["tests/scripts/"],
    "integration": ["tests/integration/"],
}

# Composite scopes
SCOPE_DEFAULT = ["core", "gui", "scripts"]
SCOPE_ALL = ["core", "gui", "scripts", "integration"]

# Scopes that automatically add --run-integration
INTEGRATION_SCOPES = {"integration", "all"}


@dataclass
class ResolvedScopes:
    """Result of resolving user-specified scope names."""

    directories: list[str]
    run_integration: bool


def resolve_scopes(scope_names: list[str]) -> ResolvedScopes:
    """Resolve scope names to test directories and flags.

    Args:
        scope_names: List of scope names (e.g., ["core", "gui"]).

    Returns:
        ResolvedScopes with deduplicated directories and integration flag.
    """
    if not scope_names:
        return ResolvedScopes(directories=[], run_integration=False)

    run_integration = False
    directories: list[str] = []
    seen: set[str] = set()

    for name in scope_names:
        if name == "default":
            expanded = SCOPE_DEFAULT
        elif name == "all":
            expanded = SCOPE_ALL
            run_integration = True
        elif name == "integration":
            expanded = ["integration"]
            run_integration = True
        elif name in SCOPES:
            expanded = [name]
        else:
            expanded = [name]

        for scope in expanded:
            if scope in SCOPES and scope not in seen:
                seen.add(scope)
                directories.extend(SCOPES[scope])

    return ResolvedScopes(directories=directories, run_integration=run_integration)


def build_pytest_args(
    *,
    directories: list[str],
    run_integration: bool = False,
    coverage: bool = False,
    cov_run_dir: Path | None = None,
    stop_first: bool = False,
    keyword: str | None = None,
) -> list[str]:
    """Build the pytest command-line argument list.

    Args:
        directories: Test directories to run.
        run_integration: Whether to add --run-integration flag.
        coverage: Whether to enable coverage collection.
        cov_run_dir: Directory for coverage output (required if coverage=True).
        stop_first: Whether to stop on first failure (-x).
        keyword: Pytest -k filter expression.

    Returns:
        List of command-line arguments (without the leading 'pytest').
    """
    args: list[str] = []

    if coverage and cov_run_dir is not None:
        args.extend(
            [
                "--cov=app",
                "--cov=scripts",
                "--cov-report=term-missing",
                f"--cov-report=html:{cov_run_dir / 'htmlcov'}",
            ]
        )

    if run_integration:
        args.append("--run-integration")

    if stop_first:
        args.append("-x")

    if keyword:
        args.extend(["-k", keyword])

    args.extend(directories)

    return args


def _create_cov_dir() -> Path:
    """Create a timestamped coverage output directory."""
    stamp = datetime.now().strftime("%Y%m%dT%H%M")
    cov_run = COV_DIR / stamp
    cov_run.mkdir(parents=True, exist_ok=True)
    return cov_run


def _update_latest_symlink(cov_run: Path) -> None:
    """Create/update the _build/coverage/latest symlink."""
    latest = COV_DIR / "latest"
    # Remove existing symlink/file
    if latest.is_symlink() or latest.exists():
        latest.unlink()
    latest.symlink_to(cov_run.name)


def _generate_lcov(cov_run: Path) -> None:
    """Generate lcov report from .coverage data."""
    subprocess.run(
        [sys.executable, "-m", "coverage", "lcov", "-o", str(cov_run / "coverage.lcov")],
        cwd=str(PROJECT_ROOT),
        check=False,
    )


def _generate_grouped_html(cov_run: Path) -> None:
    """Generate grouped HTML report via genhtml if available."""
    # noinspection PyDeprecation
    genhtml = shutil.which("genhtml")
    if genhtml is None:
        print("(genhtml not found — skipping grouped HTML report. Install with: brew install lcov)")
        return

    lcov_file = cov_run / "coverage.lcov"
    grouped_dir = cov_run / "htmlcov-grouped"
    result = subprocess.run(
        [
            genhtml,
            str(lcov_file),
            "-o",
            str(grouped_dir),
            "--hierarchical",
            "--title",
            "Greeting Cards Coverage",
            "--quiet",
            "--ignore-errors",
            "inconsistent,inconsistent,corrupt,category",
        ],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        print(f"(genhtml failed: {result.stderr.decode().strip()})")


def _print_coverage_locations(cov_run: Path) -> None:
    """Print paths to the generated coverage reports."""
    print()
    print(f"Coverage output: {cov_run}/")
    print(f"  Flat HTML:    {cov_run / 'htmlcov' / 'index.html'}")
    grouped = cov_run / "htmlcov-grouped"
    if grouped.is_dir():
        print(f"  Grouped HTML: {grouped / 'index.html'}")


def _open_coverage(cov_run: Path) -> None:
    """Open coverage HTML reports in the browser."""
    flat = cov_run / "htmlcov" / "index.html"
    if flat.exists():
        webbrowser.open(f"file://{flat}")
    grouped = cov_run / "htmlcov-grouped" / "index.html"
    if grouped.exists():
        webbrowser.open(f"file://{grouped}")


def _print_help() -> None:
    """Print usage information with scope descriptions and examples."""
    print("Test Runner — run pytest with scopes and options")
    print()
    print("Scopes:")
    print("  default       core + gui + scripts (excludes integration)")
    print("  core          tests/core/ — business logic")
    print("  gui           tests/gui/ — wxPython UI")
    print("  scripts       tests/scripts/ — standalone scripts")
    print("  integration   tests/integration/ — Apple Events (adds --run-integration)")
    print("  all           everything including integration")
    print()
    print("Options:")
    print("  --cov         Enable coverage reports (timestamped dir, HTML, lcov)")
    print("  --open        Open coverage reports in browser (implies --cov)")
    print("  -x            Stop on first failure")
    print("  -k EXPR       Pytest keyword filter")
    print()
    print("Examples:")
    print("  make test T=default                   # core + gui + scripts")
    print("  make test T=core                      # just core tests")
    print('  make test T="gui scripts"             # combine scopes')
    print('  make test T="default --cov"           # with coverage reports')
    print('  make test T="default --cov --open"    # coverage + open in browser')
    print('  make test T="core -x"                 # stop on first failure')
    print('  make test T="core -k family_name"     # keyword filter')
    print('  make test T="all --cov --open"        # everything with coverage')


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="run_tests.py",
        description="Run pytest with scopes and options.",
        add_help=False,
    )
    parser.add_argument(
        "scopes",
        nargs="*",
        help="Test scopes: default, core, gui, scripts, integration, all",
    )
    parser.add_argument("--cov", action="store_true", help="Enable coverage reports")
    parser.add_argument("--open", action="store_true", dest="open_cov", help="Open coverage in browser")
    parser.add_argument("-x", action="store_true", dest="stop_first", help="Stop on first failure")
    parser.add_argument("-k", dest="keyword", help="Pytest keyword filter")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the test runner.

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    if argv is None:
        argv = sys.argv[1:]

    # Show help when no arguments provided
    if not argv:
        _print_help()
        return 0

    args = _parse_args(argv)

    # --open implies --cov
    if args.open_cov:
        args.cov = True

    resolved = resolve_scopes(args.scopes)

    if not resolved.directories:
        print("Error: no valid scopes specified.", file=sys.stderr)
        print("Valid scopes: default, core, gui, scripts, integration, all", file=sys.stderr)
        return 1

    # Set up coverage directory if needed
    cov_run: Path | None = None
    if args.cov:
        cov_run = _create_cov_dir()

    pytest_args = build_pytest_args(
        directories=resolved.directories,
        run_integration=resolved.run_integration,
        coverage=args.cov,
        cov_run_dir=cov_run,
        stop_first=args.stop_first,
        keyword=args.keyword,
    )

    # Run pytest
    cmd = [sys.executable, "-m", "pytest"] + pytest_args  # noqa: RUF005
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))

    # Post-pytest coverage processing
    if args.cov and cov_run is not None:
        _generate_lcov(cov_run)
        _generate_grouped_html(cov_run)
        _update_latest_symlink(cov_run)
        _print_coverage_locations(cov_run)

        if args.open_cov:
            _open_coverage(cov_run)

    return result.returncode


if __name__ == "__main__":  # pragma: no cover — script entry point
    raise SystemExit(main())
