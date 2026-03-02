"""Fixtures for Apple Events integration tests.

These tests launch the real app bundle and send Apple Events via osascript.
Requires: ``make app`` to build the bundle first.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import fitz
import pytest

APP_PATH = Path("dist/Greeting Cards.app")
BUNDLE_ID = "com.kaymakcalan.app.greetingcards"


def osascript(script: str, timeout: int = 60) -> str | None:
    """Run AppleScript and return stdout, or None on error."""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def osascript_json(script: str) -> dict | list | None:
    """Run AppleScript and parse JSON result."""
    raw = osascript(script)
    if not raw:
        return None
    return json.loads(raw)


def wait_until_idle(timeout: int = 120) -> bool:
    """Poll get status until not processing and not analyzing."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        raw = osascript(f'tell application id "{BUNDLE_ID}" to get status')
        if raw and '"is_processing": false' in raw and '"is_analyzing": false' in raw:
            return True
        time.sleep(1)
    return False


def tell(command: str) -> str | None:
    """Shorthand for tell application id ... to <command>."""
    return osascript(f'tell application id "{BUNDLE_ID}" to {command}')


@pytest.fixture(scope="session")
def app_bundle():
    """Ensure the app bundle exists."""
    if not APP_PATH.exists():
        pytest.skip("App bundle not built — run 'make app' first")
    return APP_PATH


@pytest.fixture(scope="session", autouse=True)
def launch_app(app_bundle):
    """Launch the app before tests and quit after."""
    subprocess.run(["open", str(app_bundle)], check=True)
    # Wait for app to be ready
    for _ in range(30):
        result = osascript(f'tell application id "{BUNDLE_ID}" to get status')
        if result is not None:
            break
        time.sleep(1)
    else:
        pytest.fail("App did not respond within 30 seconds")
    yield
    osascript(f'tell application id "{BUNDLE_ID}" to quit')
    time.sleep(1)


@pytest.fixture
def clean_state():
    """Clear all loaded cards before each test."""
    tell("clear all")
    time.sleep(0.5)


@pytest.fixture(scope="session")
def test_pdfs(tmp_path_factory):
    """Create a temp directory with small test PDFs."""
    pdf_dir = tmp_path_factory.mktemp("test_pdfs")

    for name in ["Alpha Card.pdf", "Beta Card.pdf"]:
        path = pdf_dir / name
        doc = fitz.open()
        page = doc.new_page(width=200, height=200)
        page.insert_text((20, 50), f"Holiday Card\nFrom the {name.split()[0]} Family", fontsize=14)
        doc.save(str(path))
        doc.close()

    return pdf_dir


@pytest.fixture
def rename_pdfs(tmp_path):
    """Create a temp directory with a single PDF for rename tests (function-scoped)."""
    path = tmp_path / "RenameTarget.pdf"
    doc = fitz.open()
    page = doc.new_page(width=200, height=200)
    page.insert_text((20, 50), "Holiday Card\nFrom the Johnson Family", fontsize=14)
    doc.save(str(path))
    doc.close()
    return tmp_path
