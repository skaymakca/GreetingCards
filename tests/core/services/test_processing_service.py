"""Tests for ProcessingService — PDF processing orchestration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.core.card_store import CardStore
from app.core.services.processing_service import ProcessingService
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

    @patch("app.core.services.processing_service.ProcessPoolExecutor")
    @patch("app.core.services.processing_service.multiprocessing")
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
        with patch("app.core.services.processing_service.as_completed", return_value=iter([future1, future2])):
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

    @patch("app.core.services.processing_service.ProcessPoolExecutor")
    @patch("app.core.services.processing_service.multiprocessing")
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

        with patch("app.core.services.processing_service.as_completed", return_value=iter([future])):
            service.process_files([Path("/tmp/card.pdf")])

        assert store.count == 1
        card = store.get_by_hash("h1")
        assert card is not None
        assert card.family_name == "Smith"

    @patch("app.core.services.processing_service.ProcessPoolExecutor")
    @patch("app.core.services.processing_service.multiprocessing")
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
        with patch("app.core.services.processing_service.as_completed", return_value=iter([future])):
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

    @patch("app.core.services.processing_service.ProcessPoolExecutor")
    @patch("app.core.services.processing_service.multiprocessing")
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

        with patch("app.core.services.processing_service.as_completed", return_value=iter([future])):
            # No callbacks — should not raise
            service.process_files([Path("/tmp/card.pdf")])

        assert store.count == 1


class TestIngestPaths:
    """Tests for ProcessingService.ingest_paths()."""

    def test_scans_and_registers_new_pdfs(self, tmp_path: Path) -> None:
        """New PDFs are scanned and registered."""
        pdf = tmp_path / "card.pdf"
        pdf.write_bytes(b"%PDF-1.4 test")
        store = CardStore()
        service = ProcessingService(store)

        new_pdfs, skipped = service.ingest_paths([tmp_path])

        assert len(new_pdfs) == 1
        assert skipped == 0

    def test_skips_already_loaded(self, tmp_path: Path) -> None:
        """Already-loaded PDFs are counted as skipped."""
        pdf = tmp_path / "card.pdf"
        pdf.write_bytes(b"%PDF-1.4 test")
        resolved = pdf.resolve()

        store = CardStore()
        store._hash_by_path[resolved] = "existing_hash"
        service = ProcessingService(store)

        new_pdfs, skipped = service.ingest_paths([tmp_path])

        assert len(new_pdfs) == 0
        assert skipped == 1

    def test_no_pdfs_returns_zeros(self, tmp_path: Path) -> None:
        """Non-PDF paths return ([], 0)."""
        txt = tmp_path / "readme.txt"
        txt.write_text("hello")
        store = CardStore()
        service = ProcessingService(store)

        new_pdfs, skipped = service.ingest_paths([txt])

        assert new_pdfs == []
        assert skipped == 0


class TestComputeReload:
    """Tests for ProcessingService.compute_reload()."""

    def test_deleted_files_returned(self, tmp_path: Path) -> None:
        """Deleted files are returned and cleaned up from store."""
        pdf = tmp_path / "card.pdf"
        pdf.write_bytes(b"fake pdf")

        store = CardStore()
        from app.models.card import CardResult, Confidence

        card = CardResult(id=0, file_paths=[pdf], primary_path=pdf, file_hash="hash1", confidence=Confidence.HIGH)
        store._cards_by_hash["hash1"] = card
        store._id_to_card[0] = card
        store._hash_by_path[pdf] = "hash1"
        store._mtime_by_path[pdf] = 100.0
        store._pdf_files.add(pdf)

        pdf.unlink()

        service = ProcessingService(store)
        deleted, modified = service.compute_reload()

        assert len(deleted) == 1
        assert pdf in deleted
        assert len(modified) == 0

    @patch("app.core.card_store.compute_file_hash")
    def test_modified_files_registered(self, mock_hash: MagicMock, tmp_path: Path) -> None:
        """Modified files are returned and re-registered in store."""
        pdf = tmp_path / "card.pdf"
        pdf.write_bytes(b"original")

        store = CardStore()
        from app.models.card import CardResult, Confidence

        card = CardResult(id=0, file_paths=[pdf], primary_path=pdf, file_hash="old_hash", confidence=Confidence.HIGH)
        store._cards_by_hash["old_hash"] = card
        store._id_to_card[0] = card
        store._hash_by_path[pdf] = "old_hash"
        store._mtime_by_path[pdf] = 100.0
        store._pdf_files.add(pdf)

        mock_hash.return_value = "new_hash"

        service = ProcessingService(store)
        deleted, modified = service.compute_reload()

        assert len(deleted) == 0
        assert len(modified) == 1
        assert pdf in modified
        # Modified paths should be re-registered in pdf_files
        assert pdf in store._pdf_files


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


class TestSetStartMethodFallback:
    """Tests for multiprocessing.set_start_method RuntimeError handling (lines 82-84)."""

    def test_set_start_method_raises_other_error_propagates(self) -> None:
        """RuntimeError without 'context has already been set' re-raises."""
        store = CardStore()
        service = ProcessingService(store)

        import pytest

        with (
            patch(
                "multiprocessing.set_start_method",
                side_effect=RuntimeError("some other error"),
            ),
            pytest.raises(RuntimeError, match="some other error"),
        ):
            service.process_files([Path("/tmp/card.pdf")])

    def test_set_start_method_context_already_set_continues(self) -> None:
        """RuntimeError with 'context has already been set' is silently caught."""
        store = CardStore()
        service = ProcessingService(store)

        mock_future = MagicMock()
        mock_future.result.side_effect = RuntimeError("Worker crashed")

        with (
            patch(
                "multiprocessing.set_start_method",
                side_effect=RuntimeError("context has already been set to 'spawn'"),
            ),
            patch("app.core.services.processing_service.ProcessPoolExecutor") as mock_pool_cls,
            patch("app.core.services.processing_service.as_completed", return_value=iter([mock_future])),
        ):
            mock_executor = MagicMock()
            mock_pool_cls.return_value.__enter__ = MagicMock(return_value=mock_executor)
            mock_pool_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_executor.submit.return_value = mock_future

            progress_calls: list[tuple[int, int, str]] = []

            def on_progress(c: int, t: int, f: str) -> None:
                progress_calls.append((c, t, f))

            service.process_files([Path("/tmp/bad.pdf")], on_progress=on_progress)

        # Worker exception caught, progress reported
        assert len(progress_calls) == 1
        assert progress_calls[0] == (1, 1, "bad.pdf")
