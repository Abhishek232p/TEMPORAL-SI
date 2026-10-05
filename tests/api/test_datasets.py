import pytest
from fastapi.testclient import TestClient
from applications.api.main import app
from packages.core.db.models import User, Organization, Membership, Project, Dataset, DatasetVersion, Base
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

client = TestClient(app)

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

def test_create_dataset(setup_data):
    token = setup_data["token"]
    org_id = str(setup_data["org"].id)
    proj_id = str(setup_data["project"].id)
    
    res = client.post(
        f"/v1/projects/{proj_id}/datasets",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id},
        json={"name": "Sales Data", "source_type": "FILE"}
    )
    assert res.status_code == 201
    assert res.json()["name"] == "Sales Data"
    
def test_dataset_version_upload(setup_data):
    token = setup_data["token"]
    org_id = str(setup_data["org"].id)
    proj_id = str(setup_data["project"].id)
    
    # 1. Create dataset
    res = client.post(
        f"/v1/projects/{proj_id}/datasets",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id},
        json={"name": "Upload Data"}
    )
    dataset_id = res.json()["id"]
    
    # 2. Upload CSV
    csv_content = b"time,value\n2026-01-01,10\n2026-01-02,20"
    file_payload = {"file": ("data.csv", io.BytesIO(csv_content), "text/csv")}
    
    res2 = client.post(
        f"/v1/projects/{proj_id}/datasets/{dataset_id}/versions",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id},
        files=file_payload
    )
    assert res2.status_code == 201
    data = res2.json()
    assert data["version"] == 1
    assert data["row_count"] == 2
    assert data["column_count"] == 2
    assert data["content_hash"] is not None
    assert data["schema_hash"] is not None

def test_dataset_cross_tenant_isolation(setup_data, db):
    token = setup_data["token"]
    
    # Create org 2
    org2 = Organization(id=uuid.uuid4(), name=f"Other Org {uuid.uuid4()}", slug=f"other-{uuid.uuid4().hex}")
    proj2 = Project(id=uuid.uuid4(), organization_id=org2.id, name="Other Project", slug="other-proj")
    db.add_all([org2, proj2])
    db.commit()
    
    # User 1 attempts to create dataset in Project 2
    # Even if they try to pass org2_id, they don't have membership
    res = client.post(
        f"/v1/projects/{str(proj2.id)}/datasets",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": str(org2.id)},
        json={"name": "Hacked Data"}
    )
    # AuthContext middleware will reject it at membership check (403 or 422)
    assert res.status_code in [403, 401]
    
    # If they pass org1_id but project2's ID:
    res2 = client.post(
        f"/v1/projects/{str(proj2.id)}/datasets",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": str(setup_data["org"].id)},
        json={"name": "Hacked Data"}
    )
    # The endpoint validates verify_project_access(project_id, auth, db), which checks if project2 belongs to org1
    assert res2.status_code == 404
