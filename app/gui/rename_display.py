"""Rename display formatters — presentation helpers for rename plan/results.

These functions format rename plans and results for user-facing display.
They are pure functions with no GUI dependencies.
"""

from __future__ import annotations

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
    RenameStatus,
)


def format_candidate_label(candidate: CandidateInfo) -> str:
    """Format a candidate's display label for the review panel."""
    return f"{candidate.family_name} ({candidate.method.upper()} - {candidate.confidence.capitalize()})"


def summarize_plan(plan: list[RenamePlanItem]) -> dict[str, int]:
    """Summarize a rename plan by status counts.

    Returns dict with keys: ok, duplicate, error, skip, directory_count.
    """
    return {
        "ok": sum(1 for item in plan if item.status == STATUS_OK),
        "duplicate": sum(1 for item in plan if item.status == STATUS_DUPLICATE),
        "error": sum(1 for item in plan if item.status == STATUS_SKIP_ERROR),
        "skip": sum(1 for item in plan if item.status in {STATUS_SKIP_NO_NAME, STATUS_SKIP_SAME}),
        "directory_count": len({item.old_path.parent for item in plan}),
    }


def format_plan_summary(plan: list[RenamePlanItem]) -> str:
    """Format a rename plan summary as a user-facing string."""
    counts = summarize_plan(plan)
    parts = [f"{counts['ok']} rename(s)"]
    if counts["duplicate"]:
        parts.append(f"{counts['duplicate']} duplicate(s)")
    if counts["skip"]:
        parts.append(f"{counts['skip']} skipped")
    if counts["error"]:
        parts.append(f"{counts['error']} error(s)")
    summary = ", ".join(parts)
    if counts["directory_count"] > 1:
        summary += f" across {counts['directory_count']} directories"
    return summary


def summarize_results(results: list[RenameResult]) -> dict[str, int]:
    """Summarize rename results by outcome.

    Returns dict with keys: renamed, skipped, errors, directory_count.
    """
    return {
        "renamed": sum(1 for r in results if r.outcome == RenameOutcome.RENAMED),
        "skipped": sum(1 for r in results if r.success and r.outcome != RenameOutcome.RENAMED),
        "errors": sum(1 for r in results if not r.success),
        "directory_count": len({(r.new_path if r.success else r.old_path).parent for r in results}),
    }


def format_results_summary(results: list[RenameResult]) -> str:
    """Format rename results summary as a user-facing string."""
    counts = summarize_results(results)
    summary = f"{counts['renamed']} renamed, {counts['skipped']} skipped"
    if counts["errors"]:
        summary += f", {counts['errors']} failed"
    return summary


def get_plan_item_display(item: RenamePlanItem) -> tuple[str, str]:
    """Return (short_label, category) for a rename plan item.

    Categories: ``'ok'``, ``'duplicate'``, ``'skip'``, ``'error'``.
    Labels: ``'OK'``, ``'DUP'``, ``'SKIP'``, ``'SAME'``, ``'ERROR'``.
    """
    _DISPLAY: dict[RenameStatus, tuple[str, str]] = {
        STATUS_OK: ("OK", "ok"),
        STATUS_DUPLICATE: ("DUP", "duplicate"),
        STATUS_SKIP_NO_NAME: ("SKIP", "skip"),
        STATUS_SKIP_SAME: ("SAME", "skip"),
        STATUS_SKIP_ERROR: ("ERROR", "error"),
    }
    return _DISPLAY.get(item.status, (item.status.value, "error"))


def is_skip_status(item: RenamePlanItem) -> bool:
    """True if this item should show '-' instead of a new path."""
    return item.status in {STATUS_SKIP_NO_NAME, STATUS_SKIP_SAME, STATUS_SKIP_ERROR}


def format_result_status(result: RenameResult) -> str:
    """Derive a short display label from a rename result's outcome.

    The label is derived entirely from ``result.outcome``.  For error
    outcomes, ``result.message`` is appended as diagnostic detail when
    available (e.g. an OS-level error string).

    Returns a short string suitable for table cells such as ``"OK"``,
    ``"ERROR: Permission denied"``, or ``"Skipped (no name)"``.
    """
    _OUTCOME_DISPLAY: dict[RenameOutcome, str] = {
        RenameOutcome.RENAMED: "OK",
        RenameOutcome.ALREADY_CORRECT: "Already correct",
        RenameOutcome.SKIP_NO_NAME: "Skipped (no name)",
        RenameOutcome.SKIP_ERROR: "Skipped (error)",
        RenameOutcome.ERROR_TARGET_EXISTS: "ERROR: Target exists",
        RenameOutcome.ERROR_OS: "ERROR",
    }
    label = _OUTCOME_DISPLAY.get(result.outcome, result.outcome.value)
    if result.outcome in (RenameOutcome.ERROR_TARGET_EXISTS, RenameOutcome.ERROR_OS) and result.message:
        return f"ERROR: {result.message}"
    return label


def filter_visible_results(results: list[RenameResult]) -> list[RenameResult]:
    """Filter results to show only renamed and failed items.

    Hides skip/same rows that were already shown in the confirmation step.
    """
    return [r for r in results if not r.success or r.outcome == RenameOutcome.RENAMED]
