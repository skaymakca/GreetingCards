"""Tests for app.core.database module."""
import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.core.database as db_mod
from app.core.database import (
    Base,
    Card,
    Candidate,
    Settings,
    RawOCRResult,
    RawAIResult,
    compute_file_hash,
    _compute_schema_version,
    _ensure_schema,
    _clean_and_filter_names,
    create_or_update_card,
    add_candidate,
    get_candidates,
    set_manual_name,
    select_candidate,
    update_remove_family,
    get_card_state,
    save_raw_ocr,
    get_raw_ocr,
    save_raw_ai,
    get_raw_ai,
    clear_unselected_candidates,
    reset_database,
    should_reprocess,
    reprocess_candidates_from_raw,
)


@pytest.fixture(autouse=True)
def in_memory_db():
    """Override database globals to use an in-memory SQLite database for each test."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    session_factory = sessionmaker(bind=engine)

    # Save originals
    orig_engine = db_mod._engine
    orig_session = db_mod._Session

    # Override module globals
    db_mod._engine = engine
    db_mod._Session = session_factory

    # Create schema
    Base.metadata.create_all(engine)
    session = session_factory()
    session.add(Settings(key="schema_version", value=_compute_schema_version()))
    session.commit()
    session.close()

    yield engine

    # Restore
    db_mod._engine = orig_engine
    db_mod._Session = orig_session


class TestSchemaVersion:
    """Tests for schema versioning."""

    def test_compute_schema_version_is_hex(self):
        version = _compute_schema_version()
        assert len(version) == 16
        int(version, 16)  # Should not raise

    def test_schema_version_deterministic(self):
        v1 = _compute_schema_version()
        v2 = _compute_schema_version()
        assert v1 == v2


class TestCreateOrUpdateCard:
    """Tests for create_or_update_card()."""

    def test_creates_card(self):
        create_or_update_card("hash1")
        state = get_card_state("hash1")
        assert state is not None
        assert state.display_name == ""
        assert state.method == "missing"

    def test_idempotent(self):
        create_or_update_card("hash1")
        create_or_update_card("hash1")  # Should not raise
        state = get_card_state("hash1")
        assert state is not None

    def test_remove_family_flag(self):
        create_or_update_card("hash1", remove_family=True)
        state = get_card_state("hash1")
        assert state.remove_family is True


class TestAddCandidate:
    """Tests for add_candidate()."""

    @patch("app.core.database._clean_and_filter_names", return_value=["Smith"])
    @patch("app.core.name_formatting.smart_title_case", side_effect=lambda x: x)
    def test_adds_candidate(self, mock_title, mock_clean):
        cid = add_candidate("hash1", "Smith", "ocr", "high")
        assert cid > 0
        candidates = get_candidates("hash1")
        assert len(candidates) == 1
        assert candidates[0].family_name == "Smith"

    @patch("app.core.database._clean_and_filter_names", return_value=["Smith"])
    @patch("app.core.name_formatting.smart_title_case", side_effect=lambda x: x)
    def test_dedup_same_name_method(self, mock_title, mock_clean):
        cid1 = add_candidate("hash1", "Smith", "ocr", "high")
        cid2 = add_candidate("hash1", "Smith", "ocr", "high")
        assert cid1 == cid2
        candidates = get_candidates("hash1")
        assert len(candidates) == 1

    @patch("app.core.database._clean_and_filter_names", return_value=[])
    def test_filtered_name_returns_zero(self, mock_clean):
        cid = add_candidate("hash1", "unknown", "ocr", "low")
        assert cid == 0

    @patch("app.core.database._clean_and_filter_names", return_value=["Smith"])
    @patch("app.core.name_formatting.smart_title_case", side_effect=lambda x: x)
    def test_auto_creates_card(self, mock_title, mock_clean):
        """Card is auto-created if it doesn't exist."""
        add_candidate("newhash", "Smith", "ai", "high")
        state = get_card_state("newhash")
        assert state is not None


class TestGetCandidates:
    """Tests for get_candidates()."""

    @patch("app.core.database._clean_and_filter_names", side_effect=lambda x: x)
    @patch("app.core.name_formatting.smart_title_case", side_effect=lambda x: x)
    def test_sorted_by_method_then_confidence(self, mock_title, mock_clean):
        create_or_update_card("hash1")
        add_candidate("hash1", "OcrLow", "ocr", "low")
        add_candidate("hash1", "AiHigh", "ai", "high")
        add_candidate("hash1", "OcrHigh", "ocr", "high")

        candidates = get_candidates("hash1")
        methods = [c.method for c in candidates]
        # AI should come before OCR
        assert methods.index("ai") < methods.index("ocr")

    def test_empty_for_nonexistent(self):
        assert get_candidates("nonexistent") == []


class TestSetManualName:
    """Tests for set_manual_name()."""

    def test_sets_manual_name(self):
        create_or_update_card("hash1")
        set_manual_name("hash1", "Johnson")
        state = get_card_state("hash1")
        assert state.display_name == "Johnson"
        assert state.method == "manual"
        assert state.confidence == "manual"

    def test_clears_candidate_id(self):
        create_or_update_card("hash1")
        set_manual_name("hash1", "Johnson")
        state = get_card_state("hash1")
        assert state.selected_candidate_id is None

    def test_creates_card_if_missing(self):
        set_manual_name("newhash", "Smith")
        state = get_card_state("newhash")
        assert state.display_name == "Smith"


class TestSelectCandidate:
    """Tests for select_candidate()."""

    @patch("app.core.database._clean_and_filter_names", return_value=["Smith"])
    @patch("app.core.name_formatting.smart_title_case", side_effect=lambda x: x)
    def test_selects_candidate(self, mock_title, mock_clean):
        create_or_update_card("hash1")
        cid = add_candidate("hash1", "Smith", "ocr", "high")
        select_candidate("hash1", cid)
        state = get_card_state("hash1")
        assert state.display_name == "Smith"
        assert state.selected_candidate_id == cid

    @patch("app.core.database._clean_and_filter_names", return_value=["Smith"])
    @patch("app.core.name_formatting.smart_title_case", side_effect=lambda x: x)
    def test_clears_manual_name(self, mock_title, mock_clean):
        create_or_update_card("hash1")
        set_manual_name("hash1", "Manual")
        cid = add_candidate("hash1", "Smith", "ocr", "high")
        select_candidate("hash1", cid)
        state = get_card_state("hash1")
        assert state.method != "manual"


class TestUpdateRemoveFamily:
    """Tests for update_remove_family()."""

    def test_updates_flag(self):
        create_or_update_card("hash1")
        update_remove_family("hash1", True)
        state = get_card_state("hash1")
        assert state.remove_family is True

    def test_no_error_for_nonexistent(self):
        """Silently does nothing for nonexistent card."""
        update_remove_family("nonexistent", True)


class TestGetCardState:
    """Tests for get_card_state()."""

    def test_nonexistent_returns_none(self):
        assert get_card_state("nonexistent") is None

    def test_missing_state(self):
        create_or_update_card("hash1")
        state = get_card_state("hash1")
        assert state.method == "missing"
        assert state.confidence == "none"
        assert state.display_name == ""

    def test_manual_state(self):
        create_or_update_card("hash1")
        set_manual_name("hash1", "Smith")
        state = get_card_state("hash1")
        assert state.method == "manual"
        assert state.confidence == "manual"
        assert state.display_name == "Smith"

    @patch("app.core.database._clean_and_filter_names", return_value=["Jones"])
    @patch("app.core.name_formatting.smart_title_case", side_effect=lambda x: x)
    def test_candidate_state(self, mock_title, mock_clean):
        create_or_update_card("hash1")
        cid = add_candidate("hash1", "Jones", "ai", "high")
        select_candidate("hash1", cid)
        state = get_card_state("hash1")
        assert state.method == "ai"
        assert state.confidence == "high"
        assert state.display_name == "Jones"


class TestRawOcr:
    """Tests for save_raw_ocr() and get_raw_ocr()."""

    def test_save_and_get(self):
        create_or_update_card("hash1")
        save_raw_ocr("hash1", "OCR text here")
        assert get_raw_ocr("hash1") == "OCR text here"

    def test_get_nonexistent(self):
        assert get_raw_ocr("nonexistent") is None

    def test_update_existing(self):
        create_or_update_card("hash1")
        save_raw_ocr("hash1", "first")
        save_raw_ocr("hash1", "second")
        assert get_raw_ocr("hash1") == "second"

    def test_auto_creates_card(self):
        save_raw_ocr("newhash", "text")
        assert get_raw_ocr("newhash") == "text"


class TestRawAi:
    """Tests for save_raw_ai() and get_raw_ai()."""

    def test_save_and_get(self):
        create_or_update_card("hash1")
        save_raw_ai("hash1", "Smith", ["Jones", "Williams"])
        result = get_raw_ai("hash1")
        assert result == ("Smith", ["Jones", "Williams"])

    def test_get_nonexistent(self):
        assert get_raw_ai("nonexistent") is None

    def test_update_existing(self):
        create_or_update_card("hash1")
        save_raw_ai("hash1", "First", [])
        save_raw_ai("hash1", "Second", ["Alt"])
        assert get_raw_ai("hash1") == ("Second", ["Alt"])

    def test_auto_creates_card(self):
        save_raw_ai("newhash", "Name", [])
        assert get_raw_ai("newhash") is not None


class TestClearUnselectedCandidates:
    """Tests for clear_unselected_candidates()."""

    @patch("app.core.database._clean_and_filter_names", side_effect=lambda x: x)
    @patch("app.core.name_formatting.smart_title_case", side_effect=lambda x: x)
    def test_clears_unselected(self, mock_title, mock_clean):
        create_or_update_card("hash1")
        add_candidate("hash1", "A", "ocr", "high")
        cid = add_candidate("hash1", "B", "ocr", "medium")
        select_candidate("hash1", cid)
        clear_unselected_candidates("hash1", "ocr")
        candidates = get_candidates("hash1")
        assert len(candidates) == 1
        assert candidates[0].family_name == "B"

    def test_no_error_nonexistent(self):
        clear_unselected_candidates("nonexistent", "ocr")


class TestShouldReprocess:
    """Tests for should_reprocess()."""

    def test_true_when_no_candidates(self):
        create_or_update_card("hash1")
        assert should_reprocess("hash1", "ocr") is True

    @patch("app.core.database._clean_and_filter_names", return_value=["Smith"])
    @patch("app.core.name_formatting.smart_title_case", side_effect=lambda x: x)
    def test_false_when_candidates_exist(self, mock_title, mock_clean):
        create_or_update_card("hash1")
        add_candidate("hash1", "Smith", "ocr", "high")
        assert should_reprocess("hash1", "ocr") is False

    @patch("app.core.database._clean_and_filter_names", return_value=["Smith"])
    @patch("app.core.name_formatting.smart_title_case", side_effect=lambda x: x)
    def test_method_specific(self, mock_title, mock_clean):
        create_or_update_card("hash1")
        add_candidate("hash1", "Smith", "ocr", "high")
        assert should_reprocess("hash1", "ai") is True


class TestReprocessCandidatesFromRaw:
    """Tests for reprocess_candidates_from_raw()."""

    @patch("app.core.database._clean_and_filter_names", side_effect=lambda x: x)
    @patch("app.core.name_formatting.smart_title_case", side_effect=lambda x: x)
    def test_reprocesses_ocr(self, mock_title, mock_clean):
        create_or_update_card("hash1")
        save_raw_ocr("hash1", "The Smith Family")
        reprocess_candidates_from_raw("hash1")
        candidates = get_candidates("hash1")
        assert len(candidates) > 0

    @patch("app.core.database._clean_and_filter_names", side_effect=lambda x: x)
    @patch("app.core.name_formatting.smart_title_case", side_effect=lambda x: x)
    def test_reprocesses_ai(self, mock_title, mock_clean):
        create_or_update_card("hash1")
        save_raw_ai("hash1", "Johnson", ["Williams"])
        reprocess_candidates_from_raw("hash1")
        candidates = get_candidates("hash1")
        names = [c.family_name for c in candidates]
        assert "Johnson" in names

    @patch("app.core.database._clean_and_filter_names", side_effect=lambda x: x)
    @patch("app.core.name_formatting.smart_title_case", side_effect=lambda x: x)
    def test_preserves_manual_entry(self, mock_title, mock_clean):
        create_or_update_card("hash1")
        set_manual_name("hash1", "Manual")
        save_raw_ocr("hash1", "The Smith Family")
        reprocess_candidates_from_raw("hash1")
        state = get_card_state("hash1")
        # Manual entry should be preserved
        assert state.display_name == "Manual"
        assert state.method == "manual"

    @patch("app.core.database._clean_and_filter_names", side_effect=lambda x: x)
    @patch("app.core.name_formatting.smart_title_case", side_effect=lambda x: x)
    def test_reprocesses_both_ocr_and_ai(self, mock_title, mock_clean):
        """When both OCR and AI raw data exist, both are processed as candidates."""
        create_or_update_card("hash1")
        save_raw_ocr("hash1", "The Smith Family")
        save_raw_ai("hash1", "Johnson", ["Williams"])
        reprocess_candidates_from_raw("hash1")
        candidates = get_candidates("hash1")
        names = [c.family_name for c in candidates]
        # AI primary should be present
        assert "Johnson" in names
        # OCR candidates should also be present
        assert len(candidates) >= 2

    def test_nonexistent_card_noop(self):
        reprocess_candidates_from_raw("nonexistent")  # Should not raise


class TestComputeFileHash:
    """Tests for compute_file_hash()."""

    def test_computes_sha256(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_bytes(b"hello world")
        result = compute_file_hash(f)
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert result == expected

    def test_different_content_different_hash(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_bytes(b"aaa")
        f2.write_bytes(b"bbb")
        assert compute_file_hash(f1) != compute_file_hash(f2)

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_bytes(b"")
        result = compute_file_hash(f)
        expected = hashlib.sha256(b"").hexdigest()
        assert result == expected


class TestCleanAndFilterNames:
    """Tests for _clean_and_filter_names()."""

    @patch("app.core.ai_analyzer.clean_family_name", side_effect=lambda x: x)
    @patch("app.core.name_formatting.deparameterize_name", side_effect=lambda x: x)
    @patch("app.core.name_formatting.sanitize_for_filename", side_effect=lambda x: x)
    def test_filters_unknown(self, mock_sanitize, mock_depar, mock_clean):
        result = _clean_and_filter_names(["unknown", "Smith"])
        assert "unknown" not in [r.lower() for r in result]
        assert "Smith" in result

    @patch("app.core.ai_analyzer.clean_family_name", side_effect=lambda x: x)
    @patch("app.core.name_formatting.deparameterize_name", side_effect=lambda x: x)
    @patch("app.core.name_formatting.sanitize_for_filename", side_effect=lambda x: x)
    def test_filters_empty(self, mock_sanitize, mock_depar, mock_clean):
        result = _clean_and_filter_names(["", "Smith"])
        assert len(result) == 1

    @patch("app.core.ai_analyzer.clean_family_name", side_effect=lambda x: x)
    @patch("app.core.name_formatting.deparameterize_name", side_effect=lambda x: x)
    @patch("app.core.name_formatting.sanitize_for_filename", side_effect=lambda x: x)
    def test_filters_snapfish(self, mock_sanitize, mock_depar, mock_clean):
        result = _clean_and_filter_names(["Snapfish"])
        assert len(result) == 0


class TestEnsureSchema:
    """Tests for _ensure_schema() — schema migration logic."""

    def test_schema_mismatch_recreates(self):
        """When schema version doesn't match, tables are dropped and recreated."""
        session = db_mod._Session()
        # Tamper with the stored schema version
        row = session.query(Settings).filter_by(key="schema_version").first()
        row.value = "badhash000000000"
        session.commit()
        session.close()

        # _ensure_schema should detect mismatch and recreate
        _ensure_schema()

        # Verify schema version is now correct
        session = db_mod._Session()
        row = session.query(Settings).filter_by(key="schema_version").first()
        assert row.value == _compute_schema_version()
        session.close()

    def test_missing_settings_table_recreates(self):
        """When settings table is missing, schema is created from scratch."""
        from sqlalchemy import text
        # Drop the settings table
        with db_mod._engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS settings"))

        _ensure_schema()

        # Verify schema was recreated
        session = db_mod._Session()
        row = session.query(Settings).filter_by(key="schema_version").first()
        assert row is not None
        assert row.value == _compute_schema_version()
        session.close()

    def test_orphaned_tables_dropped(self):
        """Orphaned tables not in current metadata are dropped during migration."""
        from sqlalchemy import text, inspect
        # Create an orphaned table
        with db_mod._engine.begin() as conn:
            conn.execute(text("CREATE TABLE orphan_table (id INTEGER PRIMARY KEY)"))

        # Tamper schema version to force migration
        session = db_mod._Session()
        row = session.query(Settings).filter_by(key="schema_version").first()
        row.value = "badhash000000000"
        session.commit()
        session.close()

        _ensure_schema()

        # Verify orphaned table was dropped
        inspector = inspect(db_mod._engine)
        assert "orphan_table" not in inspector.get_table_names()


class TestResetDatabase:
    """Tests for reset_database()."""

    def test_clears_all_data(self):
        """reset_database drops and recreates all tables."""
        # Add some data first
        create_or_update_card("hash1")
        set_manual_name("hash1", "Smith")
        assert get_card_state("hash1") is not None

        reset_database()

        # Data should be gone but tables should exist
        assert get_card_state("hash1") is None

    def test_schema_version_preserved(self):
        """After reset, schema version is set correctly."""
        reset_database()
        session = db_mod._Session()
        row = session.query(Settings).filter_by(key="schema_version").first()
        assert row is not None
        assert row.value == _compute_schema_version()
        session.close()

    def test_reset_when_engine_is_none(self):
        """reset_database creates engine if it doesn't exist."""
        orig_engine = db_mod._engine
        orig_session = db_mod._Session
        try:
            db_mod._engine = None
            db_mod._Session = None
            # Should not raise — creates engine internally
            reset_database()
        finally:
            db_mod._engine = orig_engine
            db_mod._Session = orig_session


class TestSelectCandidateNewCard:
    """Tests for select_candidate() when card doesn't exist yet."""

    @patch("app.core.database._clean_and_filter_names", return_value=["Smith"])
    @patch("app.core.name_formatting.smart_title_case", side_effect=lambda x: x)
    def test_creates_card_on_select(self, mock_title, mock_clean):
        """select_candidate creates a Card row if one doesn't exist."""
        # Add a candidate (auto-creates card)
        cid = add_candidate("newhash2", "Smith", "ocr", "high")
        # Delete the card but keep the candidate
        session = db_mod._Session()
        session.query(Card).filter_by(file_hash="newhash2").delete()
        session.commit()
        session.close()

        # select_candidate should create a new card
        select_candidate("newhash2", cid)
        state = get_card_state("newhash2")
        assert state is not None
        assert state.selected_candidate_id == cid


class TestGetCardStateDeletedCandidate:
    """Tests for get_card_state() when selected candidate was deleted."""

    @patch("app.core.database._clean_and_filter_names", return_value=["Smith"])
    @patch("app.core.name_formatting.smart_title_case", side_effect=lambda x: x)
    def test_missing_candidate_returns_missing(self, mock_title, mock_clean):
        """When selected candidate no longer exists, state shows missing."""
        create_or_update_card("hash1")
        cid = add_candidate("hash1", "Smith", "ocr", "high")
        select_candidate("hash1", cid)

        # Delete the candidate directly
        session = db_mod._Session()
        session.query(Candidate).filter_by(id=cid).delete()
        session.commit()
        session.close()

        state = get_card_state("hash1")
        assert state.display_name == ""
        assert state.method == "missing"
        assert state.confidence == "none"


class TestClearUnselectedCandidatesEdgeCases:
    """Tests for clear_unselected_candidates() edge cases."""

    @patch("app.core.database._clean_and_filter_names", side_effect=lambda x: x)
    @patch("app.core.name_formatting.smart_title_case", side_effect=lambda x: x)
    def test_selected_candidate_same_method_preserved(self, mock_title, mock_clean):
        """When selected candidate is of the same method being cleared, it's preserved."""
        create_or_update_card("hash1")
        cid1 = add_candidate("hash1", "A", "ocr", "high")
        cid2 = add_candidate("hash1", "B", "ocr", "medium")
        select_candidate("hash1", cid1)

        clear_unselected_candidates("hash1", "ocr")

        candidates = get_candidates("hash1")
        assert len(candidates) == 1
        assert candidates[0].id == cid1

    @patch("app.core.database._clean_and_filter_names", side_effect=lambda x: x)
    @patch("app.core.name_formatting.smart_title_case", side_effect=lambda x: x)
    def test_selected_candidate_different_method_deletes_all(self, mock_title, mock_clean):
        """When selected candidate is of a different method, all of target method are deleted."""
        create_or_update_card("hash1")
        ai_cid = add_candidate("hash1", "AI_Name", "ai", "high")
        add_candidate("hash1", "OCR_A", "ocr", "high")
        add_candidate("hash1", "OCR_B", "ocr", "medium")
        select_candidate("hash1", ai_cid)

        clear_unselected_candidates("hash1", "ocr")

        candidates = get_candidates("hash1")
        methods = [c.method for c in candidates]
        assert "ocr" not in methods
        assert "ai" in methods

    @patch("app.core.database._clean_and_filter_names", side_effect=lambda x: x)
    @patch("app.core.name_formatting.smart_title_case", side_effect=lambda x: x)
    def test_no_selection_deletes_all_of_method(self, mock_title, mock_clean):
        """When no candidate is selected, all candidates of the method are deleted."""
        create_or_update_card("hash1")
        add_candidate("hash1", "A", "ocr", "high")
        add_candidate("hash1", "B", "ocr", "medium")
        add_candidate("hash1", "C", "ai", "high")

        clear_unselected_candidates("hash1", "ocr")

        candidates = get_candidates("hash1")
        assert len(candidates) == 1
        assert candidates[0].method == "ai"
