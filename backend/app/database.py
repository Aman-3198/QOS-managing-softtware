"""SQLAlchemy 2.0 database setup (sync engine, SQLite).

The engine is configured lazily so tests can point at an in-memory/temp DB. A
SQLite ``check_same_thread=False`` is required because FastAPI runs sync
endpoints in a threadpool. The data directory is created on init.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _ensure_data_dir(url: str) -> None:
    # Only file-based sqlite needs a directory; in-memory ("sqlite://") does not.
    if url.startswith("sqlite:///") and url != "sqlite://":
        db_path = url.replace("sqlite:///", "", 1)
        parent = os.path.dirname(db_path) or "."
        Path(parent).mkdir(parents=True, exist_ok=True)


def configure_engine(url: str | None = None) -> Engine:
    """Create (or reuse) the engine. Idempotent. Exposed for tests."""
    global _engine, _SessionLocal
    if _engine is not None and url is None:
        return _engine
    db_url = url or settings.database_url
    _ensure_data_dir(db_url)
    _engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        echo=False,
        future=True,
    )
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        configure_engine()
    assert _engine is not None
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    if _SessionLocal is None:
        configure_engine()
    assert _SessionLocal is not None
    return _SessionLocal


def init_db(url: str | None = None) -> None:
    """Create all tables. Called from the app lifespan."""
    engine = configure_engine(url)
    # Import models so they register with Base.metadata before create_all.
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate(engine)


def _migrate(engine: Engine) -> None:
    """Lightweight forward-only migrations for the dev DB.

    Phase 5 added `qos_rule.paused`. create_all only creates missing tables, not
    columns, so add the column to an existing table if absent. (Phase 9 will
    replace this with a proper migration tool.)
    """
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if "qos_rule" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("qos_rule")}
        if "paused" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE qos_rule ADD COLUMN paused BOOLEAN DEFAULT 0"))


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional session context manager (commit on success, rollback on error)."""
    factory = get_session_factory()
    sess = factory()
    try:
        yield sess
        sess.commit()
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency: yield a session, close after the request."""
    factory = get_session_factory()
    sess = factory()
    try:
        yield sess
    finally:
        sess.close()
