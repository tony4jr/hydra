"""SQLite -> PostgreSQL 데이터 마이그레이션 스크립트.

사용법:
    python scripts/migrate_sqlite_to_pg.py \
        --sqlite sqlite:///data/hydra.db \
        --pg postgresql+psycopg2://hydra:hydra_secret@localhost:5432/hydra
"""
import argparse
from sqlalchemy import create_engine, MetaData, text
from sqlalchemy.orm import sessionmaker


def migrate(sqlite_url: str, pg_url: str):
    src_engine = create_engine(sqlite_url)
    dst_engine = create_engine(pg_url)
    meta = MetaData()
    meta.reflect(bind=src_engine)

    SrcSession = sessionmaker(bind=src_engine)
    DstSession = sessionmaker(bind=dst_engine)

    src = SrcSession()
    dst = DstSession()

    # 테이블 순서 (FK 의존성 고려 — 참조하는 테이블이 먼저)
    table_order = [
        "system_config",
        "brands",
        "keywords",
        "videos",
        "accounts",
        "recovery_emails",
        "persona_slots",
        "profile_pools",
        "presets",
        "campaigns",
        "campaign_steps",
        "like_boost_queue",
        "action_log",
        "ip_log",
        "weekly_goals",
        "error_log",
        "scraped_comments",
        "channel_profile_history",
        "workers",
        "tasks",
        "profile_locks",
    ]

    for table_name in table_order:
        if table_name not in meta.tables:
            print(f"  SKIP: {table_name} (not in source)")
            continue

        table = meta.tables[table_name]
        rows = src.execute(table.select()).fetchall()
        if not rows:
            print(f"  SKIP: {table_name} (empty)")
            continue

        columns = [c.name for c in table.columns]
        for row in rows:
            data = dict(zip(columns, row))
            dst.execute(table.insert().values(**data))

        dst.commit()
        print(f"  OK: {table_name} ({len(rows)} rows)")

    # PostgreSQL 시퀀스 리셋
    for table_name in table_order:
        if table_name in meta.tables:
            try:
                dst.execute(text(f"""
                    SELECT setval(
                        pg_get_serial_sequence('{table_name}', 'id'),
                        COALESCE((SELECT MAX(id) FROM {table_name}), 0) + 1,
                        false
                    )
                """))
            except Exception:
                pass
    dst.commit()

    src.close()
    dst.close()
    print("\nMigration complete!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migrate HYDRA data from SQLite to PostgreSQL"
    )
    parser.add_argument("--sqlite", required=True, help="SQLite connection URL")
    parser.add_argument("--pg", required=True, help="PostgreSQL connection URL")
    args = parser.parse_args()
    migrate(args.sqlite, args.pg)
