"""Tests for app/gui/rename_display.py — pure rename display formatters."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.gui.rename_display import (
    filter_visible_results,
    format_candidate_label,
    format_plan_summary,
    format_result_status,
    format_results_summary,
    get_plan_item_display,
    is_skip_status,
    summarize_plan,
    summarize_results,
)
from app.models.card import (
    STATUS_DUPLICATE,
    STATUS_OK,
    STATUS_SKIP_ERROR,
    STATUS_SKIP_NO_NAME,
    STATUS_SKIP_SAME,
    CandidateInfo,
    RenameOutcome,
    RenamePlanItem,
    RenameResult,
)

# ── format_candidate_label ─────────────────────────────────────────


class TestFormatCandidateLabel:
    def test_basic_label(self) -> None:
        cand = CandidateInfo(id=1, family_name="Smith", method="ocr", confidence="high")
        assert format_candidate_label(cand) == "Smith (OCR - High)"

    def test_ai_method(self) -> None:
        cand = CandidateInfo(id=2, family_name="Jones", method="ai", confidence="medium")
        assert format_candidate_label(cand) == "Jones (AI - Medium)"

    def test_low_confidence(self) -> None:
        cand = CandidateInfo(id=3, family_name="Williams", method="ocr", confidence="low")
        assert format_candidate_label(cand) == "Williams (OCR - Low)"


# ── summarize_plan ─────────────────────────────────────────────────


def _make_plan_item(status, old_name="card.pdf", new_name="new.pdf") -> RenamePlanItem:
    return RenamePlanItem(
        old_path=Path(f"/dir/{old_name}"),
        new_path=Path(f"/dir/{new_name}"),
        status=status,
    )


class TestSummarizePlan:
    def test_all_ok(self) -> None:
        plan = [_make_plan_item(STATUS_OK), _make_plan_item(STATUS_OK)]
        counts = summarize_plan(plan)
        assert counts["ok"] == 2
        assert counts["duplicate"] == 0
        assert counts["error"] == 0
        assert counts["skip"] == 0
        assert counts["directory_count"] == 1

    def test_mixed_statuses(self) -> None:
        plan = [
            _make_plan_item(STATUS_OK),
            _make_plan_item(STATUS_DUPLICATE),
            _make_plan_item(STATUS_SKIP_NO_NAME),
            _make_plan_item(STATUS_SKIP_SAME),
            _make_plan_item(STATUS_SKIP_ERROR),
        ]
        counts = summarize_plan(plan)
        assert counts["ok"] == 1
        assert counts["duplicate"] == 1
        assert counts["error"] == 1
        assert counts["skip"] == 2

    def test_multiple_directories(self) -> None:
        plan = [
            RenamePlanItem(old_path=Path("/a/card.pdf"), new_path=Path("/a/new.pdf"), status=STATUS_OK),
            RenamePlanItem(old_path=Path("/b/card.pdf"), new_path=Path("/b/new.pdf"), status=STATUS_OK),
        ]
        counts = summarize_plan(plan)
        assert counts["directory_count"] == 2


# ── format_plan_summary ────────────────────────────────────────────


class TestFormatPlanSummary:
    def test_only_renames(self) -> None:
        plan = [_make_plan_item(STATUS_OK)]
        assert format_plan_summary(plan) == "1 rename(s)"

    def test_with_duplicates_and_skips(self) -> None:
        plan = [
            _make_plan_item(STATUS_OK),
            _make_plan_item(STATUS_DUPLICATE),
            _make_plan_item(STATUS_SKIP_NO_NAME),
        ]
        summary = format_plan_summary(plan)
        assert "1 rename(s)" in summary
        assert "1 duplicate(s)" in summary
        assert "1 skipped" in summary

    def test_with_errors(self) -> None:
        plan = [_make_plan_item(STATUS_OK), _make_plan_item(STATUS_SKIP_ERROR)]
        summary = format_plan_summary(plan)
        assert "1 error(s)" in summary

    def test_multiple_directories_appended(self) -> None:
        plan = [
            RenamePlanItem(old_path=Path("/a/card.pdf"), new_path=Path("/a/new.pdf"), status=STATUS_OK),
            RenamePlanItem(old_path=Path("/b/card.pdf"), new_path=Path("/b/new.pdf"), status=STATUS_OK),
        ]
        summary = format_plan_summary(plan)
        assert "across 2 directories" in summary


# ── summarize_results ──────────────────────────────────────────────


def _make_result(outcome, success=True, old="card.pdf", new="new.pdf") -> RenameResult:
    return RenameResult(
        old_path=Path(f"/dir/{old}"),
        new_path=Path(f"/dir/{new}"),
        success=success,
        message="",
        outcome=outcome,
    )


class TestSummarizeResults:
    def test_all_renamed(self) -> None:
        results = [_make_result(RenameOutcome.RENAMED), _make_result(RenameOutcome.RENAMED)]
        counts = summarize_results(results)
        assert counts["renamed"] == 2
        assert counts["skipped"] == 0
        assert counts["errors"] == 0
        assert counts["directory_count"] == 1

    def test_mixed_outcomes(self) -> None:
        results = [
            _make_result(RenameOutcome.RENAMED),
            _make_result(RenameOutcome.ALREADY_CORRECT),
            _make_result(RenameOutcome.ERROR_OS, success=False),
        ]
        counts = summarize_results(results)
        assert counts["renamed"] == 1
        assert counts["skipped"] == 1
        assert counts["errors"] == 1


# ── format_results_summary ─────────────────────────────────────────


class TestFormatResultsSummary:
    def test_no_errors(self) -> None:
        results = [_make_result(RenameOutcome.RENAMED), _make_result(RenameOutcome.ALREADY_CORRECT)]
        summary = format_results_summary(results)
        assert "1 renamed" in summary
        assert "1 skipped" in summary
        assert "failed" not in summary

    def test_with_errors(self) -> None:
        results = [_make_result(RenameOutcome.ERROR_OS, success=False)]
        summary = format_results_summary(results)
        assert "1 failed" in summary


# ── get_plan_item_display ──────────────────────────────────────────


class TestGetPlanItemDisplay:
    @pytest.mark.parametrize(
        ("status", "expected_label", "expected_category"),
        [
            (STATUS_OK, "OK", "ok"),
            (STATUS_DUPLICATE, "DUP", "duplicate"),
            (STATUS_SKIP_NO_NAME, "SKIP", "skip"),
            (STATUS_SKIP_SAME, "SAME", "skip"),
            (STATUS_SKIP_ERROR, "ERROR", "error"),
        ],
    )
    def test_all_statuses(self, status, expected_label, expected_category) -> None:
        item = _make_plan_item(status)
        label, category = get_plan_item_display(item)
        assert label == expected_label
        assert category == expected_category


# ── is_skip_status ─────────────────────────────────────────────────


class TestIsSkipStatus:
    def test_skip_statuses(self) -> None:
        assert is_skip_status(_make_plan_item(STATUS_SKIP_NO_NAME)) is True
        assert is_skip_status(_make_plan_item(STATUS_SKIP_SAME)) is True
        assert is_skip_status(_make_plan_item(STATUS_SKIP_ERROR)) is True

    def test_non_skip_statuses(self) -> None:
        assert is_skip_status(_make_plan_item(STATUS_OK)) is False
        assert is_skip_status(_make_plan_item(STATUS_DUPLICATE)) is False


# ── filter_visible_results ─────────────────────────────────────────


class TestFilterVisibleResults:
    def test_keeps_renamed(self) -> None:
        results = [_make_result(RenameOutcome.RENAMED)]
        assert len(filter_visible_results(results)) == 1

    def test_keeps_errors(self) -> None:
        results = [_make_result(RenameOutcome.ERROR_OS, success=False)]
        assert len(filter_visible_results(results)) == 1

    def test_hides_skipped(self) -> None:
        results = [
            _make_result(RenameOutcome.ALREADY_CORRECT),
            _make_result(RenameOutcome.SKIP_NO_NAME),
        ]
        assert len(filter_visible_results(results)) == 0

    def test_mixed(self) -> None:
        results = [
            _make_result(RenameOutcome.RENAMED),
            _make_result(RenameOutcome.ALREADY_CORRECT),
            _make_result(RenameOutcome.ERROR_TARGET_EXISTS, success=False),
        ]
        visible = filter_visible_results(results)
        assert len(visible) == 2


# ── format_result_status ───────────────────────────────────────────


class TestFormatResultStatus:
    def test_renamed_ok(self) -> None:
        result = _make_result(RenameOutcome.RENAMED)
        assert format_result_status(result) == "OK"

    def test_already_correct(self) -> None:
        result = _make_result(RenameOutcome.ALREADY_CORRECT)
        assert format_result_status(result) == "Already correct"

    def test_skip_no_name(self) -> None:
        result = _make_result(RenameOutcome.SKIP_NO_NAME)
        assert format_result_status(result) == "Skipped (no name)"

    def test_skip_error(self) -> None:
        result = _make_result(RenameOutcome.SKIP_ERROR)
        assert format_result_status(result) == "Skipped (error)"

    def test_error_target_exists_with_message(self) -> None:
        result = RenameResult(
            old_path=Path("/dir/card.pdf"),
            new_path=Path("/dir/new.pdf"),
            success=False,
            message="File already exists",
            outcome=RenameOutcome.ERROR_TARGET_EXISTS,
        )
        assert format_result_status(result) == "ERROR: File already exists"

    def test_error_os_with_message(self) -> None:
        result = RenameResult(
            old_path=Path("/dir/card.pdf"),
            new_path=Path("/dir/new.pdf"),
            success=False,
            message="Permission denied",
            outcome=RenameOutcome.ERROR_OS,
        )
        assert format_result_status(result) == "ERROR: Permission denied"

    def test_error_os_without_message(self) -> None:
        result = RenameResult(
            old_path=Path("/dir/card.pdf"),
            new_path=Path("/dir/new.pdf"),
            success=False,
            message="",
            outcome=RenameOutcome.ERROR_OS,
        )
        assert format_result_status(result) == "ERROR"

    def test_error_target_exists_without_message(self) -> None:
        result = RenameResult(
            old_path=Path("/dir/card.pdf"),
            new_path=Path("/dir/new.pdf"),
            success=False,
            message="",
            outcome=RenameOutcome.ERROR_TARGET_EXISTS,
        )
        assert format_result_status(result) == "ERROR: Target exists"
