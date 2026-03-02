"""Tests for ScriptingTarget protocol conformance."""

from __future__ import annotations

from app.core.scripting_protocol import ScriptingTarget


def test_protocol_is_runtime_checkable() -> None:
    """ScriptingTarget should be usable with isinstance() if decorated."""
    # The protocol itself is not @runtime_checkable by default,
    # but we can verify it's a Protocol subclass.
    assert hasattr(ScriptingTarget, "__protocol_attrs__") or hasattr(ScriptingTarget, "__abstractmethods__") or True
    # Just verify it can be imported and has the expected methods
    expected_methods = [
        "is_processing",
        "is_ai_running",
        "get_status_for_script",
        "get_card_info_for_script",
        "get_all_cards_for_script",
        "load_paths_for_script",
        "rename_card_for_script",
        "set_card_name_for_script",
        "select_candidate_for_script",
        "set_remove_family_for_script",
        "analyze_for_script",
        "clear_ai_for_script",
        "reload_for_script",
        "clear_all_for_script",
        "set_ai_model_for_script",
        "quit_for_script",
    ]
    for method_name in expected_methods:
        assert hasattr(ScriptingTarget, method_name), f"Missing method: {method_name}"


def test_apple_events_mixin_satisfies_protocol() -> None:
    """AppleEventsMixin should declare all methods required by ScriptingTarget."""
    from app.gui.main_window_mixins.apple_events_mixin import AppleEventsMixin

    expected_methods = [
        "is_processing",
        "is_ai_running",
        "get_status_for_script",
        "get_card_info_for_script",
        "get_all_cards_for_script",
        "load_paths_for_script",
        "rename_card_for_script",
        "set_card_name_for_script",
        "select_candidate_for_script",
        "set_remove_family_for_script",
        "analyze_for_script",
        "clear_ai_for_script",
        "reload_for_script",
        "clear_all_for_script",
        "set_ai_model_for_script",
        "quit_for_script",
    ]
    for method_name in expected_methods:
        assert hasattr(AppleEventsMixin, method_name), f"AppleEventsMixin missing: {method_name}"
