"""Tests for app.core.naming.rename_filter."""

from pathlib import Path

from app.core.naming.rename_filter import RESOLVED_OUTCOMES, filter_completed_renames
from app.models.card import RenameOutcome, RenameResult


def _make_result(
    *,
    success: bool = True,
    message: str = "Renamed",
    outcome: RenameOutcome = RenameOutcome.RENAMED,
    old_path: str = "/old/card.pdf",
    new_path: str = "/new/card.pdf",
) -> RenameResult:
    return RenameResult(
        success=success,
        message=message,
        outcome=outcome,
        old_path=Path(old_path),
        new_path=Path(new_path),
    )


class TestResolvedOutcomes:
    def test_contains_renamed(self):
        assert RenameOutcome.RENAMED in RESOLVED_OUTCOMES

    def test_contains_already_correct(self):
        assert RenameOutcome.ALREADY_CORRECT in RESOLVED_OUTCOMES

    def test_size(self):
        assert len(RESOLVED_OUTCOMES) == 2


class TestFilterCompletedRenames:
    def test_empty_results(self):
        assert filter_completed_renames([]) == set()

    def test_successful_renamed(self):
        r = _make_result(success=True, outcome=RenameOutcome.RENAMED, new_path="/new/card.pdf")
        result = filter_completed_renames([r])
        assert result == {Path("/new/card.pdf")}

    def test_already_named_correctly(self):
        r = _make_result(success=True, outcome=RenameOutcome.ALREADY_CORRECT, new_path="/same/card.pdf")
        result = filter_completed_renames([r])
        assert result == {Path("/same/card.pdf")}

    def test_failure_excluded(self):
        r = _make_result(success=False, outcome=RenameOutcome.ERROR_OS, new_path="/failed.pdf")
        assert filter_completed_renames([r]) == set()

    def test_skip_no_name_excluded(self):
        r = _make_result(success=True, outcome=RenameOutcome.SKIP_NO_NAME, new_path="/noname.pdf")
        assert filter_completed_renames([r]) == set()

    def test_mixed_results(self):
        results = [
            _make_result(success=True, outcome=RenameOutcome.RENAMED, new_path="/a.pdf"),
            _make_result(success=False, outcome=RenameOutcome.ERROR_OS, new_path="/b.pdf"),
            _make_result(success=True, outcome=RenameOutcome.ALREADY_CORRECT, new_path="/c.pdf"),
        ]
        assert filter_completed_renames(results) == {Path("/a.pdf"), Path("/c.pdf")}

    def test_uses_new_path(self):
        """filter_completed_renames returns new_path, not old_path."""
        r = _make_result(success=True, outcome=RenameOutcome.RENAMED, old_path="/old.pdf", new_path="/new.pdf")
        result = filter_completed_renames([r])
        assert Path("/new.pdf") in result
        assert Path("/old.pdf") not in result
