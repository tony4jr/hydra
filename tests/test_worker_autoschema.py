"""PR-AutoSchema: 워커 시작 시 SQLite schema 자동 생성 (alembic 의존성 제거).

scope:
- _ensure_local_schema 가 빈 DB 에서 core 테이블들 (accounts, workers, tasks, ip_logs 등) 생성
- 이미 schema 있어도 idempotent (checkfirst=True)
- DB 실패해도 워커 시작 안 막음 (try/except)
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest


def test_ensure_local_schema_creates_tables(tmp_path, monkeypatch):
    """빈 SQLite 에 _ensure_local_schema 호출 → core 테이블 생성."""
    db_path = tmp_path / "fresh.db"
    from sqlalchemy import create_engine, inspect
    from sqlalchemy.orm import sessionmaker
    from hydra.db import session as _ds

    engine = create_engine(f"sqlite:///{db_path}")
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr(_ds, "engine", engine)
    monkeypatch.setattr(_ds, "SessionLocal", Session)

    # 초기 상태: 테이블 없음
    insp_before = inspect(engine)
    assert "accounts" not in insp_before.get_table_names()

    from worker.app import _ensure_local_schema
    _ensure_local_schema()

    insp_after = inspect(engine)
    tables = set(insp_after.get_table_names())
    # 핵심 테이블들이 다 만들어짐
    expected_core = {"accounts", "workers", "tasks", "ip_log", "profile_locks", "worker_sessions"}
    missing = expected_core - tables
    assert not missing, f"missing tables: {missing}. got: {tables}"


def test_ensure_local_schema_idempotent(tmp_path, monkeypatch):
    """두 번 호출해도 안전 (checkfirst=True)."""
    db_path = tmp_path / "fresh.db"
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from hydra.db import session as _ds

    engine = create_engine(f"sqlite:///{db_path}")
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr(_ds, "engine", engine)
    monkeypatch.setattr(_ds, "SessionLocal", Session)

    from worker.app import _ensure_local_schema
    _ensure_local_schema()
    _ensure_local_schema()  # 두 번째 — 에러 없어야


def test_ensure_local_schema_swallows_db_error(monkeypatch, capsys):
    """DB engine 오류 시 워커 시작 막지 않음 (try/except)."""
    from worker.app import _ensure_local_schema

    def broken_create_all(*args, **kwargs):
        raise RuntimeError("simulated db failure")

    with patch("hydra.db.models.Base.metadata.create_all", side_effect=broken_create_all):
        _ensure_local_schema()  # 예외 없어야

    captured = capsys.readouterr()
    assert "WARNING" in captured.out
    assert "simulated db failure" in captured.out
