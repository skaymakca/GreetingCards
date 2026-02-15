from pathlib import Path
from app.models.card import CardResult, RenamePlanItem, RenameResult


def _is_same_file(a: Path, b: Path) -> bool:
    try:
        return a.samefile(b)
    except (OSError, ValueError):
        return False


def _read_directory_names(directory: Path) -> set[str]:
    """Read all filenames in a directory into a lowercase set."""
    try:
        return {f.name.lower() for f in directory.iterdir() if f.is_file()}
    except OSError:
        return set()


def _find_available_name(
    directory: Path, stem: str, suffix: str, existing: set[str]
) -> Path:
    """Find the next available numbered filename not in the existing set.

    Tries: stem (2).suffix, stem (3).suffix, ... until one is not taken.
    """
    n = 2
    while True:
        candidate = f"{stem} ({n}){suffix}"
        if candidate.lower() not in existing:
            return directory / candidate
        n += 1


def build_rename_plan(
    cards: list[CardResult], year: str
) -> list[RenamePlanItem]:
    """
    Build a rename plan for all file paths across all cards.

    Each card may have multiple file_paths (same content in different directories).
    Duplicate name tracking is per-directory so identical names in different
    directories don't interfere with each other.

    Status is one of: 'ok', 'skip_no_name', 'skip_same', 'skip_error', 'duplicate'.
    """
    plan = []
    # Per-directory tracking: dir → set of lowercase filenames (seeded from disk)
    dir_files: dict[Path, set[str]] = {}

    for card in cards:
        for file_path in card.file_paths:
            directory = file_path.parent

            # Seed from disk on first encounter
            if directory not in dir_files:
                dir_files[directory] = _read_directory_names(directory)
            existing = dir_files[directory]

            if card.error:
                plan.append(RenamePlanItem(file_path, file_path, "skip_error", card=card))
                existing.add(file_path.name.lower())
                continue

            target_name = card.target_filename(year)

            if not target_name:
                plan.append(RenamePlanItem(file_path, file_path, "skip_no_name", card=card))
                existing.add(file_path.name.lower())
                continue

            new_path = directory / target_name

            if new_path == file_path or _is_same_file(new_path, file_path):
                plan.append(RenamePlanItem(file_path, new_path, "skip_same", card=card))
                existing.add(target_name.lower())
                continue

            # Handle duplicates (per-directory)
            if target_name.lower() in existing:
                # Temporarily remove own filename so the card can "see through"
                # its own slot — if it already occupies a correctly-numbered name,
                # _find_available_name will return that slot back as available.
                own_name = file_path.name.lower()
                had_own = own_name in existing
                existing.discard(own_name)

                new_path = _find_available_name(directory, new_path.stem, new_path.suffix, existing)

                if new_path == file_path:
                    # File already sits at the right numbered slot — skip_same
                    existing.add(own_name)
                    plan.append(RenamePlanItem(file_path, new_path, "skip_same", card=card))
                else:
                    # File moves to a new numbered slot
                    if had_own:
                        existing.add(own_name)
                    existing.add(new_path.name.lower())
                    plan.append(RenamePlanItem(file_path, new_path, "duplicate", card=card))
            else:
                existing.add(target_name.lower())
                plan.append(RenamePlanItem(file_path, new_path, "ok", card=card))

    return plan


def execute_rename_plan(plan: list[RenamePlanItem]) -> list[RenameResult]:
    """Execute a rename plan.

    After each successful rename, updates the card's file_paths and primary_path
    so they reflect the new location.
    """
    results = []
    for item in plan:
        if item.status.startswith("skip"):
            if item.status == "skip_no_name":
                reason = "No name extracted"
            elif item.status == "skip_error":
                reason = "Processing error"
            else:
                reason = "Already named correctly"
            results.append(RenameResult(item.old_path, item.new_path, True, reason))
            continue

        try:
            # Race condition protection: check if target already exists
            if item.new_path.exists() and not _is_same_file(item.new_path, item.old_path):
                results.append(RenameResult(
                    item.old_path, item.new_path, False,
                    f"Target already exists: {item.new_path.name}"
                ))
                continue

            item.old_path.rename(item.new_path)

            # Update card's file_paths and primary_path
            if item.card is not None:
                card = item.card
                try:
                    idx = card.file_paths.index(item.old_path)
                    card.file_paths[idx] = item.new_path
                except ValueError:
                    pass
                if card.primary_path == item.old_path:
                    card.primary_path = item.new_path

            results.append(RenameResult(item.old_path, item.new_path, True, "Renamed"))
        except OSError as e:
            results.append(RenameResult(item.old_path, item.new_path, False, str(e)))

    return results
