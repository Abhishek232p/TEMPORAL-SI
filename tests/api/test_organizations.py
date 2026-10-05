import pytest
from fastapi.testclient import TestClient
from applications.api.main import app
from packages.core.db.models import User, Organization, Membership, Base
from packages.core.auth.tokens import create_access_token
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import uuid
import os

# Determine if we are testing against real Postgres
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
    user = User(id=uuid.uuid4(), email=f"auth-{uuid.uuid4()}@example.com", password_hash="hash", status="ACTIVE")
    db.add(user)
    db.commit()
    token = create_access_token({"sub": str(user.id)})
    return user, token
    
@pytest.fixture
def other_user(db):
    user = User(id=uuid.uuid4(), email=f"other-{uuid.uuid4()}@example.com", password_hash="hash", status="ACTIVE")
    db.add(user)
    db.commit()
    return user

def test_create_organization(auth_user):
    user, token = auth_user
    response = client.post(
        "/v1/organizations",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "New Org", "slug": "new-org"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "New Org"
    assert "id" in data
    
    org_id = data["id"]
    # Check that owner membership was created
    response2 = client.get(
        f"/v1/organizations/{org_id}/members",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id}
    )
    assert response2.status_code == 200
    members = response2.json()
    assert len(members) == 1
    assert members[0]["user_id"] == str(user.id)
    assert members[0]["role"] == "OWNER"

def test_add_member_as_owner(auth_user, other_user):
    user, token = auth_user
    # Create org
    res = client.post("/v1/organizations", headers={"Authorization": f"Bearer {token}"}, json={"name": "O", "slug": f"o-{uuid.uuid4().hex}"})
    org_id = res.json()["id"]
    
    # Add other user
    res2 = client.post(
        f"/v1/organizations/{org_id}/members",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id},
        json={"user_id": str(other_user.id), "role": "MEMBER"}
    )
    assert res2.status_code == 201
    assert res2.json()["role"] == "MEMBER"

def test_last_owner_protection(auth_user):
    user, token = auth_user
    res = client.post("/v1/organizations", headers={"Authorization": f"Bearer {token}"}, json={"name": "O", "slug": f"o-{uuid.uuid4().hex}"})
    org_id = res.json()["id"]
    
    # Try demoting self
    res2 = client.patch(
        f"/v1/organizations/{org_id}/members/{user.id}",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id},
        json={"role": "ADMIN"}
    )
    assert res2.status_code == 400
    assert "Cannot demote the last OWNER" in res2.json()["detail"]
    
    # Try deleting self
    res3 = client.delete(
        f"/v1/organizations/{org_id}/members/{user.id}",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id}
    )
    assert res3.status_code == 400
    assert "Cannot remove the last OWNER" in res3.json()["detail"]

def test_admin_cannot_demote_owner(db, auth_user, other_user):
    admin_user, admin_token = auth_user
    owner_user = other_user
    
    # Setup manually
    org = Organization(id=uuid.uuid4(), name="Org", slug=f"org-{uuid.uuid4().hex}")
    db.add(org)
    db.add(Membership(id=uuid.uuid4(), user_id=owner_user.id, organization_id=org.id, role="OWNER", status="ACTIVE"))
    db.add(Membership(id=uuid.uuid4(), user_id=admin_user.id, organization_id=org.id, role="ADMIN", status="ACTIVE"))
    db.commit()
    
    res = client.patch(
        f"/v1/organizations/{org.id}/members/{owner_user.id}",
        headers={"Authorization": f"Bearer {admin_token}", "X-Organization-ID": str(org.id)},
        json={"role": "MEMBER"}
    )
    assert res.status_code == 403
    assert "ADMIN cannot manage OWNER roles" in res.json()["detail"]

