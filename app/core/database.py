import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, inspect
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

DB_PATH = Path(__file__).resolve().parent.parent.parent / "GreetingCards.sqlite"


class Settings(Base):
    __tablename__ = "settings"
    key = Column(String, primary_key=True)
    value = Column(String)


class FileNameCache(Base):
    __tablename__ = "file_names"
    id = Column(Integer, primary_key=True, autoincrement=True)
    file_hash = Column(String(64), index=True, nullable=False)
    family_name = Column(String, nullable=False, default="")
    source = Column(String, nullable=False)  # "ocr", "ai", "manual"
    confidence = Column(String, nullable=False, default="none")  # high/medium/low/manual/none
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class AIResultCache(Base):
    __tablename__ = "ai_results"
    id = Column(Integer, primary_key=True, autoincrement=True)
    file_hash = Column(String(64), index=True, unique=True, nullable=False)
    best_name = Column(String, nullable=False, default="")
    alternates = Column(Text, nullable=False, default="[]")  # JSON list
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


def _compute_schema_version() -> str:
    """Compute a hash representing the current model schema."""
    schema_parts = []
    for model in [Settings, FileNameCache, AIResultCache]:
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
        _engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
        _Session = sessionmaker(bind=_engine)
        _ensure_schema()
    return _Session()


def _ensure_schema():
    """Check schema version; if mismatch, drop all and recreate."""
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

    # Schema mismatch or missing — drop everything and recreate
    Base.metadata.drop_all(_engine)
    Base.metadata.create_all(_engine)

    session = _Session()
    try:
        session.add(Settings(key="schema_version", value=expected))
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


# --- Public API ---

def get_cached_name(file_hash: str) -> tuple[str, str, str] | None:
    """Get the most recent cached family name for a file hash.
    Returns (family_name, source, confidence) or None."""
    session = get_session()
    try:
        row = (session.query(FileNameCache)
               .filter_by(file_hash=file_hash)
               .order_by(FileNameCache.updated_at.desc())
               .first())
        if row:
            return row.family_name, row.source, row.confidence
        return None
    finally:
        session.close()


def save_name(file_hash: str, family_name: str, source: str, confidence: str = ""):
    """Save or update a family name for a file hash."""
    if not confidence:
        confidence = {"ocr": "medium", "ai": "high", "manual": "manual"}.get(source, "none")
    session = get_session()
    try:
        row = session.query(FileNameCache).filter_by(file_hash=file_hash).first()
        if row:
            row.family_name = family_name
            row.source = source
            row.confidence = confidence
            row.updated_at = datetime.now(timezone.utc)
        else:
            row = FileNameCache(
                file_hash=file_hash,
                family_name=family_name,
                source=source,
                confidence=confidence,
            )
            session.add(row)
        session.commit()
    finally:
        session.close()


def get_cached_ai_result(file_hash: str) -> tuple[str, list[str]] | None:
    """Get cached AI result for a file hash.
    Returns (best_name, alternates) or None."""
    session = get_session()
    try:
        row = session.query(AIResultCache).filter_by(file_hash=file_hash).first()
        if row:
            alternates = json.loads(row.alternates) if row.alternates else []
            return row.best_name, alternates
        return None
    finally:
        session.close()


def save_ai_result(file_hash: str, best_name: str, alternates: list[str]):
    """Save AI analysis result for a file hash."""
    session = get_session()
    try:
        row = session.query(AIResultCache).filter_by(file_hash=file_hash).first()
        if row:
            row.best_name = best_name
            row.alternates = json.dumps(alternates)
            row.created_at = datetime.now(timezone.utc)
        else:
            row = AIResultCache(
                file_hash=file_hash,
                best_name=best_name,
                alternates=json.dumps(alternates),
            )
            session.add(row)
        session.commit()
    finally:
        session.close()
