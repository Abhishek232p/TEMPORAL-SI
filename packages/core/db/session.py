import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

_ROOT = Path(__file__).resolve().parents[2]  # repository root (/workspace layout)

# Get database URL from environment or use a serverless-safe fallback.
# On Vercel/Serverless the code directory is read-only, so we default to a
# writable location (/tmp) unless DATABASE_URL points elsewhere.
_default_db = f"sqlite:///{_ROOT / 'temporal_intelligence.db'}"
if not os.access(_ROOT, os.W_OK):
    _default_db = "sqlite:////tmp/temporal_intelligence.db"

DATABASE_URL = os.environ.get("DATABASE_URL", _default_db)

_is_sqlite = DATABASE_URL.startswith("sqlite")

_engine_kwargs = {"pool_pre_ping": True}
if _is_sqlite:
    _engine_kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}

engine = create_engine(DATABASE_URL, **_engine_kwargs)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable WAL + foreign keys on SQLite for concurrent production traffic."""
    if not _is_sqlite:
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
