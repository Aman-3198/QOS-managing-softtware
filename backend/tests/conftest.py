"""Pytest fixtures.

Tests run against an isolated temporary SQLite database so they never touch the
real ``data/smartqos.db``. The monitor background task runs under the
TestClient's lifespan; it publishes honest placeholder snapshots (Phase 2).
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # Isolate DB + log dir from the real project.
    from app.config import settings

    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setattr(settings, "log_dir", str(tmp_path / "logs"))

    # Keep tests fast/deterministic: point the connectivity probe at a closed
    # local port so DNS resolves instantly and TCP refuses instantly (=> "limited").
    # Real internet checks are verified live, not in the unit suite.
    monkeypatch.setattr(settings, "connectivity_host", "localhost")
    monkeypatch.setattr(settings, "connectivity_fallbacks", [])
    monkeypatch.setattr(settings, "connectivity_port", 1)
    monkeypatch.setattr(settings, "connectivity_timeout_s", 0.2)
    monkeypatch.setattr(settings, "connectivity_ttl_s", 1.0)

    # Reset the lazily-created engine so it reconfigures with the temp DB.
    import app.database as dbm
    dbm._engine = None
    dbm._SessionLocal = None

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def tmp_db_path(tmp_path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture()
def db_ready(tmp_path, monkeypatch):
    """Isolated, initialized DB for non-client tests (e.g. device service)."""
    from app.config import settings

    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setattr(settings, "log_dir", str(tmp_path / "logs"))
    import app.database as dbm
    dbm._engine = None
    dbm._SessionLocal = None
    from app.database import init_db
    init_db(f"sqlite:///{tmp_path / 'test.db'}")
    yield
