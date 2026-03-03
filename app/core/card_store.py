"""Thread-safe single source of truth for in-memory card state."""

from __future__ import annotations

import threading
from pathlib import Path

from app.core.database import compute_file_hash
from app.core.pipeline.card_processor import worker_result_to_card
from app.models.card import CardResult, PdfWorkerResult


class CardStore:
    """Thread-safe single source of truth for in-memory card state.

    Owns all card dictionaries and the threading lock. Called from both the
    background PDF worker thread (add_or_update) and the main UI thread.
    """

    def __init__(self) -> None:
        self._cards_by_hash: dict[str, CardResult] = {}
        self._id_to_card: dict[int, CardResult] = {}
        self._hash_by_path: dict[Path, str] = {}
        self._mtime_by_path: dict[Path, float] = {}
        self._pdf_files: set[Path] = set()
        self._next_card_id: int = 0
        self._lock = threading.Lock()

    # ── Queries (main thread, no lock needed) ──
    # These read-only accessors run exclusively on the main (UI) thread.
    # Thread safety relies on the GIL guaranteeing atomic dict reads; the
    # background worker only mutates via add_or_update() under self._lock.
    # This is an intentional design choice — no lock is needed here.

    def get_by_id(self, card_id: int) -> CardResult | None:
        """Get card by ID. O(1) lookup."""
        return self._id_to_card.get(card_id)

    def get_by_hash(self, file_hash: str) -> CardResult | None:
        """Get card by content hash."""
        return self._cards_by_hash.get(file_hash)

    def get_all_cards(self) -> list[CardResult]:
        """Return all loaded cards as a list."""
        return list(self._cards_by_hash.values())

    def find_by_filename(self, filename: str) -> CardResult | None:
        """Find a card by filename (case-insensitive match on any file_path)."""
        lower = filename.lower()
        for card in self._cards_by_hash.values():
            for p in card.file_paths:
                if p.name.lower() == lower:
                    return card
        return None

    def has_path(self, path: Path) -> bool:
        """Check if a path is already loaded."""
        return path in self._hash_by_path

    def get_hash_for_path(self, path: Path) -> str | None:
        """Get the content hash for a given path."""
        return self._hash_by_path.get(path)

    def get_mtime_for_path(self, path: Path) -> float | None:
        """Get the cached mtime for a given path."""
        return self._mtime_by_path.get(path)

    def get_all_paths(self) -> set[Path]:
        """Return snapshot of all loaded paths."""
        return set(self._hash_by_path.keys())

    @property
    def count(self) -> int:
        """Number of unique cards (by content hash)."""
        return len(self._cards_by_hash)

    @property
    def is_empty(self) -> bool:
        """True if no cards are loaded."""
        return not self._cards_by_hash

    @property
    def has_paths(self) -> bool:
        """True if any paths are loaded (used for reload checks)."""
        return bool(self._hash_by_path)

    def derive_folders(self) -> list[Path]:
        """Derive sorted unique source folders from all loaded cards."""
        return sorted({p.parent for card in self._cards_by_hash.values() for p in card.file_paths})

    # ── Mutations (thread-safe via internal lock) ──

    def add_or_update(self, worker_result: PdfWorkerResult, pdf_path: Path) -> tuple[CardResult, bool]:
        """Process a worker result: deduplicate or create new card.

        Called from the background processing thread -- must be thread-safe.

        Returns:
            (card, is_new) -- the card and whether it was newly created
        """
        file_hash = worker_result.file_hash
        with self._lock:
            if file_hash and file_hash in self._cards_by_hash:
                # Duplicate content — add path to existing card
                existing = self._cards_by_hash[file_hash]
                if pdf_path not in existing.file_paths:
                    existing.file_paths.append(pdf_path)
                card = existing
                is_new = False
            else:
                # New content — create new card
                card_id = self._next_card_id
                self._next_card_id += 1
                card = worker_result_to_card(worker_result, card_id)
                # Cards with null file_hash (e.g. processing errors) are intentionally
                # not stored in the lookup dicts — they exist only as transient results
                # and cannot be deduplicated or looked up by hash.
                if file_hash is not None:
                    self._cards_by_hash[file_hash] = card
                    self._id_to_card[card.id] = card
                is_new = True

            # Always update path → hash mapping
            if file_hash is not None:
                self._hash_by_path[pdf_path] = file_hash
                try:
                    self._mtime_by_path[pdf_path] = pdf_path.stat().st_mtime
                except OSError:
                    pass  # File vanished; reload will re-check

        return card, is_new

    # noinspection GrazieInspection
    def register_new_pdfs(self, paths: list[Path]) -> None:
        """Add paths to the pdf_files set (called before processing)."""
        self._pdf_files.update(paths)

    # The methods below (register_new_pdfs, _detach_path, unlink_path,
    # update_path_mapping, remove_hash_for_path) run on the main (UI) thread
    # and mutate dicts without holding self._lock.  This is safe because the
    # background worker only touches these dicts inside add_or_update() under
    # the lock, and Python's GIL makes individual dict operations atomic.
    # Low-risk unlocked mutations — intentional design choice.

    # noinspection GrazieInspection
    def _detach_path(self, path: Path) -> str | None:
        """Pop path from tracking dicts and detach it from its card.

        Removes path from hash_by_path, mtime_by_path, and pdf_files.
        If the card has no remaining paths, deletes the card entirely.

        Returns the file hash that was associated with the path (or None).
        """
        file_hash = self._hash_by_path.pop(path, None)
        self._mtime_by_path.pop(path, None)
        self._pdf_files.discard(path)
        if file_hash and file_hash in self._cards_by_hash:
            card = self._cards_by_hash[file_hash]
            if path in card.file_paths:
                card.file_paths.remove(path)
            if not card.file_paths:
                del self._cards_by_hash[file_hash]
                self._id_to_card.pop(card.id, None)
        return file_hash

    # noinspection GrazieInspection
    def unlink_path(self, path: Path) -> None:
        """Remove a path from all tracking dicts and its associated card.

        Pops path from hash_by_path, mtime_by_path, and pdf_files.
        Removes path from its card's file_paths list and deletes the card
        if it has no remaining paths.
        """
        self._detach_path(path)

    def update_path_mapping(self, old_path: Path, new_path: Path) -> None:
        """Update tracking dicts when a file is renamed on disk.

        Moves path -> hash and path -> mtime mappings from old_path to new_path.
        Also updates the card's file_paths list.
        """
        file_hash = self._hash_by_path.pop(old_path, None)
        if file_hash is not None:
            self._hash_by_path[new_path] = file_hash

        old_mtime = self._mtime_by_path.pop(old_path, None)
        if old_mtime is not None:
            self._mtime_by_path[new_path] = old_mtime

        self._pdf_files.discard(old_path)
        self._pdf_files.add(new_path)

        # Update file_paths on the card itself
        if file_hash and file_hash in self._cards_by_hash:
            card = self._cards_by_hash[file_hash]
            if old_path in card.file_paths:
                idx = card.file_paths.index(old_path)
                card.file_paths[idx] = new_path
                # Update primary_path if it was the renamed file
                if card.primary_path == old_path:
                    card.primary_path = new_path

    # noinspection GrazieInspection
    def remove_hash_for_path(self, path: Path) -> str | None:
        """Remove and return the hash mapping for a path (used during reload).

        Also removes the mtime and pdf_files entries, and detaches path from
        its card (removing card if no paths remain). This is more granular
        than unlink_path — it returns the old hash for comparison.
        """
        return self._detach_path(path)

    def filter_and_register(self, pdf_paths: list[Path]) -> tuple[list[Path], list[Path]]:
        """Filter out already-loaded paths and register new ones.

        Returns (new_pdfs, skipped_pdfs).
        """
        new_pdfs: list[Path] = []
        skipped_pdfs: list[Path] = []
        for path in pdf_paths:
            if self.has_path(path):
                skipped_pdfs.append(path)
            else:
                new_pdfs.append(path)
        self.register_new_pdfs(new_pdfs)
        return new_pdfs, skipped_pdfs

    def compute_reload_diff(self, *, mtime_only: bool = False) -> tuple[list[Path], list[Path]]:
        """Compute deleted and content-modified paths.

        Returns (deleted_paths, modified_paths).

        For deleted paths, calls ``unlink_path`` to clean up tracking state.
        For modified paths, calls ``remove_hash_for_path`` so the path can
        be re-processed with fresh content.

        Args:
            mtime_only: When True, use mtime as a fast pre-filter — files
                whose mtime hasn't changed are skipped without hashing.
        """
        loaded_paths = self.get_all_paths()
        deleted_paths: list[Path] = []
        modified_paths: list[Path] = []

        for path in loaded_paths:
            if not path.exists():
                self.unlink_path(path)
                deleted_paths.append(path)
            else:
                if mtime_only:
                    try:
                        current_mtime = path.stat().st_mtime
                    except OSError:
                        continue
                    if current_mtime == self.get_mtime_for_path(path):
                        continue

                old_hash = self.get_hash_for_path(path)
                try:
                    new_hash = compute_file_hash(path)
                except OSError:
                    continue
                if new_hash != old_hash:
                    self.remove_hash_for_path(path)
                    modified_paths.append(path)

        return deleted_paths, modified_paths

    def clear(self) -> None:
        """Clear all state."""
        self._cards_by_hash.clear()
        self._id_to_card.clear()
        self._hash_by_path.clear()
        self._mtime_by_path.clear()
        self._pdf_files.clear()
        self._next_card_id = 0
