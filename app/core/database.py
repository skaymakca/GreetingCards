import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, String, DateTime, Text, Boolean, ForeignKey, UniqueConstraint, inspect
from sqlalchemy.orm import declarative_base, sessionmaker, Mapped, mapped_column

from app.core.paths import get_db_path
from app.models.card import CandidateInfo, CardState

Base = declarative_base()


class Settings(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String)


class Card(Base):
    """Main card record. Tracks selected name (manual or from candidates) and preferences."""
    __tablename__ = "cards"
    file_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    selected_family_name: Mapped[str | None] = mapped_column(String)  # Manual entry only
    selected_candidate_id: Mapped[int | None] = mapped_column(ForeignKey("candidates.id", use_alter=True, name="fk_card_selected_candidate"))
    remove_family: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc),
                                                  onupdate=lambda: datetime.now(timezone.utc))


class Candidate(Base):
    """Name candidates extracted via OCR or AI."""
    __tablename__ = "candidates"
    __table_args__ = (
        UniqueConstraint('file_hash', 'family_name', 'method', name='_file_name_method_uc'),
    )
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    file_hash: Mapped[str] = mapped_column(String(64), ForeignKey("cards.file_hash"), index=True)
    family_name: Mapped[str] = mapped_column(String)
    method: Mapped[str] = mapped_column(String)  # 'ocr' | 'ai'
    confidence: Mapped[str] = mapped_column(String)  # 'high' | 'medium' | 'low'
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class RawOCRResult(Base):
    """Raw OCR text preserved for potential re-processing with improved extraction logic."""
    __tablename__ = "raw_ocr_results"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    file_hash: Mapped[str] = mapped_column(String(64), ForeignKey("cards.file_hash"), index=True, unique=True)
    ocr_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class RawAIResult(Base):
    """Raw AI response preserved for debugging and potential re-processing."""
    __tablename__ = "raw_ai_results"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    file_hash: Mapped[str] = mapped_column(String(64), ForeignKey("cards.file_hash"), index=True, unique=True)
    raw_response: Mapped[str] = mapped_column(Text)  # JSON: {"best_name": "...", "alternates": [...]}
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


def _compute_schema_version() -> str:
    """Compute a hash representing the current model schema."""
    schema_parts = []
    for model in [Settings, Card, Candidate, RawOCRResult, RawAIResult]:
        cols = []
        for col in model.__table__.columns:
            cols.append(f"{col.name}:{col.type}:{col.nullable}:{col.primary_key}")
        schema_parts.append(f"{model.__tablename__}|{'|'.join(sorted(cols))}")
    schema_str = "||".join(sorted(schema_parts))
    return hashlib.sha256(schema_str.encode()).hexdigest()[:16]


_engine = None
_Session = None


def get_session():
    global _engine, _Session
    if _Session is None:
        _engine = create_engine(f"sqlite:///{get_db_path()}", echo=False)
        _Session = sessionmaker(bind=_engine)
        _ensure_schema()
    return _Session()


def _ensure_schema():
    """Check schema version; if mismatch, drop all tables and recreate."""
    expected = _compute_schema_version()
    inspector = inspect(_engine)

    if "settings" in inspector.get_table_names():
        session = _Session()
        try:
            row = session.query(Settings).filter_by(key="schema_version").first()
            if row and row.value == expected:
                return  # schema is current
        finally:
            session.close()

    # Schema mismatch or missing — drop ALL tables including orphaned ones
    # First drop tables known to SQLAlchemy
    Base.metadata.drop_all(_engine)

    # Then check for and drop any orphaned tables not in current metadata
    all_tables = inspector.get_table_names()
    known_tables = {table.name for table in Base.metadata.tables.values()}
    orphaned = set(all_tables) - known_tables

    if orphaned:
        from sqlalchemy import text
        with _engine.begin() as conn:
            for table_name in orphaned:
                conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}"'))

    # Create new schema
    Base.metadata.create_all(_engine)

    session = _Session()
    try:
        session.add(Settings(key="schema_version", value=expected))
        session.commit()
    finally:
        session.close()


def reset_database():
    """Drop all tables and recreate from scratch."""
    global _engine, _Session
    # Ensure engine exists
    if _engine is None:
        _engine = create_engine(f"sqlite:///{get_db_path()}", echo=False)
        _Session = sessionmaker(bind=_engine)

    # Drop all tables including orphaned ones
    inspector = inspect(_engine)
    all_tables = inspector.get_table_names()

    if all_tables:
        from sqlalchemy import text
        with _engine.begin() as conn:
            for table_name in all_tables:
                conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}"'))

    # Create new schema
    Base.metadata.create_all(_engine)
    session = _Session()
    try:
        session.add(Settings(key="schema_version", value=_compute_schema_version()))
        session.commit()
    finally:
        session.close()


def compute_file_hash(path: Path) -> str:
    """Compute SHA256 hash of a file's contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _clean_and_filter_names(names: list[str]) -> list[str]:
    """Apply unified cleaning and filtering to a list of names.

    This is the ONLY place where cleaning/filtering is applied.
    Raw data is persisted in the DB and cleaned on load.
    """
    from app.core.ai_analyzer import clean_family_name
    from app.core.name_formatting import deparameterize_name, sanitize_for_filename

    # Filter words that are not family names
    FILTER_OUT = {
        "unknown",  # AI response when uncertain
        "snapfish",  # Card printing service
        "shutterfly",  # Card printing service
    }

    cleaned = []
    for name in names:
        if not name:
            continue
        # Apply comprehensive cleaning
        clean_name = clean_family_name(name)
        # Remove plural 's' (Smiths → Smith)
        clean_name = deparameterize_name(clean_name)
        # Replace filesystem-invalid characters (cross-platform)
        clean_name = sanitize_for_filename(clean_name)
        # Filter out unwanted values
        if clean_name and clean_name.lower() not in FILTER_OUT:
            cleaned.append(clean_name)

    return cleaned


# --- Public API ---

# Sort order for candidates dropdown
# Priority: AI results first, then OCR, sorted by confidence within each method
_METHOD_ORDER = {"ai": 0, "ocr": 1}
_CONFIDENCE_ORDER = {"high": 0, "medium": 1, "low": 2}


def create_or_update_card(file_hash: str, remove_family: bool = False) -> None:
    """Create or update a card record. Call this when first processing a file."""
    session = get_session()
    try:
        card = session.query(Card).filter_by(file_hash=file_hash).first()
        if not card:
            card = Card(file_hash=file_hash, remove_family=remove_family)
            session.add(card)
            session.commit()
    finally:
        session.close()


def add_candidate(file_hash: str, family_name: str, method: str, confidence: str) -> int:
    """Add a name candidate (OCR or AI result). Returns candidate ID.

    Automatically creates card if it doesn't exist.
    Applies cleaning/filtering and smart title case to the name before storing.
    Returns 0 if name is filtered out.
    """
    from app.core.name_formatting import smart_title_case

    # Clean the name first
    cleaned = _clean_and_filter_names([family_name])
    if not cleaned:
        return 0  # Filtered out

    # Apply smart title case
    clean_name = smart_title_case(cleaned[0])

    session = get_session()
    try:
        # Ensure card exists
        card = session.query(Card).filter_by(file_hash=file_hash).first()
        if not card:
            card = Card(file_hash=file_hash)
            session.add(card)
            session.flush()

        # Check if candidate already exists
        existing = (session.query(Candidate)
                   .filter_by(file_hash=file_hash, family_name=clean_name, method=method)
                   .first())
        if existing:
            return existing.id

        # Add new candidate
        candidate = Candidate(
            file_hash=file_hash,
            family_name=clean_name,
            method=method,
            confidence=confidence
        )
        session.add(candidate)
        session.commit()
        return candidate.id
    finally:
        session.close()


def get_candidates(file_hash: str) -> list[CandidateInfo]:
    """Get all candidates for a file, sorted by method (AI first) then confidence.

    Priority: AI high > AI medium > AI low > OCR high > OCR medium > OCR low
    """
    session = get_session()
    try:
        candidates = (session.query(Candidate)
                     .filter_by(file_hash=file_hash)
                     .all())

        # Sort by method (AI first), then confidence (high first)
        sorted_candidates = sorted(
            candidates,
            key=lambda c: (
                _METHOD_ORDER.get(c.method, 999),
                _CONFIDENCE_ORDER.get(c.confidence, 999)
            )
        )

        return [
            CandidateInfo(
                id=c.id,
                family_name=c.family_name,
                method=c.method,
                confidence=c.confidence
            )
            for c in sorted_candidates
        ]
    finally:
        session.close()


def set_manual_name(file_hash: str, family_name: str, remove_family: bool = False) -> None:
    """Set a manual name entry. Clears selected_candidate_id."""
    session = get_session()
    try:
        card = session.query(Card).filter_by(file_hash=file_hash).first()
        if card:
            card.selected_family_name = family_name
            card.selected_candidate_id = None
            card.remove_family = remove_family
            card.updated_at = datetime.now(timezone.utc)
        else:
            card = Card(
                file_hash=file_hash,
                selected_family_name=family_name,
                remove_family=remove_family
            )
            session.add(card)
        session.commit()
    finally:
        session.close()


def select_candidate(file_hash: str, candidate_id: int, remove_family: bool = False) -> None:
    """Select a candidate from the dropdown. Clears selected_family_name."""
    session = get_session()
    try:
        card = session.query(Card).filter_by(file_hash=file_hash).first()
        if card:
            card.selected_candidate_id = candidate_id
            card.selected_family_name = None
            card.remove_family = remove_family
            card.updated_at = datetime.now(timezone.utc)
        else:
            card = Card(
                file_hash=file_hash,
                selected_candidate_id=candidate_id,
                remove_family=remove_family
            )
            session.add(card)
        session.commit()
    finally:
        session.close()


def update_remove_family(file_hash: str, remove_family: bool) -> None:
    """Update just the remove_family flag for a card."""
    session = get_session()
    try:
        card = session.query(Card).filter_by(file_hash=file_hash).first()
        if card:
            card.remove_family = remove_family
            card.updated_at = datetime.now(timezone.utc)
            session.commit()
    finally:
        session.close()


def get_card_state(file_hash: str) -> CardState | None:
    """Get complete card state for display."""
    session = get_session()
    try:
        card = session.query(Card).filter_by(file_hash=file_hash).first()
        if not card:
            return None

        # Get all candidates
        candidates = get_candidates(file_hash)

        # Determine display name, method, and confidence
        if card.selected_family_name:
            # Manual entry
            display_name = card.selected_family_name
            method = "manual"
            confidence = "manual"
        elif card.selected_candidate_id:
            # Selected candidate
            candidate = session.query(Candidate).filter_by(id=card.selected_candidate_id).first()
            if candidate:
                display_name = candidate.family_name
                method = candidate.method
                confidence = candidate.confidence
            else:
                # Candidate was deleted somehow
                display_name = ""
                method = "missing"
                confidence = "none"
        else:
            # No selection - missing
            display_name = ""
            method = "missing"
            confidence = "none"

        return CardState(
            display_name=display_name,
            method=method,
            confidence=confidence,
            candidates=candidates,
            remove_family=card.remove_family,
            selected_candidate_id=card.selected_candidate_id
        )
    finally:
        session.close()


def save_raw_ocr(file_hash: str, ocr_text: str) -> None:
    """Save raw OCR text for potential re-processing."""
    session = get_session()
    try:
        # Ensure card exists
        card = session.query(Card).filter_by(file_hash=file_hash).first()
        if not card:
            card = Card(file_hash=file_hash)
            session.add(card)
            session.flush()

        # Save or update OCR result
        ocr_result = session.query(RawOCRResult).filter_by(file_hash=file_hash).first()
        if ocr_result:
            ocr_result.ocr_text = ocr_text
            ocr_result.created_at = datetime.now(timezone.utc)
        else:
            ocr_result = RawOCRResult(file_hash=file_hash, ocr_text=ocr_text)
            session.add(ocr_result)
        session.commit()
    finally:
        session.close()


def get_raw_ocr(file_hash: str) -> str | None:
    """Get raw OCR text for re-processing."""
    session = get_session()
    try:
        ocr_result = session.query(RawOCRResult).filter_by(file_hash=file_hash).first()
        return ocr_result.ocr_text if ocr_result else None
    finally:
        session.close()


def save_raw_ai(file_hash: str, best_name: str, alternates: list[str]) -> None:
    """Save raw AI result for debugging and potential re-processing."""
    session = get_session()
    try:
        # Ensure card exists
        card = session.query(Card).filter_by(file_hash=file_hash).first()
        if not card:
            card = Card(file_hash=file_hash)
            session.add(card)
            session.flush()

        # Save raw AI response as JSON
        raw_data = json.dumps({"best_name": best_name, "alternates": alternates})
        ai_result = session.query(RawAIResult).filter_by(file_hash=file_hash).first()
        if ai_result:
            ai_result.raw_response = raw_data
            ai_result.created_at = datetime.now(timezone.utc)
        else:
            ai_result = RawAIResult(file_hash=file_hash, raw_response=raw_data)
            session.add(ai_result)
        session.commit()
    finally:
        session.close()


def get_raw_ai(file_hash: str) -> tuple[str, list[str]] | None:
    """Get raw AI result for re-processing.

    Returns (best_name, alternates) or None.
    """
    session = get_session()
    try:
        ai_result = session.query(RawAIResult).filter_by(file_hash=file_hash).first()
        if ai_result:
            data = json.loads(ai_result.raw_response)
            return data.get("best_name", ""), data.get("alternates", [])
        return None
    finally:
        session.close()


def clear_unselected_candidates(file_hash: str, method: str) -> None:
    """Clear candidates of a specific method (ocr/ai) except the selected one.

    Used when re-processing to ensure new extraction logic is applied while
    preserving user's selection.
    """
    session = get_session()
    try:
        card = session.query(Card).filter_by(file_hash=file_hash).first()
        if not card:
            return

        # Get selected candidate ID (if any)
        selected_id = card.selected_candidate_id

        # Delete all candidates of this method except the selected one
        query = session.query(Candidate).filter_by(file_hash=file_hash, method=method)
        if selected_id:
            # Only delete if the selected candidate is of a different method
            selected = session.query(Candidate).filter_by(id=selected_id).first()
            if selected and selected.method != method:
                # Safe to delete all of this method
                query.delete()
            else:
                # Selected candidate is of this method, preserve it
                query = query.filter(Candidate.id != selected_id)
                query.delete()
        else:
            # No selection, safe to delete all
            query.delete()

        session.commit()
    finally:
        session.close()


def should_reprocess(file_hash: str, method: str) -> bool:
    """Check if we should re-run OCR/AI for this file.

    Returns True if no candidates of this method exist.
    """
    session = get_session()
    try:
        count = session.query(Candidate).filter_by(file_hash=file_hash, method=method).count()
        return count == 0
    finally:
        session.close()


def reprocess_candidates_from_raw(file_hash: str) -> None:
    """Reprocess candidates from raw OCR and AI data.

    - Clears all existing candidates (except if manual entry is selected)
    - Re-parses raw_ocr and raw_ai with current cleaning logic
    - Auto-selects best candidate (prioritizes AI high > OCR high)
    - Preserves manual entries (selected_family_name)
    """
    from app.core.name_extractor import extract_family_names

    session = get_session()
    try:
        card = session.query(Card).filter_by(file_hash=file_hash).first()
        if not card:
            return

        # If manual entry exists, keep it but still update candidates
        is_manual = bool(card.selected_family_name)

        # Clear all existing candidates
        session.query(Candidate).filter_by(file_hash=file_hash).delete()
        session.commit()

        # Re-parse raw OCR if exists
        ocr_result = session.query(RawOCRResult).filter_by(file_hash=file_hash).first()
        if ocr_result:
            names = extract_family_names(ocr_result.ocr_text)
            for match in names:
                add_candidate(file_hash, match.name, "ocr", match.confidence.value)

        # Re-parse raw AI if exists
        ai_result = session.query(RawAIResult).filter_by(file_hash=file_hash).first()
        if ai_result:
            data = json.loads(ai_result.raw_response)
            best_name = data.get("best_name", "")
            alternates = data.get("alternates", [])

            if best_name:
                add_candidate(file_hash, best_name, "ai", "high")
            for alt_name in alternates:
                add_candidate(file_hash, alt_name, "ai", "high")

        # Auto-select best candidate if not manual entry
        if not is_manual:
            candidates = get_candidates(file_hash)
            if candidates:
                # First candidate is best (AI high priority due to sorting)
                best_id = candidates[0].id
                select_candidate(file_hash, best_id)

    finally:
        session.close()
