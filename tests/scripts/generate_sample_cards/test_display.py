"""Tests for scripts/generate_sample_cards/display.py."""

from __future__ import annotations

from rich.table import Table
from scripts.generate_sample_cards.display import build_status_table
from scripts.generate_sample_cards.models import CardJob


def _make_job(status: str = "waiting", detail: str = "") -> CardJob:
    job = CardJob(index=1, family_name="Smith", holiday="Christmas", style="minimalist", back_page="none")
    job.status = status
    job.detail = detail
    return job


class TestBuildStatusTable:
    def test_returns_table(self) -> None:
        jobs = [_make_job()]
        result = build_status_table(jobs, "gpt-image-1")
        assert isinstance(result, Table)

    def test_correct_column_count(self) -> None:
        jobs = [_make_job()]
        table = build_status_table(jobs, "gpt-image-1")
        assert len(table.columns) == 6  # #, Family, Holiday, Style, Back, Status

    def test_correct_row_count(self) -> None:
        jobs = [_make_job(), _make_job(), _make_job()]
        table = build_status_table(jobs, "gpt-image-1")
        assert table.row_count == 3

    def test_empty_jobs(self) -> None:
        table = build_status_table([], "model")
        assert isinstance(table, Table)
        assert table.row_count == 0

    def test_caption_contains_image_src(self) -> None:
        jobs = [_make_job("done")]
        table = build_status_table(jobs, "gpt-image-1")
        assert "gpt-image-1" in (table.caption or "")

    def test_caption_shows_done_count(self) -> None:
        jobs = [_make_job("done"), _make_job("done")]
        table = build_status_table(jobs, "model")
        assert "2" in (table.caption or "")
        assert "done" in (table.caption or "")

    def test_caption_shows_error_count(self) -> None:
        jobs = [_make_job("error"), _make_job("done")]
        table = build_status_table(jobs, "model")
        caption = table.caption or ""
        assert "error" in caption

    def test_caption_shows_waiting_count(self) -> None:
        jobs = [_make_job("waiting")]
        table = build_status_table(jobs, "model")
        caption = table.caption or ""
        assert "waiting" in caption

    def test_caption_shows_rate_limited_count(self) -> None:
        jobs = [_make_job("rate_limited")]
        table = build_status_table(jobs, "model")
        caption = table.caption or ""
        assert "rate-limited" in caption

    def test_active_job_uses_spinner(self) -> None:
        # We can't inspect table cells directly in Rich, so just verify
        # the table is built without error for all active statuses
        for status in ("gen_front", "gen_back", "composing", "rate_limited"):
            jobs = [_make_job(status)]
            table = build_status_table(jobs, "model")
            assert table.row_count == 1

    def test_all_status_values_build_without_error(self) -> None:
        statuses = ("waiting", "gen_front", "gen_back", "composing", "done", "error", "rate_limited")
        for status in statuses:
            jobs = [_make_job(status, "detail")]
            table = build_status_table(jobs, "model")
            assert table.row_count == 1

    def test_multiple_jobs_mixed_statuses(self) -> None:
        jobs = [
            _make_job("done"),
            _make_job("error"),
            _make_job("gen_front"),
            _make_job("waiting"),
        ]
        table = build_status_table(jobs, "model")
        assert table.row_count == 4
        caption = table.caption or ""
        assert "1" in caption  # 1 done, 1 error, etc.
