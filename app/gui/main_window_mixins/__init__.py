"""MainWindow mixin package — functional groups extracted from MainWindow."""

from app.gui.main_window_mixins.ai_mixin import AIMixin
from app.gui.main_window_mixins.apple_events_mixin import AppleEventsMixin
from app.gui.main_window_mixins.filter_mixin import FilterMixin
from app.gui.main_window_mixins.selection_mixin import SelectionMixin

__all__ = ["AIMixin", "AppleEventsMixin", "FilterMixin", "SelectionMixin"]
