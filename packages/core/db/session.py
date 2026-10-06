import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Get database URL from environment or use a safe fallback (which should not be prod).
# Serverless platforms (Vercel) have a read-only filesystem except for /tmp, so the
# SQLite fallback must not be written to the repo root there.
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    _default_db = "sqlite:////tmp/temporal_intelligence.db" if os.environ.get("VERCEL") else "sqlite:///temporal_intelligence.db"
    DATABASE_URL = _default_db

connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
