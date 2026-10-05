import pytest
from fastapi.testclient import TestClient
from applications.api.main import app
from packages.core.db.models import User, Organization, Membership, Project, Dataset, DatasetVersion, DataProfile, Base
from packages.core.auth.tokens import create_access_token
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import uuid
import os
import io

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

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()
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

def test_create_and_get_profile(setup_data, db):
    token = setup_data["token"]
    org_id = str(setup_data["org"].id)
    proj_id = str(setup_data["project"].id)
    client = TestClient(app)
    
    # Create dataset
    res = client.post(
        f"/v1/projects/{proj_id}/datasets",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id},
        json={"name": "Profile Data"}
    )
    dataset_id = res.json()["id"]
    
    # Upload CSV to create version
    csv_content = b"timestamp,series_id,value\n2026-01-01T00:00:00Z,s1,10.0\n2026-01-02T00:00:00Z,s1,20.0"
    file_payload = {"file": ("data.csv", io.BytesIO(csv_content), "text/csv")}
    
    res2 = client.post(
        f"/v1/projects/{proj_id}/datasets/{dataset_id}/versions",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id},
        files=file_payload
    )
    version_id = res2.json()["id"]
    
    # Create Profile
    res3 = client.post(
        f"/v1/projects/{proj_id}/datasets/{dataset_id}/versions/{version_id}/profile",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id}
    )
    assert res3.status_code == 201
    profile = res3.json()
    assert profile["row_count"] == 2
    assert profile["column_count"] == 3
    assert "temporal_statistics" in profile["schema_summary"]
    
    # Get Profile
    res4 = client.get(
        f"/v1/projects/{proj_id}/datasets/{dataset_id}/versions/{version_id}/profile",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id}
    )
    assert res4.status_code == 200
    assert res4.json()["id"] == profile["id"]
