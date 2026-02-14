from pathlib import Path
from app.models.card import CardResult, RenamePlanItem, RenameResult


def _is_same_file(a: Path, b: Path) -> bool:
    try:
        return a.samefile(b)
    except (OSError, ValueError):
        return False


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
    # Per-directory tracking: dir → {lowercase_name → count}
    used_names: dict[Path, dict[str, int]] = {}

    for card in cards:
        for file_path in card.file_paths:
            directory = file_path.parent

            # Ensure directory has a tracking dict
            if directory not in used_names:
                used_names[directory] = {}
            dir_names = used_names[directory]

            if card.error:
                plan.append(RenamePlanItem(file_path, file_path, "skip_error", card=card))
                dir_names[file_path.name.lower()] = 1
                continue

            target_name = card.target_filename(year)

            if not target_name:
                plan.append(RenamePlanItem(file_path, file_path, "skip_no_name", card=card))
                dir_names[file_path.name.lower()] = 1
                continue

            new_path = directory / target_name

            if new_path == file_path or _is_same_file(new_path, file_path):
                plan.append(RenamePlanItem(file_path, new_path, "skip_same", card=card))
                dir_names[target_name.lower()] = 1
                continue

            # Handle duplicates (per-directory)
            base_name = target_name
            key = base_name.lower()
            if key in dir_names:
                dir_names[key] += 1
                stem = new_path.stem
                suffix = new_path.suffix
                new_path = directory / f"{stem} ({dir_names[key]}){suffix}"
                # If duplicate would rename to itself, treat as skip_same
                if new_path == file_path:
                    plan.append(RenamePlanItem(file_path, new_path, "skip_same", card=card))
                else:
                    plan.append(RenamePlanItem(file_path, new_path, "duplicate", card=card))
            else:
                dir_names[key] = 1
                # Check if file already exists on disk
                if new_path.exists() and not _is_same_file(new_path, file_path):
                    dir_names[key] += 1
                    stem = new_path.stem
                    suffix = new_path.suffix
                    new_path = directory / f"{stem} ({dir_names[key]}){suffix}"
                    # If duplicate would rename to itself, treat as skip_same
                    if new_path == file_path:
                        plan.append(RenamePlanItem(file_path, new_path, "skip_same", card=card))
                    else:
                        plan.append(RenamePlanItem(file_path, new_path, "duplicate", card=card))
                else:
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
