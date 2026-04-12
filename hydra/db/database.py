"""
HYDRA Database Connection + Session Management
"""

import os
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from hydra.db.models import Base


DATA_DIR = Path(__file__).parent.parent.parent / "data"
DB_PATH = DATA_DIR / "hydra.db"


def get_engine():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{DB_PATH}",
        echo=False,
        connect_args={"check_same_thread": False},
    )

    # SQLite WAL mode for concurrent reads
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def init_db():
    """Create all tables if they don't exist."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    print(f"✅ Database initialized: {DB_PATH}")
    return engine


def get_session() -> Session:
    engine = get_engine()
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


# Context manager for clean session handling
class db_session:
    def __enter__(self):
        self.session = get_session()
        return self.session

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.session.rollback()
        else:
            self.session.commit()
        self.session.close()
