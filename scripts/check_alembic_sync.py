#!/usr/bin/env python3
"""Pre-commit: 모델 수정 시 alembic 마이그레이션 동봉 강제.

오늘 (2026-05-07) 같은 결함 3번 반복 방지:
- PR #66 sa.text('0') Postgres 비호환 (server_default)
- PR #67 백필 SQL 정수→Boolean 비호환
- PR #68 Brand.category 컬럼 마이그레이션 누락

근본 원인: 로컬 테스트(SQLite create_all) 통과해도 prod(Postgres alembic) 깨짐.

이 훅이 차단하는 것:
- hydra/db/models.py 의 Column/__tablename__ 같은 schema-bearing 라인 변경
- alembic/versions/*.py 신규 파일 staged 0개
- 커밋 메시지에 [skip-alembic-check] 없음
→ 차단

우회: 진짜 schema 변경 아닌 경우 (relationship 추가, 타입 hint 등)
- git commit -m "... [skip-alembic-check]"
"""
from __future__ import annotations

import re
import subprocess
import sys


SCHEMA_PATTERNS = [
    re.compile(r"^\+\s*[a-zA-Z_]+\s*=\s*Column\("),         # 새 컬럼
    re.compile(r"^\-\s*[a-zA-Z_]+\s*=\s*Column\("),         # 컬럼 제거
    re.compile(r"^\+\s*__tablename__\s*=\s*"),              # 새 테이블
    re.compile(r"^\+class\s+\w+\(Base\)"),                  # 새 모델 클래스
    re.compile(r"^\+\s*UniqueConstraint\("),                # 새 unique
    re.compile(r"^\+\s*Index\("),                           # 새 index
    re.compile(r"^\+\s*ForeignKey\("),                      # 새 FK (Column 안 있을 수도)
]


def run(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, text=True)


def staged_files() -> list[str]:
    out = run(["git", "diff", "--cached", "--name-only"])
    return [l.strip() for l in out.splitlines() if l.strip()]


def staged_diff(path: str) -> str:
    try:
        return run(["git", "diff", "--cached", "--", path])
    except subprocess.CalledProcessError:
        return ""


def commit_message() -> str:
    """현재 커밋 메시지 (pre-commit 훅 컨텍스트에서 .git/COMMIT_EDITMSG 또는 인자)."""
    # pre-commit 환경에선 메시지 파일 미정. 인자로 안 들어옴.
    # 우회 키워드는 별도 환경변수 ALLOW_SCHEMA_NO_MIGRATION=1 로도 OK.
    import os
    return os.environ.get("COMMIT_MSG_HINT", "")


def has_schema_change(diff: str) -> list[str]:
    """diff 에서 schema-bearing 라인 찾아 반환."""
    hits = []
    for line in diff.splitlines():
        for p in SCHEMA_PATTERNS:
            if p.match(line):
                hits.append(line[:120])
                break
    return hits


def main() -> int:
    files = staged_files()
    if not files:
        return 0

    models_changed = "hydra/db/models.py" in files
    new_alembic = [f for f in files if f.startswith("alembic/versions/") and f.endswith(".py")]

    # 우회 환경변수
    import os
    if os.environ.get("ALLOW_SCHEMA_NO_MIGRATION", "").strip() in ("1", "true", "yes"):
        return 0

    if not models_changed:
        return 0

    # models.py 가 변경됐을 때 schema-bearing 라인 있는지 검사
    diff = staged_diff("hydra/db/models.py")
    schema_lines = has_schema_change(diff)

    if not schema_lines:
        # relationship 추가 / docstring / type hint 등 → 통과
        return 0

    if new_alembic:
        # schema 변경 + alembic 새 파일 → 통과
        return 0

    # FAIL
    print("=" * 70, file=sys.stderr)
    print("❌ pre-commit: hydra/db/models.py schema 변경, alembic 마이그레이션 누락", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    print("", file=sys.stderr)
    print("감지된 schema 변경 라인:", file=sys.stderr)
    for line in schema_lines[:10]:
        print("  " + line, file=sys.stderr)
    print("", file=sys.stderr)
    print("권장 작업:", file=sys.stderr)
    print("  1. alembic revision -m 'desc' 으로 새 revision 생성", file=sys.stderr)
    print("  2. upgrade()/downgrade() 작성 (Postgres + SQLite 양쪽 호환)", file=sys.stderr)
    print("     - Boolean server_default: sa.true()/sa.false() 사용 (text X)", file=sys.stderr)
    print("     - 백필 SQL: true/false (1/0 X)", file=sys.stderr)
    print("  3. git add alembic/versions/<new>.py 후 다시 커밋", file=sys.stderr)
    print("", file=sys.stderr)
    print("우회 (정말 schema 변경 아님 — relationship, type hint 등):", file=sys.stderr)
    print("  ALLOW_SCHEMA_NO_MIGRATION=1 git commit ...", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
