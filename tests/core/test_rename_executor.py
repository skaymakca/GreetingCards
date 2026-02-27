"""Tests for app.core.rename_executor."""

from pathlib import Path

from app.core.rename_executor import RESOLVED_MESSAGES, filter_completed_renames
from app.models.card import RenameResult


def _make_result(
    *,
    success: bool = True,
    message: str = "Renamed",
    old_path: str = "/old/card.pdf",
    new_path: str = "/new/card.pdf",
) -> RenameResult:
    return RenameResult(
        success=success,
        message=message,
        old_path=Path(old_path),
        new_path=Path(new_path),
    )


class TestResolvedMessages:
    def test_contains_renamed(self):
        assert "Renamed" in RESOLVED_MESSAGES

    def test_contains_already_named_correctly(self):
        assert "Already named correctly" in RESOLVED_MESSAGES

    def test_size(self):
        assert len(RESOLVED_MESSAGES) == 2


class TestFilterCompletedRenames:
    def test_empty_results(self):
        assert filter_completed_renames([]) == set()

    def test_successful_renamed(self):
        r = _make_result(success=True, message="Renamed", new_path="/new/card.pdf")
        result = filter_completed_renames([r])
        assert result == {Path("/new/card.pdf")}

    def test_already_named_correctly(self):
        r = _make_result(success=True, message="Already named correctly", new_path="/same/card.pdf")
        result = filter_completed_renames([r])
        assert result == {Path("/same/card.pdf")}

    def test_failure_excluded(self):
        r = _make_result(success=False, message="Renamed", new_path="/failed.pdf")
        assert filter_completed_renames([r]) == set()

    def test_no_name_excluded(self):
        r = _make_result(success=False, message="No name detected", new_path="/noname.pdf")
        assert filter_completed_renames([r]) == set()

    def test_mixed_results(self):
        results = [
            _make_result(success=True, message="Renamed", new_path="/a.pdf"),
            _make_result(success=False, message="No name detected", new_path="/b.pdf"),
            _make_result(success=True, message="Already named correctly", new_path="/c.pdf"),
        ]
        assert filter_completed_renames(results) == {Path("/a.pdf"), Path("/c.pdf")}

    def test_uses_new_path(self):
        """filter_completed_renames returns new_path, not old_path."""
        r = _make_result(success=True, message="Renamed", old_path="/old.pdf", new_path="/new.pdf")
        result = filter_completed_renames([r])
        assert Path("/new.pdf") in result
        assert Path("/old.pdf") not in result
