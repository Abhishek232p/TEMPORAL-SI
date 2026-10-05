import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from packages.core.db.models import Base

@pytest.fixture(scope="session")
def engine():
    # Setup test DB
    engine = create_engine('sqlite:///:memory:', echo=False)
    # Enforce foreign keys in SQLite for the tests
    from sqlalchemy import event
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)

@pytest.fixture
def db_session(engine):
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.rollback()
    session.close()
