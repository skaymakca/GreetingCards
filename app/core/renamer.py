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
    Build a rename plan.
    Status is one of: 'ok', 'skip_no_name', 'skip_same', 'skip_error', 'duplicate'.
    """
    plan = []
    used_names: dict[str, int] = {}

    for card in cards:
        if card.error:
            plan.append(RenamePlanItem(card.pdf_path, card.pdf_path, "skip_error"))
            used_names[card.pdf_path.name.lower()] = 1
            continue

        target_name = card.target_filename(year)

        if not target_name:
            plan.append(RenamePlanItem(card.pdf_path, card.pdf_path, "skip_no_name"))
            used_names[card.pdf_path.name.lower()] = 1
            continue

        new_path = card.pdf_path.parent / target_name

        if new_path == card.pdf_path or _is_same_file(new_path, card.pdf_path):
            plan.append(RenamePlanItem(card.pdf_path, new_path, "skip_same"))
            used_names[target_name.lower()] = 1
            continue

        # Handle duplicates
        base_name = target_name
        key = base_name.lower()
        if key in used_names:
            used_names[key] += 1
            stem = new_path.stem
            suffix = new_path.suffix
            new_path = new_path.parent / f"{stem} ({used_names[key]}){suffix}"
            # If duplicate would rename to itself, treat as skip_same
            if new_path == card.pdf_path:
                plan.append(RenamePlanItem(card.pdf_path, new_path, "skip_same"))
            else:
                plan.append(RenamePlanItem(card.pdf_path, new_path, "duplicate"))
        else:
            used_names[key] = 1
            # Check if file already exists on disk
            if new_path.exists() and not _is_same_file(new_path, card.pdf_path):
                used_names[key] += 1
                stem = new_path.stem
                suffix = new_path.suffix
                new_path = new_path.parent / f"{stem} ({used_names[key]}){suffix}"
                # If duplicate would rename to itself, treat as skip_same
                if new_path == card.pdf_path:
                    plan.append(RenamePlanItem(card.pdf_path, new_path, "skip_same"))
                else:
                    plan.append(RenamePlanItem(card.pdf_path, new_path, "duplicate"))
            else:
                plan.append(RenamePlanItem(card.pdf_path, new_path, "ok"))

    return plan


def execute_rename_plan(plan: list[RenamePlanItem]) -> list[RenameResult]:
    """Execute a rename plan."""
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
            item.old_path.rename(item.new_path)
            results.append(RenameResult(item.old_path, item.new_path, True, "Renamed"))
        except OSError as e:
            results.append(RenameResult(item.old_path, item.new_path, False, str(e)))

    return results
