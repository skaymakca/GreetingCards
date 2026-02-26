"""Shared pytest fixtures for GUI tests."""

import pytest
import wx


@pytest.fixture(scope="session")
def wx_app():
    """Create a wx.App for the entire test session.

    wxPython only supports one wx.App at a time. This session-scoped
    fixture ensures a single instance is shared across all GUI tests.
    """
    app = wx.App()
    yield app
    app.Destroy()


@pytest.fixture
def wx_frame(wx_app):
    """Create a temporary frame for testing widgets.

    The frame is not shown during tests, but provides a parent
    for widgets that require one.
    """
    frame = wx.Frame(None, title="Test Frame")
    yield frame
    frame.Destroy()
