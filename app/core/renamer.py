from pathlib import Path
from app.models.card import CardResult


def build_rename_plan(
    cards: list[CardResult], year: str
) -> list[tuple[Path, Path, str]]:
    """
    Build a rename plan: list of (old_path, new_path, status).
    Status is one of: 'ok', 'skip_no_name', 'skip_same', 'duplicate'.
    """
    plan = []
    used_names: dict[str, int] = {}

    for card in cards:
        target_name = card.target_filename(year)

        if not target_name:
            plan.append((card.pdf_path, card.pdf_path, "skip_no_name"))
            continue

        new_path = card.pdf_path.parent / target_name

        if new_path == card.pdf_path:
            plan.append((card.pdf_path, new_path, "skip_same"))
            continue

        # Handle duplicates
        base_name = target_name
        key = base_name.lower()
        if key in used_names:
            used_names[key] += 1
            stem = new_path.stem
            suffix = new_path.suffix
            new_path = new_path.parent / f"{stem} ({used_names[key]}){suffix}"
            plan.append((card.pdf_path, new_path, "duplicate"))
        else:
            used_names[key] = 1
            # Check if file already exists on disk
            if new_path.exists() and new_path != card.pdf_path:
                used_names[key] += 1
                stem = new_path.stem
                suffix = new_path.suffix
                new_path = new_path.parent / f"{stem} ({used_names[key]}){suffix}"
                plan.append((card.pdf_path, new_path, "duplicate"))
            else:
                plan.append((card.pdf_path, new_path, "ok"))

    return plan


def execute_rename_plan(plan: list[tuple[Path, Path, str]]) -> list[tuple[Path, Path, bool, str]]:
    """
    Execute a rename plan. Returns list of (old_path, new_path, success, message).
    """
    results = []
    for old_path, new_path, status in plan:
        if status.startswith("skip"):
            reason = "No name extracted" if status == "skip_no_name" else "Already named correctly"
            results.append((old_path, new_path, True, reason))
            continue

        try:
            old_path.rename(new_path)
            results.append((old_path, new_path, True, "Renamed"))
        except OSError as e:
            results.append((old_path, new_path, False, str(e)))

    return results
