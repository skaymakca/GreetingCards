"""Shared pytest fixtures for tests/scripts/."""

from __future__ import annotations

import io
from unittest.mock import MagicMock

import pytest
from rich.console import Console


@pytest.fixture
def quiet_console() -> Console:
    """A Console that writes to a StringIO — suppresses terminal output."""
    return Console(file=io.StringIO())


@pytest.fixture
def mock_console() -> MagicMock:
    """A MagicMock with Console spec — for asserting print calls."""
    return MagicMock(spec=Console)
