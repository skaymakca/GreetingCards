"""Tests for ProcessingService — PDF processing orchestration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.core.card_store import CardStore
from app.core.processing_service import ProcessingService
from app.models.card import PdfWorkerResult


def _make_worker_result(
    pdf_path: str = "/tmp/card.pdf",
    file_hash: str = "abc123",
    family_name: str = "Smith",
) -> PdfWorkerResult:
    """Create a minimal PdfWorkerResult for testing."""
    return PdfWorkerResult(
        pdf_path=pdf_path,
        file_hash=file_hash,
        family_name=family_name,
        confidence="high",
        method="ocr",
    )


class TestProcessFiles:
    """Tests for ProcessingService.process_files()."""

    @patch("app.core.processing_service.ProcessPoolExecutor")
    @patch("app.core.processing_service.multiprocessing")
    def test_calls_on_progress_for_each_file(self, mock_mp: MagicMock, mock_pool_cls: MagicMock) -> None:
        """on_progress should be called for each processed file."""
        store = CardStore()
        service = ProcessingService(store)

        wr1 = _make_worker_result(pdf_path="/tmp/a.pdf", file_hash="h1", family_name="Smith")
        wr2 = _make_worker_result(pdf_path="/tmp/b.pdf", file_hash="h2", family_name="Jones")

        # Mock the executor context manager
        mock_executor = MagicMock()
        mock_pool_cls.return_value.__enter__ = MagicMock(return_value=mock_executor)
        mock_pool_cls.return_value.__exit__ = MagicMock(return_value=False)

        # Create mock futures that return worker results
        future1 = MagicMock()
        future1.result.return_value = wr1
        future2 = MagicMock()
        future2.result.return_value = wr2

        mock_executor.submit.side_effect = [future1, future2]

        # as_completed yields futures in order
        with patch("app.core.processing_service.as_completed", return_value=iter([future1, future2])):
            progress_calls: list[tuple[int, int, str]] = []

            def on_progress(completed: int, total: int, filename: str) -> None:
                progress_calls.append((completed, total, filename))

            on_complete = MagicMock()

            service.process_files(
                [Path("/tmp/a.pdf"), Path("/tmp/b.pdf")],
                on_progress=on_progress,
                on_complete=on_complete,
            )

        assert len(progress_calls) == 2
        assert progress_calls[0][0] == 1  # completed count
        assert progress_calls[0][1] == 2  # total
        assert progress_calls[1][0] == 2
        on_complete.assert_called_once()

    @patch("app.core.processing_service.ProcessPoolExecutor")
    @patch("app.core.processing_service.multiprocessing")
    def test_stores_results_in_card_store(self, mock_mp: MagicMock, mock_pool_cls: MagicMock) -> None:
        """Worker results should be added to the CardStore."""
        store = CardStore()
        service = ProcessingService(store)

        wr = _make_worker_result(pdf_path="/tmp/card.pdf", file_hash="h1", family_name="Smith")

        mock_executor = MagicMock()
        mock_pool_cls.return_value.__enter__ = MagicMock(return_value=mock_executor)
        mock_pool_cls.return_value.__exit__ = MagicMock(return_value=False)

        future = MagicMock()
        future.result.return_value = wr
        mock_executor.submit.return_value = future

        with patch("app.core.processing_service.as_completed", return_value=iter([future])):
            service.process_files([Path("/tmp/card.pdf")])

        assert store.count == 1
        card = store.get_by_hash("h1")
        assert card is not None
        assert card.family_name == "Smith"

    @patch("app.core.processing_service.ProcessPoolExecutor")
    @patch("app.core.processing_service.multiprocessing")
    def test_handles_worker_exception(self, mock_mp: MagicMock, mock_pool_cls: MagicMock) -> None:
        """Worker exceptions should be caught and progress still reported."""
        store = CardStore()
        service = ProcessingService(store)

        mock_executor = MagicMock()
        mock_pool_cls.return_value.__enter__ = MagicMock(return_value=mock_executor)
        mock_pool_cls.return_value.__exit__ = MagicMock(return_value=False)

        future = MagicMock()
        future.result.side_effect = RuntimeError("Worker crashed")
        mock_executor.submit.return_value = future

        # Need to mock the futures dict mapping
        with patch("app.core.processing_service.as_completed", return_value=iter([future])):
            progress_calls: list[tuple[int, int, str]] = []

            def on_progress(completed: int, total: int, filename: str) -> None:
                progress_calls.append((completed, total, filename))

            on_complete = MagicMock()

            service.process_files(
                [Path("/tmp/bad.pdf")],
                on_progress=on_progress,
                on_complete=on_complete,
            )

        # Progress should still be called (even for failures)
        assert len(progress_calls) == 1
        assert progress_calls[0][0] == 1  # completed
        assert progress_calls[0][2] == "bad.pdf"  # filename from path
        # Completion should still fire
        on_complete.assert_called_once()
        # No card should be stored (worker failed)
        assert store.count == 0

    @patch("app.core.processing_service.ProcessPoolExecutor")
    @patch("app.core.processing_service.multiprocessing")
    def test_no_callbacks_when_none(self, mock_mp: MagicMock, mock_pool_cls: MagicMock) -> None:
        """Should not fail when callbacks are None."""
        store = CardStore()
        service = ProcessingService(store)

        wr = _make_worker_result(pdf_path="/tmp/card.pdf", file_hash="h1")

        mock_executor = MagicMock()
        mock_pool_cls.return_value.__enter__ = MagicMock(return_value=mock_executor)
        mock_pool_cls.return_value.__exit__ = MagicMock(return_value=False)

        future = MagicMock()
        future.result.return_value = wr
        mock_executor.submit.return_value = future

        with patch("app.core.processing_service.as_completed", return_value=iter([future])):
            # No callbacks — should not raise
            service.process_files([Path("/tmp/card.pdf")])

        assert store.count == 1


class TestScanForPdfs:
    """Tests for ProcessingService.scan_for_pdfs()."""

    def test_scan_pdf_file(self, tmp_path: Path) -> None:
        """Single PDF file should be returned."""
        pdf = tmp_path / "card.pdf"
        pdf.write_bytes(b"%PDF-1.4 test")
        result = ProcessingService.scan_for_pdfs(pdf)
        assert len(result) == 1
        assert result[0].name == "card.pdf"

    def test_scan_non_pdf_file(self, tmp_path: Path) -> None:
        """Non-PDF file should be skipped."""
        txt = tmp_path / "readme.txt"
        txt.write_text("hello")
        result = ProcessingService.scan_for_pdfs(txt)
        assert result == []

    def test_scan_directory(self, tmp_path: Path) -> None:
        """Directory should be scanned recursively."""
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "a.pdf").write_bytes(b"%PDF")
        (sub / "b.txt").write_text("hi")
        (tmp_path / "c.pdf").write_bytes(b"%PDF")
        result = ProcessingService.scan_for_pdfs(tmp_path)
        assert len(result) == 2
