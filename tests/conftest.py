"""Shared pytest fixtures for all tests."""

import pytest
import wx


@pytest.fixture(scope="session")
def wx_app():
    """Create a wx.App for the entire test session.

    This fixture is needed for any tests that create wxPython widgets.
    Mark tests that need this with @pytest.mark.gui
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
