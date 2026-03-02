"""Shared pytest fixtures for all tests."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.core.database as db_mod
from app.core.database import Base, Settings, _compute_schema_version


def pytest_addoption(parser):
    parser.addoption("--run-integration", action="store_true", default=False, help="Run integration tests")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-integration"):
        return
    skip_integration = pytest.mark.skip(reason="Need --run-integration to run")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)


@pytest.fixture
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

    # Clean up
    engine.dispose()

    # Restore
    db_mod._engine = orig_engine
    db_mod._Session = orig_session
