"""Shared pytest fixtures for GUI tests."""

import pytest
import wx


@pytest.fixture
def wx_app():
    """Create wxPython app for testing.

    This fixture provides a wx.App instance required for all wx GUI operations.
    The app is automatically destroyed after the test completes.
    """
    app = wx.App()
    yield app
    app.Destroy()


@pytest.fixture
def wx_frame(wx_app):
    """Create test frame.

    This fixture provides a wx.Frame for testing widget creation and layout.
    The frame is automatically destroyed after the test completes.
    Requires wx_app fixture.
    """
    frame = wx.Frame(None)
    yield frame
    frame.Destroy()
