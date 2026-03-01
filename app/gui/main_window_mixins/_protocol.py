"""MainWindowProtocol — structural type for mixin self-annotations.

Each mixin method uses ``self: MainWindowProtocol`` so that type-checkers
understand which attributes and methods are available from the full
MainWindow instance at runtime.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import wx

from app.core.card_service import CardService
from app.core.card_store import CardStore
from app.gui.components.filter_sidebar import FilterSidebar
from app.gui.components.preview_panel import PreviewPanel
from app.gui.components.review_panel import ReviewPanelMasterDetail
from app.gui.styles import Layout
from app.models.card import CardResult


class MainWindowProtocol(Protocol):
    """Structural interface declaring all MainWindow state used by mixins."""

    # --- Widgets ---
    _frame: wx.Frame
    _toolbar: wx.ToolBar
    _search_ctrl: wx.SearchCtrl
    _year_ctrl: wx.TextCtrl
    _reload_id: int
    _edit_debounce_timer: wx.Timer

    # --- Panels ---
    _sidebar: FilterSidebar
    _review_panel: ReviewPanelMasterDetail
    _preview_panel: PreviewPanel

    # --- Services ---
    _card_store: CardStore
    _card_service: CardService

    # --- Orchestration state ---
    _processing_files: list[Path]

    # --- Filter state ---
    _current_category_filters: list[str]
    _current_folder_filters: list[str]

    # --- AI state ---
    _ai_batch_running: bool
    _ai_target_cards: list[CardResult]

    # --- Methods that stay in MainWindow core ---

    def _set_empty_state(self, is_empty: bool) -> None: ...

    def _get_card_by_id(self, card_id: int) -> CardResult | None: ...

    def _unlink_path(self, path: Path) -> None: ...

    def _show_info_message(
        self, message: str, icon: int = wx.ICON_INFORMATION, duration_ms: int = Layout.INFO_DISMISS_MS
    ) -> None: ...

    def _show_progress_strip(self, total: int, title: str) -> None: ...

    def _update_progress_strip(self, current: int, message: str) -> None: ...

    def _hide_progress_strip(self) -> None: ...

    def _enable_action_tools(
        self,
        *,
        reload: bool | None = None,
        ai: bool | None = None,
        rename: bool | None = None,
        clear: bool | None = None,
    ) -> None: ...

    def _start_processing(self, files: list[Path] | None = None) -> None: ...

    def _reload_cards(self, *, mtime_only: bool = False) -> None: ...

    def _clear_all(self) -> None: ...

    # --- FilterMixin methods ---

    def _refresh_display(self) -> None: ...

    def _has_active_filters(self) -> bool: ...

    def _get_search_filtered_cards(self) -> list[CardResult]: ...

    def _apply_folder_filters(self, cards: list[CardResult]) -> list[CardResult]: ...

    def _apply_category_filters(self, cards: list[CardResult]) -> list[CardResult]: ...

    # --- AIMixin methods ---

    def _ensure_api_key(self) -> bool: ...

    def _get_target_cards(self) -> tuple[list[CardResult], str]: ...

    def _start_ai_all(self, cards: list[CardResult] | None = None, title: str | None = None) -> None: ...

    def _run_ai_all(self) -> None: ...

    def _update_ai_all_progress(
        self,
        completed: int,
        total: int,
        filename: str,
        card_id: int,
        card: CardResult | None,
    ) -> None: ...

    def _ai_all_complete(self, errors: list[tuple[str, str]], auth_aborted: bool = False) -> None: ...

    # --- AppleEventsMixin methods ---

    @property
    def is_processing(self) -> bool: ...

    @property
    def is_ai_running(self) -> bool: ...

    def _find_card_by_filename(self, filename: str) -> CardResult | None: ...
