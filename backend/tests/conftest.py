"""Shared fixtures: a migrated `bist_test` database and a rolled-back session per test."""

import argparse
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import get_settings

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.cmd_opts = argparse.Namespace(x=["test=true"])  # read by alembic/env.py
    command.upgrade(cfg, "head")

    engine = create_engine(get_settings().database_url(test=True))
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine: Engine) -> Iterator[Session]:
    """Session bound to an outer transaction that is rolled back after the test.

    Code under test may call `session.commit()`; it only releases a savepoint.
    """
    with db_engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()
