import hashlib
import json
import logging
import threading
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Engine,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.core.paths import get_db_path
from app.models.card import CandidateConfidenceStr, CandidateInfo, CandidateMethodStr, CardState

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class Settings(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String)


class Card(Base):
    """Main card record. Tracks selected name (manual or from candidates) and preferences."""

    __tablename__ = "cards"
    file_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    selected_family_name: Mapped[str | None] = mapped_column(String)  # Manual entry only
    selected_candidate_id: Mapped[int | None] = mapped_column(
        ForeignKey("candidates.id", use_alter=True, name="fk_card_selected_candidate")
    )
    remove_family: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


class Candidate(Base):
    """Name candidates extracted via OCR or AI."""

    __tablename__ = "candidates"
    __table_args__ = (UniqueConstraint("file_hash", "family_name", "method", name="_file_name_method_uc"),)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    file_hash: Mapped[str] = mapped_column(String(64), ForeignKey("cards.file_hash"), index=True)
    family_name: Mapped[str] = mapped_column(String)
    method: Mapped[str] = mapped_column(String)  # 'ocr' | 'ai'
    confidence: Mapped[str] = mapped_column(String)  # 'high' | 'medium' | 'low'
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class RawOCRResult(Base):
    """Raw OCR text preserved for potential re-processing with improved extraction logic."""

    __tablename__ = "raw_ocr_results"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    file_hash: Mapped[str] = mapped_column(String(64), ForeignKey("cards.file_hash"), index=True, unique=True)
    ocr_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class RawAIResult(Base):
    """Raw AI response preserved for debugging and potential re-processing."""

    __tablename__ = "raw_ai_results"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    file_hash: Mapped[str] = mapped_column(String(64), ForeignKey("cards.file_hash"), index=True, unique=True)
    raw_response: Mapped[str] = mapped_column(Text)  # JSON: {"best_name": "...", "alternates": [...]}
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


# noinspection PyTypeChecker
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


_engine: Engine | None = None
_Session: sessionmaker[Session] | None = None
_init_lock = threading.Lock()


def _drop_tables(engine: Engine, table_names: set[str] | list[str]) -> None:
    """Drop the given tables from the database."""
    if table_names:
        # noinspection PyTypeChecker
        with engine.begin() as conn:
            for table_name in table_names:
                conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}"'))


def _get_engine() -> Engine:
    """Return the engine, raising if not yet initialized."""
    if _engine is None:
        raise RuntimeError("Database not initialized — call get_session() first")
    return _engine


def _get_session_factory() -> sessionmaker[Session]:
    """Return the session factory, raising if not yet initialized."""
    if _Session is None:
        raise RuntimeError("Database not initialized — call get_session() first")
    return _Session


def get_session() -> Session:
    global _engine, _Session
    with _init_lock:
        if _Session is None:
            _engine = create_engine(f"sqlite:///{get_db_path()}", echo=False)
            _Session = sessionmaker(bind=_engine)
            _ensure_schema()
    return _Session()


@contextmanager
def _session_scope() -> Generator[Session]:
    """Provide a transactional scope around a series of operations."""
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        logger.exception("Database operation failed, rolling back")
        session.rollback()
        raise
    finally:
        session.close()


def _parse_raw_ai_json(raw_response: str, file_hash: str) -> dict | None:
    """Parse raw AI JSON, returning None on decode error."""
    try:
        return json.loads(raw_response)
    except json.JSONDecodeError:
        logger.warning("Corrupt JSON in raw_ai_results for %s", file_hash)
        return None


# noinspection PyTypeChecker,GrazieInspection
def _ensure_schema() -> None:
    """Check schema version; if mismatch, drop all tables and recreate."""
    engine = _get_engine()
    session_factory = _get_session_factory()
    expected = _compute_schema_version()
    db_inspector = inspect(engine)

    if "settings" in db_inspector.get_table_names():
        session = session_factory()
        try:
            row = session.query(Settings).filter_by(key="schema_version").first()
            if row and row.value == expected:
                return  # schema is current
        finally:
            session.close()

    # Schema mismatch or missing — drop ALL tables including orphaned ones
    # First drop tables known to SQLAlchemy
    Base.metadata.drop_all(engine)

    # Then check for and drop any orphaned tables not in current metadata
    # Use fresh inspector since drop_all invalidated the cached one
    fresh_inspector = inspect(engine)
    all_tables = fresh_inspector.get_table_names()
    known_tables = {table.name for table in Base.metadata.tables.values()}
    orphaned = set(all_tables) - known_tables

    _drop_tables(engine, orphaned)

    # Create new schema
    Base.metadata.create_all(engine)

    session = session_factory()
    try:
        session.add(Settings(key="schema_version", value=expected))
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# noinspection PyTypeChecker
def reset_database() -> None:
    """Drop all tables and recreate from scratch."""
    global _engine, _Session
    with _init_lock:
        # Ensure engine exists
        if _engine is None:
            _engine = create_engine(f"sqlite:///{get_db_path()}", echo=False)
            _Session = sessionmaker(bind=_engine)

    engine = _get_engine()
    session_factory = _get_session_factory()

    # Drop all tables including orphaned ones
    db_inspector = inspect(engine)
    all_tables = db_inspector.get_table_names()
    _drop_tables(engine, all_tables)

    # Create new schema
    Base.metadata.create_all(engine)
    session = session_factory()
    try:
        session.add(Settings(key="schema_version", value=_compute_schema_version()))
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def clear_ai_results(file_hashes: list[str]) -> int:
    """Clear AI results for specific cards, preserving OCR and manual entries.

    Deletes raw_ai_results and AI candidates for the given hashes.
    For cards whose selected candidate was AI: re-selects best OCR candidate,
    or clears selection if none remain. Manual entries are untouched.

    Returns the number of cards whose selection changed.
    """
    if not file_hashes:
        return 0

    with _session_scope() as session:
        # Delete raw AI results for these hashes
        session.query(RawAIResult).filter(RawAIResult.file_hash.in_(file_hashes)).delete(synchronize_session="fetch")

        # Find cards whose selected candidate is an AI candidate (within scope)
        affected_cards = []
        for file_hash in file_hashes:
            card = session.query(Card).filter_by(file_hash=file_hash).first()
            if not card:
                continue
            if card.selected_candidate_id:
                selected = session.query(Candidate).filter_by(id=card.selected_candidate_id).first()
                if selected and selected.method == "ai":
                    affected_cards.append(card)

        # Null out selected_candidate_id BEFORE deleting candidates (prevents dangling FK)
        for card in affected_cards:
            card.selected_candidate_id = None
        session.flush()

        # Delete all AI candidates for these hashes
        session.query(Candidate).filter(Candidate.file_hash.in_(file_hashes), Candidate.method == "ai").delete(
            synchronize_session="fetch"
        )

        # Re-select best OCR candidate for affected cards
        changed = 0
        for card in affected_cards:
            # Skip if manual entry exists — manual wins
            if card.selected_family_name:
                continue

            # Find best remaining OCR candidate
            best_ocr = session.query(Candidate).filter_by(file_hash=card.file_hash, method="ocr").all()
            if best_ocr:
                best = min(best_ocr, key=lambda c: _CONFIDENCE_ORDER.get(c.confidence, 999))  # type: ignore[call-overload]  # Candidate.confidence is Mapped[str]
                card.selected_candidate_id = best.id
            else:
                card.selected_candidate_id = None
            changed += 1

        return changed


_HASH_CHUNK_SIZE = 8192


def compute_file_hash(path: Path) -> str:
    """Compute SHA256 hash of a file's contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_HASH_CHUNK_SIZE), b""):
            h.update(chunk)
    return h.hexdigest()


# --- Public API ---

# Sort order for candidates list
# Priority: AI results first, then OCR, sorted by confidence within each method
_METHOD_ORDER: dict[CandidateMethodStr, int] = {"ai": 0, "ocr": 1}
_CONFIDENCE_ORDER: dict[CandidateConfidenceStr, int] = {"high": 0, "medium": 1, "low": 2}


def _sort_candidates(candidates: list[Any]) -> list[CandidateInfo]:
    """Sort candidates by method (AI first) then confidence (high first), returning CandidateInfo list."""
    sorted_candidates = sorted(
        candidates, key=lambda c: (_METHOD_ORDER.get(c.method, 999), _CONFIDENCE_ORDER.get(c.confidence, 999))
    )
    return [
        CandidateInfo(id=c.id, family_name=c.family_name, method=c.method, confidence=c.confidence)
        for c in sorted_candidates
    ]


def _ensure_card_exists(session: Session, file_hash: str) -> Card:
    """Return the Card for file_hash, creating it if missing. Caller must flush/commit."""
    card = session.query(Card).filter_by(file_hash=file_hash).first()
    if not card:
        card = Card(file_hash=file_hash)
        session.add(card)
        session.flush()
    return card


def create_or_update_card(file_hash: str, remove_family: bool = False) -> None:
    """Create or update a card record. Call this when first processing a file."""
    with _session_scope() as session:
        card = session.query(Card).filter_by(file_hash=file_hash).first()
        if not card:
            card = Card(file_hash=file_hash, remove_family=remove_family)
            session.add(card)


# noinspection PyTypeChecker
def _insert_candidates(
    session: Session, file_hash: str, family_name: str, method: CandidateMethodStr, confidence: CandidateConfidenceStr
) -> int:
    """Insert candidates within an existing session. Returns first candidate ID, or 0 if filtered out.

    Applies cleaning/filtering and smart title case. When the cleaning pipeline returns multiple
    names (e.g. a recognized alternate form plus its related forms), all are added as separate candidates.
    """
    from app.core.naming.family_name import clean_and_filter_family_names, smart_title_case_family_name

    cleaned = clean_and_filter_family_names([family_name])
    if not cleaned:
        return 0

    first_id = 0
    for name in cleaned:
        clean_name = smart_title_case_family_name(name)

        existing = (
            session.query(Candidate).filter_by(file_hash=file_hash, family_name=clean_name, method=method).first()
        )
        if existing:
            if not first_id:
                first_id = existing.id
            continue

        candidate = Candidate(file_hash=file_hash, family_name=clean_name, method=method, confidence=confidence)
        try:
            # Savepoint so a constraint violation only rolls back this insert,
            # not the entire session — post-rollback queries stay valid.
            with session.begin_nested():
                session.add(candidate)
                session.flush()
        except IntegrityError:
            existing = (
                session.query(Candidate).filter_by(file_hash=file_hash, family_name=clean_name, method=method).first()
            )
            if existing and not first_id:
                first_id = existing.id
            continue
        if not first_id:
            first_id = candidate.id

    return first_id


def _add_candidate_inline(
    session: Session, file_hash: str, family_name: str, method: CandidateMethodStr, confidence: CandidateConfidenceStr
) -> int:
    """Add a candidate within an existing session (no new session scope).

    Used by reprocess_candidates_from_raw() to keep everything in one transaction.
    Returns the first candidate ID, or 0 if all names are filtered out.
    """
    return _insert_candidates(session, file_hash, family_name, method, confidence)


def add_candidate(
    file_hash: str, family_name: str, method: CandidateMethodStr, confidence: CandidateConfidenceStr
) -> int:
    """Add a name candidate (OCR or AI result). Returns first candidate ID.

    Automatically creates card if it doesn't exist.
    Applies cleaning/filtering and smart title case to the name before storing.
    When the cleaning pipeline returns multiple names (e.g. a recognized alternate
    form plus its related forms), all are added as separate candidates.
    Returns 0 if all names are filtered out.
    """
    first_id = 0
    with _session_scope() as session:
        _ensure_card_exists(session, file_hash)
        first_id = _insert_candidates(session, file_hash, family_name, method, confidence)
    return first_id


def get_candidates(file_hash: str) -> list[CandidateInfo]:
    """Get all candidates for a file, sorted by method (AI first) then confidence.

    Priority: AI high > AI medium > AI low > OCR high > OCR medium > OCR low
    """
    with _session_scope() as session:
        candidates = session.query(Candidate).filter_by(file_hash=file_hash).all()
        return _sort_candidates(candidates)


# noinspection DuplicatedCode
def set_manual_name(file_hash: str, family_name: str, remove_family: bool = False) -> None:
    """Set a manual name entry. Clears selected_candidate_id."""
    with _session_scope() as session:
        card = session.query(Card).filter_by(file_hash=file_hash).first()
        if card:
            card.selected_family_name = family_name
            card.selected_candidate_id = None
            card.remove_family = remove_family
            card.updated_at = datetime.now(UTC)
        else:
            card = Card(file_hash=file_hash, selected_family_name=family_name, remove_family=remove_family)
            session.add(card)


# noinspection DuplicatedCode
def select_candidate(file_hash: str, candidate_id: int, remove_family: bool = False) -> None:
    """Select a candidate for the card. Clears selected_family_name."""
    with _session_scope() as session:
        card = session.query(Card).filter_by(file_hash=file_hash).first()
        if card:
            card.selected_candidate_id = candidate_id
            card.selected_family_name = None
            card.remove_family = remove_family
            card.updated_at = datetime.now(UTC)
        else:
            card = Card(file_hash=file_hash, selected_candidate_id=candidate_id, remove_family=remove_family)
            session.add(card)


def update_remove_family(file_hash: str, remove_family: bool) -> None:
    """Update just the remove_family flag for a card."""
    with _session_scope() as session:
        card = session.query(Card).filter_by(file_hash=file_hash).first()
        if card:
            card.remove_family = remove_family
            card.updated_at = datetime.now(UTC)


# noinspection PyTypeChecker
def get_card_state(file_hash: str) -> CardState | None:
    """Get complete card state as a read-only DTO.

    Returns the resolved display name, method, confidence, candidates,
    and preferences for a card identified by its content hash.
    """
    with _session_scope() as session:
        card = session.query(Card).filter_by(file_hash=file_hash).first()
        if not card:
            return None

        # Inline candidate query to avoid opening a nested session
        raw_candidates = session.query(Candidate).filter_by(file_hash=file_hash).all()
        candidates = _sort_candidates(raw_candidates)

        # Determine display name, method, and confidence
        match (card.selected_family_name, card.selected_candidate_id):
            case (str(name), _) if name:
                # Manual entry
                display_name = name
                method = "manual"
                confidence = "manual"
            case (_, int(cid)) if cid:
                # Selected candidate
                candidate = session.query(Candidate).filter_by(id=cid).first()
                if candidate:
                    display_name = candidate.family_name
                    method = candidate.method
                    confidence = candidate.confidence
                else:
                    display_name = ""
                    method = "missing"
                    confidence = "none"
            case _:
                # No selection
                display_name = ""
                method = "missing"
                confidence = "none"

        return CardState(
            display_name=display_name,
            method=method,  # type: ignore[arg-type]  # mypy can't narrow match/case branches
            confidence=confidence,  # type: ignore[arg-type]
            candidates=candidates,
            remove_family=card.remove_family,
            selected_candidate_id=card.selected_candidate_id,
        )


def save_raw_ocr(file_hash: str, ocr_text: str) -> None:
    """Save raw OCR text for potential re-processing."""
    with _session_scope() as session:
        _ensure_card_exists(session, file_hash)

        # Save or update OCR result
        ocr_result = session.query(RawOCRResult).filter_by(file_hash=file_hash).first()
        if ocr_result:
            ocr_result.ocr_text = ocr_text
        else:
            ocr_result = RawOCRResult(file_hash=file_hash, ocr_text=ocr_text)
            session.add(ocr_result)


def get_raw_ocr(file_hash: str) -> str | None:
    """Get raw OCR text for re-processing."""
    with _session_scope() as session:
        ocr_result = session.query(RawOCRResult).filter_by(file_hash=file_hash).first()
        return ocr_result.ocr_text if ocr_result else None


def save_raw_ai(file_hash: str, best_name: str, alternates: list[str]) -> None:
    """Save raw AI result for debugging and potential re-processing."""
    with _session_scope() as session:
        _ensure_card_exists(session, file_hash)

        # Save raw AI response as JSON
        raw_data = json.dumps({"best_name": best_name, "alternates": alternates})
        ai_result = session.query(RawAIResult).filter_by(file_hash=file_hash).first()
        if ai_result:
            ai_result.raw_response = raw_data
        else:
            ai_result = RawAIResult(file_hash=file_hash, raw_response=raw_data)
            session.add(ai_result)


# noinspection PyTypeChecker
def get_raw_ai(file_hash: str) -> tuple[str, list[str]] | None:
    """Get raw AI result for re-processing.

    Returns (best_name, alternates) or None.
    """
    with _session_scope() as session:
        ai_result = session.query(RawAIResult).filter_by(file_hash=file_hash).first()
        if ai_result:
            data = _parse_raw_ai_json(ai_result.raw_response, file_hash)
            if data is None:
                return None
            return data.get("best_name", ""), data.get("alternates", [])
        return None


def clear_unselected_candidates(file_hash: str, method: str) -> None:
    """Clear candidates of a specific method (ocr/AI) except the selected one.

    Used when re-processing to ensure new extraction logic is applied while
    preserving user's selection.
    """
    with _session_scope() as session:
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
                query.delete(synchronize_session="fetch")
            else:
                # Selected candidate is of this method, preserve it
                query = query.filter(Candidate.id != selected_id)
                query.delete(synchronize_session="fetch")
        else:
            # No selection, safe to delete all
            query.delete(synchronize_session="fetch")


def should_reprocess(file_hash: str, method: str) -> bool:
    """Check if we should re-run OCR/AI for this file.

    Returns True if no candidates of this method exist.
    """
    with _session_scope() as session:
        count = session.query(Candidate).filter_by(file_hash=file_hash, method=method).count()
        return not count


# noinspection PyTypeChecker,GrazieInspection
def reprocess_candidates_from_raw(file_hash: str) -> None:
    """Reprocess candidates from raw OCR and AI data.

    - Clears all existing candidates (except if manual entry is selected)
    - Re-parses raw_ocr and raw_ai with current cleaning logic
    - Auto-selects best candidate (prioritizes AI high > OCR high)
    - Preserves manual entries (selected_family_name)

    All work happens in a single transaction to prevent dangling FKs
    and inconsistent intermediate states.
    """
    from app.core.naming.extractor import extract_family_names

    with _session_scope() as session:
        card = session.query(Card).filter_by(file_hash=file_hash).first()
        if not card:
            return

        # If manual entry exists, keep it but still update candidates
        is_manual = bool(card.selected_family_name)

        # Clear selected_candidate_id BEFORE deleting candidates (prevents dangling FK)
        card.selected_candidate_id = None
        session.flush()

        # Clear all existing candidates
        session.query(Candidate).filter_by(file_hash=file_hash).delete()

        # Re-parse raw OCR if exists
        ocr_result = session.query(RawOCRResult).filter_by(file_hash=file_hash).first()
        if ocr_result:
            names = extract_family_names(ocr_result.ocr_text)
            for match in names:
                _add_candidate_inline(session, file_hash, match.name, "ocr", match.confidence.value)  # type: ignore[arg-type]  # Confidence.value is str

        # Re-parse raw AI if exists
        ai_result = session.query(RawAIResult).filter_by(file_hash=file_hash).first()
        if ai_result:
            data = _parse_raw_ai_json(ai_result.raw_response, file_hash)
            if data is None:
                data = {}
            best_name = data.get("best_name", "")
            alternates = data.get("alternates", [])

            if best_name:
                _add_candidate_inline(session, file_hash, best_name, "ai", "high")
            for alt_name in alternates:
                _add_candidate_inline(session, file_hash, alt_name, "ai", "medium")

        # Auto-select best candidate if not manual entry
        if not is_manual:
            raw_candidates = session.query(Candidate).filter_by(file_hash=file_hash).all()
            sorted_candidates = _sort_candidates(raw_candidates)
            if sorted_candidates:
                card.selected_candidate_id = sorted_candidates[0].id
