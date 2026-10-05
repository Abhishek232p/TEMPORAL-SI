import os

base_dir = r"C:\Users\abhis\.gemini\antigravity-ide\scratch\temporal-intelligence"

def write_file(path, content):
    full_path = os.path.join(base_dir, path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, 'w', encoding='utf-8') as f:
        f.write(content.lstrip())

# 11. Ingestion Tests
test_ingestion = """
import pytest
from fastapi.testclient import TestClient
from applications.api.main import app
from packages.core.db.session import Base
from packages.core.db.models import User, Organization, Membership, Project, Dataset, DatasetVersion, DataSource, IngestionJob, IngestionCheckpoint, ProvenanceRecord
from packages.core.auth.tokens import create_access_token
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import uuid
import os

DB_URL = os.environ.get("DATABASE_URL", "sqlite:///:memory:")
if "sqlite" in DB_URL:
    engine = create_engine(DB_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
else:
    engine = create_engine(DB_URL)

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

from packages.core.db.session import get_db
app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def db():
    db = TestingSessionLocal()
    yield db
    db.close()

@pytest.fixture
def setup_data(db):
    user = User(id=uuid.uuid4(), email=f"user-{uuid.uuid4()}@example.com", password_hash="hash", status="ACTIVE")
    org = Organization(id=uuid.uuid4(), name=f"Org {uuid.uuid4()}", slug=f"org-{uuid.uuid4().hex}")
    mem = Membership(id=uuid.uuid4(), user_id=user.id, organization_id=org.id, role="OWNER", status="ACTIVE")
    project = Project(id=uuid.uuid4(), organization_id=org.id, name="Test Project", slug="test-proj")
    
    db.add_all([user, org, mem, project])
    db.commit()
    token = create_access_token({"sub": str(user.id)})
    return {"user": user, "org": org, "project": project, "token": token}

def test_rest_ingestion_idempotency_and_checkpoints(setup_data, db, monkeypatch):
    token = setup_data["token"]
    org_id = str(setup_data["org"].id)
    proj_id = str(setup_data["project"].id)
    
    # 1. Create dataset
    res = client.post(
        f"/v1/projects/{proj_id}/datasets",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id},
        json={"name": "Sales Data REST"}
    )
    dataset_id = res.json()["id"]
    
    # 2. Create Source
    res = client.post(
        f"/v1/projects/{proj_id}/datasets/{dataset_id}/sources",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id},
        json={
            "category": "REST",
            "metadata_": {
                "url": "http://mock-api",
                "method": "GET"
            }
        }
    )
    assert res.status_code == 201
    source_id = res.json()["id"]
    
    # Mock RESTConnector to avoid SSRF exception + network request
    from packages.core.data.connectors.rest import RESTConnector
    
    # First fetch mock
    fetch_call_count = 0
    def mock_fetch(self, config, checkpoint=None):
        nonlocal fetch_call_count
        fetch_call_count += 1
        return b"timestamp,series_id,value\\n2026-01-01T00:00:00Z,s1,10.0\\n2026-01-02T00:00:00Z,s1,20.0"
        
    monkeypatch.setattr(RESTConnector, "fetch", mock_fetch)
    monkeypatch.setattr(RESTConnector, "validate_config", lambda self, config: True)
    
    # Mock Sync Execution
    os.environ["SYNC_INGESTION"] = "1"
    
    # 3. Create Ingestion
    res = client.post(
        f"/v1/projects/{proj_id}/datasets/{dataset_id}/ingestions?source_id={source_id}",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id}
    )
    assert res.status_code == 201
    job = res.json()
    assert job["status"] == "SUCCEEDED"
    assert job["rows_ingested"] == 2
    
    # Verify DatasetVersion
    versions = client.get(
        f"/v1/projects/{proj_id}/datasets/{dataset_id}/versions",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id}
    ).json()
    assert len(versions) == 1
    v1_id = versions[0]["id"]
    
    # Verify Checkpoint
    chk = db.query(IngestionCheckpoint).filter(IngestionCheckpoint.source_id == uuid.UUID(source_id)).first()
    assert chk is not None
    assert chk.last_successful_timestamp is not None
    
    # 4. Trigger Idempotent Ingestion (identical data)
    res = client.post(
        f"/v1/projects/{proj_id}/datasets/{dataset_id}/ingestions?source_id={source_id}",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id}
    )
    assert res.status_code == 201
    job2 = res.json()
    assert job2["status"] == "SUCCEEDED"
    assert job2["rows_ingested"] == 0 # no new rows
    
    versions2 = client.get(
        f"/v1/projects/{proj_id}/datasets/{dataset_id}/versions",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id}
    ).json()
    assert len(versions2) == 1 # No duplicate version created
    
    # 5. Trigger new data fetch
    def mock_fetch_new(self, config, checkpoint=None):
        return b"timestamp,series_id,value\\n2026-01-03T00:00:00Z,s1,30.0"
        
    monkeypatch.setattr(RESTConnector, "fetch", mock_fetch_new)
    
    res = client.post(
        f"/v1/projects/{proj_id}/datasets/{dataset_id}/ingestions?source_id={source_id}",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id}
    )
    assert res.status_code == 201
    job3 = res.json()
    assert job3["status"] == "SUCCEEDED"
    assert job3["rows_ingested"] == 1
    
    versions3 = client.get(
        f"/v1/projects/{proj_id}/datasets/{dataset_id}/versions",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id}
    ).json()
    assert len(versions3) == 2 # New version created
"""
write_file("tests/api/test_ingestion.py", test_ingestion)

print("Part 4 generation done.")
