"""PR-D 이후: _ensure_local_schema 는 no-op (워커 SQLite 사용 안 함).

호환성만 유지 — WorkerCommand "ensure_schema" 호출 가능.
"""
from __future__ import annotations

import pytest


def test_ensure_local_schema_is_noop_after_pr_d(capsys):
    """_ensure_local_schema 가 no-op 으로 변경됨 (PR-D — 워커 SQLite 폐기)."""
    from worker.app import _ensure_local_schema
    _ensure_local_schema()
    captured = capsys.readouterr()
    assert "PR-D" in captured.out
    assert "no-op" in captured.out


def test_worker_app_main_does_not_call_ensure_schema():
    """main() 에 _ensure_local_schema() 호출 없음 (PR-D 이후 불필요)."""
    with open("worker/app.py") as f:
        src = f.read()
    # main() 본문 추출
    main_idx = src.find("def main():")
    next_def = src.find("\ndef ", main_idx + 1)
    main_src = src[main_idx:next_def if next_def != -1 else len(src)]
    # _ensure_local_schema() 호출 없음 (주석 제외)
    code_lines = [l for l in main_src.split("\n") if not l.strip().startswith("#")]
    code = "\n".join(code_lines)
    assert "_ensure_local_schema()" not in code, "main() 이 _ensure_local_schema 호출 — PR-D 위반"
