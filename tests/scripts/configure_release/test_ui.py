"""Tests for scripts/configure_release/ui.py."""

from __future__ import annotations

from scripts.configure_release.ui import InteractiveInput


class TestChoose:
    """Test InteractiveInput.choose()."""

    def test_choose_valid_input(self, monkeypatch: object) -> None:
        # monkeypatch is pytest.MonkeyPatch but we keep it simple for type checkers
        import builtins

        inputs = iter(["2"])
        monkeypatch.setattr(builtins, "input", lambda _prompt: next(inputs))  # type: ignore[attr-defined]

        ui = InteractiveInput()
        result = ui.choose("Pick one:", ["Alpha", "Beta", "Gamma"])

        assert result == 1  # 0-based index for "Beta"

    def test_choose_default(self, monkeypatch: object) -> None:
        import builtins

        inputs = iter([""])
        monkeypatch.setattr(builtins, "input", lambda _prompt: next(inputs))  # type: ignore[attr-defined]

        ui = InteractiveInput()
        result = ui.choose("Pick one:", ["Alpha", "Beta"], default=0)

        assert result == 0

    def test_choose_invalid_then_valid(self, monkeypatch: object) -> None:
        import builtins

        inputs = iter(["abc", "1"])
        monkeypatch.setattr(builtins, "input", lambda _prompt: next(inputs))  # type: ignore[attr-defined]

        ui = InteractiveInput()
        result = ui.choose("Pick one:", ["Alpha", "Beta"])

        assert result == 0  # "1" → index 0

    def test_choose_out_of_range_then_valid(self, monkeypatch: object) -> None:
        import builtins

        inputs = iter(["99", "1"])
        monkeypatch.setattr(builtins, "input", lambda _prompt: next(inputs))  # type: ignore[attr-defined]

        ui = InteractiveInput()
        result = ui.choose("Pick one:", ["Alpha", "Beta"])

        assert result == 0

    def test_choose_empty_no_default_then_valid(self, monkeypatch: object) -> None:
        import builtins

        inputs = iter(["", "2"])
        monkeypatch.setattr(builtins, "input", lambda _prompt: next(inputs))  # type: ignore[attr-defined]

        ui = InteractiveInput()
        result = ui.choose("Pick one:", ["Alpha", "Beta"])

        assert result == 1


class TestAsk:
    """Test InteractiveInput.ask()."""

    def test_ask_returns_user_value(self, monkeypatch: object) -> None:
        import builtins

        monkeypatch.setattr(builtins, "input", lambda _prompt: "MyProfile")  # type: ignore[attr-defined]

        ui = InteractiveInput()
        result = ui.ask("Profile name", default="Default")

        assert result == "MyProfile"

    def test_ask_empty_returns_default(self, monkeypatch: object) -> None:
        import builtins

        monkeypatch.setattr(builtins, "input", lambda _prompt: "")  # type: ignore[attr-defined]

        ui = InteractiveInput()
        result = ui.ask("Profile name", default="GreetingCards")

        assert result == "GreetingCards"

    def test_ask_whitespace_returns_default(self, monkeypatch: object) -> None:
        import builtins

        monkeypatch.setattr(builtins, "input", lambda _prompt: "   ")  # type: ignore[attr-defined]

        ui = InteractiveInput()
        result = ui.ask("Profile name", default="Fallback")

        assert result == "Fallback"


class TestConfirm:
    """Test InteractiveInput.confirm()."""

    def test_confirm_default_yes(self, monkeypatch: object) -> None:
        import builtins

        monkeypatch.setattr(builtins, "input", lambda _prompt: "")  # type: ignore[attr-defined]

        ui = InteractiveInput()
        result = ui.confirm("Continue?", default=True)

        assert result is True

    def test_confirm_explicit_no(self, monkeypatch: object) -> None:
        import builtins

        monkeypatch.setattr(builtins, "input", lambda _prompt: "n")  # type: ignore[attr-defined]

        ui = InteractiveInput()
        result = ui.confirm("Continue?", default=True)

        assert result is False

    def test_confirm_default_false_empty(self, monkeypatch: object) -> None:
        import builtins

        monkeypatch.setattr(builtins, "input", lambda _prompt: "")  # type: ignore[attr-defined]

        ui = InteractiveInput()
        result = ui.confirm("Continue?", default=False)

        assert result is False

    def test_confirm_explicit_yes(self, monkeypatch: object) -> None:
        import builtins

        monkeypatch.setattr(builtins, "input", lambda _prompt: "y")  # type: ignore[attr-defined]

        ui = InteractiveInput()
        result = ui.confirm("Continue?", default=False)

        assert result is True

    def test_confirm_explicit_yes_full(self, monkeypatch: object) -> None:
        import builtins

        monkeypatch.setattr(builtins, "input", lambda _prompt: "yes")  # type: ignore[attr-defined]

        ui = InteractiveInput()
        result = ui.confirm("Continue?", default=False)

        assert result is True

    def test_confirm_non_boolean_input(self, monkeypatch: object) -> None:
        import builtins

        monkeypatch.setattr(builtins, "input", lambda _prompt: "maybe")  # type: ignore[attr-defined]

        ui = InteractiveInput()
        result = ui.confirm("Continue?", default=True)

        assert result is False
