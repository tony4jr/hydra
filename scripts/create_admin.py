#!/usr/bin/env python3
"""첫 관리자 계정을 DB 에 생성하는 CLI.

VPS 최초 세팅 직후 1회 실행용. users 테이블이 존재해야 함
(Alembic migration 004_add_users 적용 후 실행 가능).

usage: python scripts/create_admin.py <email> <password> [--role admin|operator]

예시:
    python scripts/create_admin.py admin@hydra.local 'StrongPass!2026'
    python scripts/create_admin.py ops@hydra.local 'Op!2026' --role operator

기존 이메일이면 안내만 하고 종료 (중복 생성 방지).
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

# 프로젝트 루트를 import path 에 추가 (scripts/ 에서 실행 시)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    parser = argparse.ArgumentParser(description="HYDRA 관리자 계정 생성")
    parser.add_argument("email", help="관리자 이메일")
    parser.add_argument("password", help="비밀번호 (평문 — bcrypt 해시해서 저장)")
    parser.add_argument("--role", choices=["admin", "operator"], default="admin",
                        help="역할 (기본: admin)")
    args = parser.parse_args()

    # DB / 해시 import 는 argparse 이후 — import 에러 시 사용법 먼저 보여주도록
    try:
        from hydra.db.session import SessionLocal
        from hydra.db.models import User
    except ImportError as e:
        print(f"ERROR: hydra modules import 실패: {e}", file=sys.stderr)
        print("프로젝트 루트에서 실행하거나 venv 활성화 확인.", file=sys.stderr)
        return 1

    try:
        from hydra.core.auth import hash_password
    except ImportError:
        print("ERROR: hydra.core.auth 미구현 (Task 15 완료 필요).", file=sys.stderr)
        return 2

    db = SessionLocal()
    try:
        existing = db.query(User).filter_by(email=args.email).first()
        if existing is not None:
            print(f"ℹ️  이미 존재: id={existing.id} email={existing.email} role={existing.role}")
            return 0

        user = User(
            email=args.email,
            password_hash=hash_password(args.password),
            role=args.role,
        )
        db.add(user)
        db.commit()
        print(f"✅ 생성됨: id={user.id} email={user.email} role={user.role}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
