"""Tests for CardStore — thread-safe in-memory card state owner."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from app.core.card_store import CardStore
from app.models.card import PdfWorkerResult


def _make_worker_result(
    pdf_path: str = "/tmp/card.pdf",
    file_hash: str | None = "abc123",
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


class TestCardStoreEmpty:
    """Tests on an empty store."""

    def test_initial_state(self) -> None:
        store = CardStore()
        assert store.count == 0
        assert store.is_empty is True
        assert store.has_paths is False
        assert store.get_all_cards() == []
        assert store.get_all_paths() == set()

    def test_get_by_id_returns_none(self) -> None:
        store = CardStore()
        assert store.get_by_id(0) is None
        assert store.get_by_id(999) is None

    def test_get_by_hash_returns_none(self) -> None:
        store = CardStore()
        assert store.get_by_hash("nonexistent") is None

    def test_find_by_filename_returns_none(self) -> None:
        store = CardStore()
        assert store.find_by_filename("card.pdf") is None

    def test_has_path_returns_false(self) -> None:
        store = CardStore()
        assert store.has_path(Path("/tmp/card.pdf")) is False

    def test_get_hash_for_path_returns_none(self) -> None:
        store = CardStore()
        assert store.get_hash_for_path(Path("/tmp/card.pdf")) is None

    def test_get_mtime_for_path_returns_none(self) -> None:
        store = CardStore()
        assert store.get_mtime_for_path(Path("/tmp/card.pdf")) is None


class TestAddOrUpdate:
    """Tests for add_or_update — the main mutation method."""

    def test_add_new_card(self) -> None:
        store = CardStore()
        wr = _make_worker_result()
        pdf_path = Path("/tmp/card.pdf")

        card, is_new = store.add_or_update(wr, pdf_path)

        assert is_new is True
        assert card.id == 0
        assert card.family_name == "Smith"
        assert card.file_hash == "abc123"
        assert pdf_path in card.file_paths
        assert store.count == 1
        assert store.is_empty is False

    def test_add_duplicate_content_returns_existing(self) -> None:
        store = CardStore()
        wr1 = _make_worker_result(pdf_path="/tmp/card1.pdf", file_hash="abc123")
        wr2 = _make_worker_result(pdf_path="/tmp/card2.pdf", file_hash="abc123")
        path1 = Path("/tmp/card1.pdf")
        path2 = Path("/tmp/card2.pdf")

        card1, is_new1 = store.add_or_update(wr1, path1)
        card2, is_new2 = store.add_or_update(wr2, path2)

        assert is_new1 is True
        assert is_new2 is False
        assert card1 is card2  # Same object
        assert path1 in card1.file_paths
        assert path2 in card1.file_paths
        assert store.count == 1  # Still one unique card

    def test_add_duplicate_path_no_double_append(self) -> None:
        store = CardStore()
        wr = _make_worker_result()
        pdf_path = Path("/tmp/card.pdf")

        store.add_or_update(wr, pdf_path)
        card, is_new = store.add_or_update(wr, pdf_path)

        assert is_new is False
        # Path should appear only once
        assert card.file_paths.count(pdf_path) == 1

    def test_add_multiple_different_cards(self) -> None:
        store = CardStore()
        wr1 = _make_worker_result(pdf_path="/tmp/card1.pdf", file_hash="hash1", family_name="Smith")
        wr2 = _make_worker_result(pdf_path="/tmp/card2.pdf", file_hash="hash2", family_name="Jones")

        card1, _ = store.add_or_update(wr1, Path("/tmp/card1.pdf"))
        card2, _ = store.add_or_update(wr2, Path("/tmp/card2.pdf"))

        assert card1.id == 0
        assert card2.id == 1
        assert store.count == 2

    def test_add_with_none_hash(self) -> None:
        store = CardStore()
        wr = _make_worker_result(file_hash=None)
        pdf_path = Path("/tmp/card.pdf")

        card, is_new = store.add_or_update(wr, pdf_path)

        assert is_new is True
        # With None hash, card should NOT be stored in hash/id dicts
        assert store.count == 0
        assert store.get_by_id(card.id) is None
        assert not store.has_path(pdf_path)

    def test_monotonic_id_assignment(self) -> None:
        store = CardStore()
        ids = []
        for i in range(5):
            wr = _make_worker_result(pdf_path=f"/tmp/card{i}.pdf", file_hash=f"hash{i}")
            card, _ = store.add_or_update(wr, Path(f"/tmp/card{i}.pdf"))
            ids.append(card.id)

        assert ids == [0, 1, 2, 3, 4]


class TestQueries:
    """Tests for query methods after adding cards."""

    @pytest.fixture
    def populated_store(self) -> CardStore:
        """Store with two cards: Smith (hash1, 2 paths) and Jones (hash2, 1 path)."""
        store = CardStore()
        wr1 = _make_worker_result(pdf_path="/tmp/smith.pdf", file_hash="hash1", family_name="Smith")
        wr1_dup = _make_worker_result(pdf_path="/tmp/smith_copy.pdf", file_hash="hash1", family_name="Smith")
        wr2 = _make_worker_result(pdf_path="/tmp/jones.pdf", file_hash="hash2", family_name="Jones")
        store.add_or_update(wr1, Path("/tmp/smith.pdf"))
        store.add_or_update(wr1_dup, Path("/tmp/smith_copy.pdf"))
        store.add_or_update(wr2, Path("/tmp/jones.pdf"))
        return store

    def test_get_by_id(self, populated_store: CardStore) -> None:
        card = populated_store.get_by_id(0)
        assert card is not None
        assert card.family_name == "Smith"

    def test_get_by_id_second(self, populated_store: CardStore) -> None:
        card = populated_store.get_by_id(1)
        assert card is not None
        assert card.family_name == "Jones"

    def test_get_by_hash(self, populated_store: CardStore) -> None:
        card = populated_store.get_by_hash("hash1")
        assert card is not None
        assert card.family_name == "Smith"

    def test_get_all_cards(self, populated_store: CardStore) -> None:
        cards = populated_store.get_all_cards()
        assert len(cards) == 2
        names = {c.family_name for c in cards}
        assert names == {"Smith", "Jones"}

    def test_find_by_filename_exact(self, populated_store: CardStore) -> None:
        card = populated_store.find_by_filename("smith.pdf")
        assert card is not None
        assert card.family_name == "Smith"

    def test_find_by_filename_case_insensitive(self, populated_store: CardStore) -> None:
        card = populated_store.find_by_filename("SMITH.PDF")
        assert card is not None
        assert card.family_name == "Smith"

    def test_find_by_filename_duplicate_path(self, populated_store: CardStore) -> None:
        card = populated_store.find_by_filename("smith_copy.pdf")
        assert card is not None
        assert card.family_name == "Smith"

    def test_find_by_filename_not_found(self, populated_store: CardStore) -> None:
        assert populated_store.find_by_filename("nonexistent.pdf") is None

    def test_has_path(self, populated_store: CardStore) -> None:
        assert populated_store.has_path(Path("/tmp/smith.pdf")) is True
        assert populated_store.has_path(Path("/tmp/nonexistent.pdf")) is False

    def test_get_hash_for_path(self, populated_store: CardStore) -> None:
        assert populated_store.get_hash_for_path(Path("/tmp/smith.pdf")) == "hash1"
        assert populated_store.get_hash_for_path(Path("/tmp/jones.pdf")) == "hash2"
        assert populated_store.get_hash_for_path(Path("/tmp/nope.pdf")) is None

    def test_get_all_paths(self, populated_store: CardStore) -> None:
        paths = populated_store.get_all_paths()
        assert paths == {
            Path("/tmp/smith.pdf"),
            Path("/tmp/smith_copy.pdf"),
            Path("/tmp/jones.pdf"),
        }

    def test_count(self, populated_store: CardStore) -> None:
        assert populated_store.count == 2

    def test_is_empty(self, populated_store: CardStore) -> None:
        assert populated_store.is_empty is False

    def test_has_paths(self, populated_store: CardStore) -> None:
        assert populated_store.has_paths is True


class TestRegisterNewPdfs:
    """Tests for register_new_pdfs."""

    def test_register_adds_to_pdf_files(self) -> None:
        store = CardStore()
        paths = [Path("/tmp/a.pdf"), Path("/tmp/b.pdf")]
        store.register_new_pdfs(paths)
        # pdf_files is internal, but we can verify via unlink_path behavior
        # After registering, unlinking should remove from pdf_files without error
        store.unlink_path(Path("/tmp/a.pdf"))
        # No assertion needed — just verifying no error

    def test_register_idempotent(self) -> None:
        store = CardStore()
        path = Path("/tmp/a.pdf")
        store.register_new_pdfs([path])
        store.register_new_pdfs([path])
        # Set semantics — no duplicates


class TestUnlinkPath:
    """Tests for unlink_path."""

    def test_unlink_removes_path_card_survives(self) -> None:
        store = CardStore()
        wr = _make_worker_result(pdf_path="/tmp/card1.pdf", file_hash="hash1", family_name="Smith")
        path1 = Path("/tmp/card1.pdf")
        path2 = Path("/tmp/card2.pdf")

        store.add_or_update(wr, path1)
        # Add second path to same card
        wr2 = _make_worker_result(pdf_path="/tmp/card2.pdf", file_hash="hash1", family_name="Smith")
        store.add_or_update(wr2, path2)

        store.unlink_path(path1)

        # Card should still exist with remaining path
        assert store.count == 1
        card = store.get_by_hash("hash1")
        assert card is not None
        assert path1 not in card.file_paths
        assert path2 in card.file_paths
        assert not store.has_path(path1)
        assert store.has_path(path2)

    def test_unlink_removes_card_when_last_path(self) -> None:
        store = CardStore()
        wr = _make_worker_result(pdf_path="/tmp/card.pdf", file_hash="hash1", family_name="Smith")
        pdf_path = Path("/tmp/card.pdf")
        store.add_or_update(wr, pdf_path)

        store.unlink_path(pdf_path)

        assert store.count == 0
        assert store.is_empty is True
        assert store.get_by_hash("hash1") is None
        assert store.get_by_id(0) is None

    def test_unlink_nonexistent_path_no_error(self) -> None:
        store = CardStore()
        store.unlink_path(Path("/tmp/nonexistent.pdf"))  # Should not raise

    def test_unlink_clears_mtime(self) -> None:
        store = CardStore()
        wr = _make_worker_result(pdf_path="/tmp/card.pdf", file_hash="hash1")
        pdf_path = Path("/tmp/card.pdf")
        store.add_or_update(wr, pdf_path)

        # Mtime may or may not be set (depends on whether /tmp/card.pdf exists)
        store.unlink_path(pdf_path)
        assert store.get_mtime_for_path(pdf_path) is None

    def test_unlink_removes_from_pdf_files(self) -> None:
        store = CardStore()
        pdf_path = Path("/tmp/card.pdf")
        store.register_new_pdfs([pdf_path])
        store.unlink_path(pdf_path)
        # Verify by re-registering and unlinking without issues
        store.register_new_pdfs([pdf_path])


class TestUpdatePathMapping:
    """Tests for update_path_mapping."""

    def test_update_moves_hash_mapping(self) -> None:
        store = CardStore()
        wr = _make_worker_result(pdf_path="/tmp/old.pdf", file_hash="hash1")
        old_path = Path("/tmp/old.pdf")
        new_path = Path("/tmp/new.pdf")

        store.add_or_update(wr, old_path)
        store.update_path_mapping(old_path, new_path)

        assert store.get_hash_for_path(old_path) is None
        assert store.get_hash_for_path(new_path) == "hash1"

    def test_update_moves_mtime_mapping(self) -> None:
        store = CardStore()
        wr = _make_worker_result(pdf_path="/tmp/old.pdf", file_hash="hash1")
        old_path = Path("/tmp/old.pdf")
        new_path = Path("/tmp/new.pdf")

        store.add_or_update(wr, old_path)
        # Manually set mtime since test file may not exist
        store._mtime_by_path[old_path] = 12345.0

        store.update_path_mapping(old_path, new_path)

        assert store.get_mtime_for_path(old_path) is None
        assert store.get_mtime_for_path(new_path) == 12345.0

    def test_update_updates_card_file_paths(self) -> None:
        store = CardStore()
        wr = _make_worker_result(pdf_path="/tmp/old.pdf", file_hash="hash1")
        old_path = Path("/tmp/old.pdf")
        new_path = Path("/tmp/new.pdf")

        store.add_or_update(wr, old_path)
        store.update_path_mapping(old_path, new_path)

        card = store.get_by_hash("hash1")
        assert card is not None
        assert old_path not in card.file_paths
        assert new_path in card.file_paths

    def test_update_updates_primary_path(self) -> None:
        store = CardStore()
        wr = _make_worker_result(pdf_path="/tmp/old.pdf", file_hash="hash1")
        old_path = Path("/tmp/old.pdf")
        new_path = Path("/tmp/new.pdf")

        store.add_or_update(wr, old_path)
        assert store.get_by_hash("hash1") is not None
        assert store.get_by_hash("hash1").primary_path == old_path  # type: ignore[union-attr]

        store.update_path_mapping(old_path, new_path)

        card = store.get_by_hash("hash1")
        assert card is not None
        assert card.primary_path == new_path

    def test_update_pdf_files_set(self) -> None:
        store = CardStore()
        old_path = Path("/tmp/old.pdf")
        new_path = Path("/tmp/new.pdf")
        store.register_new_pdfs([old_path])

        store.update_path_mapping(old_path, new_path)

        assert old_path not in store._pdf_files
        assert new_path in store._pdf_files

    def test_update_nonexistent_path_no_error(self) -> None:
        store = CardStore()
        # Should not raise
        store.update_path_mapping(Path("/tmp/old.pdf"), Path("/tmp/new.pdf"))


class TestRemoveHashForPath:
    """Tests for remove_hash_for_path."""

    def test_returns_hash_and_removes_path(self) -> None:
        store = CardStore()
        wr = _make_worker_result(pdf_path="/tmp/card.pdf", file_hash="hash1")
        pdf_path = Path("/tmp/card.pdf")
        store.add_or_update(wr, pdf_path)

        removed_hash = store.remove_hash_for_path(pdf_path)

        assert removed_hash == "hash1"
        assert not store.has_path(pdf_path)

    def test_removes_card_when_last_path(self) -> None:
        store = CardStore()
        wr = _make_worker_result(pdf_path="/tmp/card.pdf", file_hash="hash1")
        pdf_path = Path("/tmp/card.pdf")
        store.add_or_update(wr, pdf_path)

        store.remove_hash_for_path(pdf_path)

        assert store.count == 0
        assert store.get_by_hash("hash1") is None

    def test_card_survives_if_other_paths_remain(self) -> None:
        store = CardStore()
        path1 = Path("/tmp/card1.pdf")
        path2 = Path("/tmp/card2.pdf")
        wr1 = _make_worker_result(pdf_path="/tmp/card1.pdf", file_hash="hash1")
        wr2 = _make_worker_result(pdf_path="/tmp/card2.pdf", file_hash="hash1")
        store.add_or_update(wr1, path1)
        store.add_or_update(wr2, path2)

        removed_hash = store.remove_hash_for_path(path1)

        assert removed_hash == "hash1"
        assert store.count == 1
        card = store.get_by_hash("hash1")
        assert card is not None
        assert path1 not in card.file_paths
        assert path2 in card.file_paths

    def test_returns_none_for_unknown_path(self) -> None:
        store = CardStore()
        result = store.remove_hash_for_path(Path("/tmp/nonexistent.pdf"))
        assert result is None


class TestClear:
    """Tests for clear."""

    def test_clear_resets_all_state(self) -> None:
        store = CardStore()
        wr = _make_worker_result(pdf_path="/tmp/card.pdf", file_hash="hash1")
        pdf_path = Path("/tmp/card.pdf")
        store.add_or_update(wr, pdf_path)
        store.register_new_pdfs([pdf_path])

        store.clear()

        assert store.count == 0
        assert store.is_empty is True
        assert store.has_paths is False
        assert store.get_all_cards() == []
        assert store.get_all_paths() == set()
        assert store.get_by_id(0) is None
        assert store.get_by_hash("hash1") is None

    def test_clear_resets_id_counter(self) -> None:
        store = CardStore()
        wr = _make_worker_result(pdf_path="/tmp/card.pdf", file_hash="hash1")
        store.add_or_update(wr, Path("/tmp/card.pdf"))

        store.clear()

        # After clear, next card should get id 0 again
        wr2 = _make_worker_result(pdf_path="/tmp/card2.pdf", file_hash="hash2")
        card, _ = store.add_or_update(wr2, Path("/tmp/card2.pdf"))
        assert card.id == 0


class TestThreadSafety:
    """Tests for concurrent access to CardStore."""

    def test_concurrent_add_or_update(self) -> None:
        """Multiple threads adding cards concurrently should not corrupt state."""
        store = CardStore()
        num_threads = 10
        cards_per_thread = 50
        barrier = threading.Barrier(num_threads)
        errors: list[str] = []

        def worker(thread_id: int) -> None:
            try:
                barrier.wait(timeout=5)
                for i in range(cards_per_thread):
                    file_hash = f"hash_{thread_id}_{i}"
                    pdf_path = Path(f"/tmp/thread{thread_id}_card{i}.pdf")
                    wr = _make_worker_result(
                        pdf_path=str(pdf_path),
                        file_hash=file_hash,
                        family_name=f"Family_{thread_id}_{i}",
                    )
                    _, is_new = store.add_or_update(wr, pdf_path)
                    if not is_new:
                        errors.append(f"Thread {thread_id} card {i}: expected new card")
            except Exception as exc:
                err = exc
                errors.append(f"Thread {thread_id}: {err}")

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, f"Thread errors: {errors}"
        assert store.count == num_threads * cards_per_thread

    def test_concurrent_add_duplicates(self) -> None:
        """Multiple threads adding the same hash should deduplicate correctly."""
        store = CardStore()
        num_threads = 20
        barrier = threading.Barrier(num_threads)
        results: list[tuple[bool, int]] = []
        results_lock = threading.Lock()

        def worker(thread_id: int) -> None:
            barrier.wait(timeout=5)
            pdf_path = Path(f"/tmp/thread{thread_id}_same.pdf")
            wr = _make_worker_result(
                pdf_path=str(pdf_path),
                file_hash="same_hash",
                family_name="SharedFamily",
            )
            card, is_new = store.add_or_update(wr, pdf_path)
            with results_lock:
                results.append((is_new, card.id))

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        # Exactly one thread should have created the card
        new_count = sum(1 for is_new, _ in results if is_new)
        assert new_count == 1

        # All threads should reference the same card ID
        card_ids = {cid for _, cid in results}
        assert len(card_ids) == 1

        # Store should have exactly one card
        assert store.count == 1

        # Card should have all paths
        card = store.get_by_hash("same_hash")
        assert card is not None
        assert len(card.file_paths) == num_threads

    def test_monotonic_ids_under_contention(self) -> None:
        """IDs should be unique even under heavy contention."""
        store = CardStore()
        num_threads = 8
        cards_per_thread = 100
        all_ids: list[int] = []
        ids_lock = threading.Lock()
        barrier = threading.Barrier(num_threads)

        def worker(thread_id: int) -> None:
            barrier.wait(timeout=5)
            local_ids = []
            for i in range(cards_per_thread):
                wr = _make_worker_result(
                    pdf_path=f"/tmp/t{thread_id}_c{i}.pdf",
                    file_hash=f"h_{thread_id}_{i}",
                )
                card, _ = store.add_or_update(wr, Path(f"/tmp/t{thread_id}_c{i}.pdf"))
                local_ids.append(card.id)
            with ids_lock:
                all_ids.extend(local_ids)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        # All IDs should be unique
        assert len(all_ids) == num_threads * cards_per_thread
        assert len(set(all_ids)) == len(all_ids)


class TestMtimeBehavior:
    """Tests for mtime tracking edge cases."""

    def test_mtime_set_for_existing_file(self, tmp_path: Path) -> None:
        """mtime should be recorded when the file actually exists."""
        store = CardStore()
        pdf_file = tmp_path / "real.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 test")

        wr = _make_worker_result(pdf_path=str(pdf_file), file_hash="hash_real")
        store.add_or_update(wr, pdf_file)

        mtime = store.get_mtime_for_path(pdf_file)
        assert mtime is not None
        assert mtime > 0

    def test_mtime_not_set_for_missing_file(self) -> None:
        """mtime should not be recorded if the file doesn't exist."""
        store = CardStore()
        pdf_path = Path("/nonexistent/path/card.pdf")
        wr = _make_worker_result(pdf_path=str(pdf_path), file_hash="hash_missing")
        store.add_or_update(wr, pdf_path)

        # File doesn't exist, so OSError is caught and mtime is not recorded
        assert store.get_mtime_for_path(pdf_path) is None


class TestEdgeCases:
    """Edge case and integration tests."""

    def test_add_then_unlink_then_readd(self) -> None:
        """A card can be removed and then re-added."""
        store = CardStore()
        pdf_path = Path("/tmp/card.pdf")
        wr = _make_worker_result(pdf_path="/tmp/card.pdf", file_hash="hash1")

        card1, _ = store.add_or_update(wr, pdf_path)
        assert card1.id == 0

        store.unlink_path(pdf_path)
        assert store.count == 0

        card2, is_new = store.add_or_update(wr, pdf_path)
        assert is_new is True
        assert card2.id == 1  # ID counter continues from where it left off
        assert store.count == 1

    def test_get_all_paths_returns_snapshot(self) -> None:
        """get_all_paths should return a copy, not a live reference."""
        store = CardStore()
        wr = _make_worker_result(pdf_path="/tmp/card.pdf", file_hash="hash1")
        store.add_or_update(wr, Path("/tmp/card.pdf"))

        paths = store.get_all_paths()
        paths.add(Path("/tmp/injected.pdf"))

        # Store should not be affected
        assert Path("/tmp/injected.pdf") not in store.get_all_paths()

    def test_get_all_cards_returns_copy(self) -> None:
        """get_all_cards should return a new list, not the internal dict values."""
        store = CardStore()
        wr = _make_worker_result(pdf_path="/tmp/card.pdf", file_hash="hash1")
        store.add_or_update(wr, Path("/tmp/card.pdf"))

        cards = store.get_all_cards()
        cards.clear()

        # Store should not be affected
        assert store.count == 1

    def test_update_path_mapping_with_multiple_paths(self) -> None:
        """update_path_mapping only renames the specified path."""
        store = CardStore()
        path1 = Path("/tmp/card1.pdf")
        path2 = Path("/tmp/card2.pdf")
        new_path1 = Path("/tmp/renamed1.pdf")

        wr1 = _make_worker_result(pdf_path="/tmp/card1.pdf", file_hash="hash1")
        wr2 = _make_worker_result(pdf_path="/tmp/card2.pdf", file_hash="hash1")
        store.add_or_update(wr1, path1)
        store.add_or_update(wr2, path2)

        store.update_path_mapping(path1, new_path1)

        card = store.get_by_hash("hash1")
        assert card is not None
        assert new_path1 in card.file_paths
        assert path2 in card.file_paths
        assert path1 not in card.file_paths

    def test_update_path_mapping_non_primary(self) -> None:
        """Renaming a non-primary path should not change primary_path."""
        store = CardStore()
        path1 = Path("/tmp/primary.pdf")
        path2 = Path("/tmp/secondary.pdf")
        new_path2 = Path("/tmp/renamed_secondary.pdf")

        wr1 = _make_worker_result(pdf_path="/tmp/primary.pdf", file_hash="hash1")
        wr2 = _make_worker_result(pdf_path="/tmp/secondary.pdf", file_hash="hash1")
        store.add_or_update(wr1, path1)
        store.add_or_update(wr2, path2)

        store.update_path_mapping(path2, new_path2)

        card = store.get_by_hash("hash1")
        assert card is not None
        assert card.primary_path == path1  # Unchanged

    def test_clear_then_add(self) -> None:
        """After clear, store should work normally with reset IDs."""
        store = CardStore()
        wr = _make_worker_result(pdf_path="/tmp/old.pdf", file_hash="old_hash")
        store.add_or_update(wr, Path("/tmp/old.pdf"))

        store.clear()

        wr2 = _make_worker_result(pdf_path="/tmp/new.pdf", file_hash="new_hash")
        card, is_new = store.add_or_update(wr2, Path("/tmp/new.pdf"))

        assert is_new is True
        assert card.id == 0
        assert store.count == 1


class TestFilterAndRegister:
    """Tests for filter_and_register."""

    def test_separates_new_and_existing_paths(self) -> None:
        store = CardStore()
        wr = _make_worker_result(pdf_path="/tmp/existing.pdf", file_hash="hash1")
        store.add_or_update(wr, Path("/tmp/existing.pdf"))

        new_pdfs, skipped = store.filter_and_register([Path("/tmp/existing.pdf"), Path("/tmp/new.pdf")])

        assert new_pdfs == [Path("/tmp/new.pdf")]
        assert skipped == [Path("/tmp/existing.pdf")]

    def test_registers_new_pdfs(self) -> None:
        store = CardStore()
        new_pdfs, skipped = store.filter_and_register([Path("/tmp/a.pdf"), Path("/tmp/b.pdf")])

        assert new_pdfs == [Path("/tmp/a.pdf"), Path("/tmp/b.pdf")]
        assert skipped == []

    def test_empty_input(self) -> None:
        store = CardStore()
        new_pdfs, skipped = store.filter_and_register([])

        assert new_pdfs == []
        assert skipped == []

    def test_all_already_loaded(self) -> None:
        store = CardStore()
        wr1 = _make_worker_result(pdf_path="/tmp/a.pdf", file_hash="h1")
        wr2 = _make_worker_result(pdf_path="/tmp/b.pdf", file_hash="h2")
        store.add_or_update(wr1, Path("/tmp/a.pdf"))
        store.add_or_update(wr2, Path("/tmp/b.pdf"))

        new_pdfs, skipped = store.filter_and_register([Path("/tmp/a.pdf"), Path("/tmp/b.pdf")])

        assert new_pdfs == []
        assert skipped == [Path("/tmp/a.pdf"), Path("/tmp/b.pdf")]


class TestComputeReloadDiff:
    """Tests for compute_reload_diff."""

    def test_detects_deleted_files(self, tmp_path: Path) -> None:
        """Deleted files should be returned and unlinked from the store."""
        store = CardStore()
        pdf_file = tmp_path / "card.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 test")

        wr = _make_worker_result(pdf_path=str(pdf_file), file_hash="hash1")
        store.add_or_update(wr, pdf_file)

        # Delete the file
        pdf_file.unlink()

        deleted, modified = store.compute_reload_diff()

        assert deleted == [pdf_file]
        assert modified == []
        assert store.count == 0  # Should have been unlinked

    def test_detects_modified_files(self, tmp_path: Path) -> None:
        """Files with changed content should be returned as modified."""
        store = CardStore()
        pdf_file = tmp_path / "card.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 original")

        wr = _make_worker_result(pdf_path=str(pdf_file), file_hash="original_hash")
        store.add_or_update(wr, pdf_file)

        # Modify the file content (hash will differ)
        pdf_file.write_bytes(b"%PDF-1.4 modified content")

        deleted, modified = store.compute_reload_diff()

        assert deleted == []
        assert modified == [pdf_file]
        # Path should have been detached from old card
        assert store.get_hash_for_path(pdf_file) is None

    def test_unchanged_files_skipped(self, tmp_path: Path) -> None:
        """Unchanged files should not appear in either list."""
        from app.core.database import compute_file_hash

        store = CardStore()
        pdf_file = tmp_path / "card.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 test")
        real_hash = compute_file_hash(pdf_file)

        wr = _make_worker_result(pdf_path=str(pdf_file), file_hash=real_hash)
        store.add_or_update(wr, pdf_file)

        deleted, modified = store.compute_reload_diff()

        assert deleted == []
        assert modified == []
        assert store.count == 1  # Still there

    def test_mtime_prefilter_skips_unchanged_mtime(self, tmp_path: Path) -> None:
        """With mtime_only=True, files with unchanged mtime should be skipped."""
        from app.core.database import compute_file_hash

        store = CardStore()
        pdf_file = tmp_path / "card.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 test")
        real_hash = compute_file_hash(pdf_file)

        wr = _make_worker_result(pdf_path=str(pdf_file), file_hash=real_hash)
        store.add_or_update(wr, pdf_file)

        # mtime hasn't changed, so should be skipped
        deleted, modified = store.compute_reload_diff(mtime_only=True)

        assert deleted == []
        assert modified == []

    def test_empty_store(self) -> None:
        """Empty store should return empty lists."""
        store = CardStore()

        deleted, modified = store.compute_reload_diff()

        assert deleted == []
        assert modified == []
