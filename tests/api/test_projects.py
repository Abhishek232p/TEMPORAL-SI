import pytest
from fastapi.testclient import TestClient
from applications.api.main import app
from packages.core.db.models import User, Organization, Membership, Project, Base
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
def auth_user(db):
    user = User(id=uuid.uuid4(), email=f"user-{uuid.uuid4()}@example.com", password_hash="hash", status="ACTIVE")
    org = Organization(id=uuid.uuid4(), name=f"Org {uuid.uuid4()}", slug=f"org-{uuid.uuid4().hex}")
    mem = Membership(id=uuid.uuid4(), user_id=user.id, organization_id=org.id, role="OWNER", status="ACTIVE")
    db.add_all([user, org, mem])
    db.commit()
    token = create_access_token({"sub": str(user.id)})
    return {"user": user, "org": org, "token": token}

@pytest.fixture
def cross_tenant_user(db):
    user = User(id=uuid.uuid4(), email=f"cross-{uuid.uuid4()}@example.com", password_hash="hash", status="ACTIVE")
    org = Organization(id=uuid.uuid4(), name=f"Other Org {uuid.uuid4()}", slug=f"other-{uuid.uuid4().hex}")
    mem = Membership(id=uuid.uuid4(), user_id=user.id, organization_id=org.id, role="OWNER", status="ACTIVE")
    db.add_all([user, org, mem])
    db.commit()
    token = create_access_token({"sub": str(user.id)})
    return {"user": user, "org": org, "token": token}

def test_create_project(auth_user):
    token = auth_user["token"]
    org_id = str(auth_user["org"].id)
    
    res = client.post(
        "/v1/projects",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id},
        json={"name": "Alpha", "slug": "alpha", "description": "First project"}
    )
    assert res.status_code == 201
    assert res.json()["name"] == "Alpha"
    assert res.json()["organization_id"] == org_id

def test_tenant_isolation(auth_user, cross_tenant_user, db):
    # Setup project in org 1
    token1 = auth_user["token"]
    org1_id = str(auth_user["org"].id)
    
    res1 = client.post(
        "/v1/projects",
        headers={"Authorization": f"Bearer {token1}", "X-Organization-ID": org1_id},
        json={"name": "Secret", "slug": "secret"}
    )
    proj_id = res1.json()["id"]
    
    # Try to access it from org 2 using user 2
    token2 = cross_tenant_user["token"]
    org2_id = str(cross_tenant_user["org"].id)
    
    # Attempt 1: Using their own org header, but fetching project 1
    res2 = client.get(
        f"/v1/projects/{proj_id}",
        headers={"Authorization": f"Bearer {token2}", "X-Organization-ID": org2_id}
    )
    # The database query explicitly enforces `Project.organization_id == auth.organization_id`
    assert res2.status_code == 404
    
    # Attempt 2: Using org 1 header to access project 1 (User 2 is not a member of org 1)
    res3 = client.get(
        f"/v1/projects/{proj_id}",
        headers={"Authorization": f"Bearer {token2}", "X-Organization-ID": org1_id}
    )
    assert res3.status_code == 403

def test_delete_project(auth_user):
    token = auth_user["token"]
    org_id = str(auth_user["org"].id)
    
    res = client.post(
        "/v1/projects",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id},
        json={"name": "Delete Me", "slug": "delete-me"}
    )
    proj_id = res.json()["id"]
    
    res2 = client.delete(
        f"/v1/projects/{proj_id}",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id}
    )
    assert res2.status_code == 204
    
    res3 = client.get(
        f"/v1/projects/{proj_id}",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id}
    )
    assert res3.status_code == 404
