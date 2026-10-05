import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from applications.api.dependencies import get_auth_context
from packages.core.auth.context import AuthContext
from packages.core.auth.tokens import create_access_token
from packages.core.db.models import User, Organization, Membership, Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import uuid

# Setup test db
engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app = FastAPI()

# We need to override the get_db dependency in dependencies.py
import applications.api.dependencies as deps
app.dependency_overrides[deps.get_db] = override_get_db

@app.get("/protected")
def protected_route(auth: AuthContext = Depends(get_auth_context)):
    return {"user_id": str(auth.user_id), "org_id": str(auth.organization_id), "role": auth.role}

client = TestClient(app)

@pytest.fixture
def db():
    db = TestingSessionLocal()
    yield db
    db.close()

@pytest.fixture
def test_data(db):
    user = User(id=uuid.uuid4(), email=f"test-{uuid.uuid4()}@example.com", password_hash="hash", status="ACTIVE")
    org = Organization(id=uuid.uuid4(), name=f"Test Org {uuid.uuid4()}", slug=f"test-org-{uuid.uuid4().hex}")
    mem = Membership(id=uuid.uuid4(), user_id=user.id, organization_id=org.id, role="ADMIN", status="ACTIVE")
    
    db.add_all([user, org, mem])
    db.commit()
    
    return {"user": user, "org": org, "mem": mem}

def test_missing_token():
    response = client.get("/protected", headers={"X-Organization-ID": str(uuid.uuid4())})
    assert response.status_code == 401

def test_invalid_token():
    response = client.get("/protected", headers={"Authorization": "Bearer invalid", "X-Organization-ID": str(uuid.uuid4())})
    assert response.status_code == 401

def test_missing_org_header(test_data):
    token = create_access_token({"sub": str(test_data["user"].id)})
    response = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 422 # FastAPI missing header

def test_valid_auth(test_data):
    token = create_access_token({"sub": str(test_data["user"].id)})
    response = client.get("/protected", headers={
        "Authorization": f"Bearer {token}",
        "X-Organization-ID": str(test_data["org"].id)
    })
    assert response.status_code == 200
    assert response.json()["role"] == "ADMIN"

def test_inactive_user(db, test_data):
    test_data["user"].status = "INACTIVE"
    db.commit()
    
    token = create_access_token({"sub": str(test_data["user"].id)})
    response = client.get("/protected", headers={
        "Authorization": f"Bearer {token}",
        "X-Organization-ID": str(test_data["org"].id)
    })
    assert response.status_code == 401
    assert "Inactive user" in response.json()["detail"]

def test_wrong_organization(db, test_data):
    other_org_id = str(uuid.uuid4())
    token = create_access_token({"sub": str(test_data["user"].id)})
    response = client.get("/protected", headers={
        "Authorization": f"Bearer {token}",
        "X-Organization-ID": other_org_id
    })
    assert response.status_code == 403
    assert "User is not a member" in response.json()["detail"]

def test_inactive_membership(db, test_data):
    test_data["mem"].status = "INACTIVE"
    db.commit()
    
    token = create_access_token({"sub": str(test_data["user"].id)})
    response = client.get("/protected", headers={
        "Authorization": f"Bearer {token}",
        "X-Organization-ID": str(test_data["org"].id)
    })
    assert response.status_code == 403
    assert "Membership is inactive" in response.json()["detail"]

def test_malformed_token():
    response = client.get("/protected", headers={
        "Authorization": f"Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.malformed.token",
        "X-Organization-ID": str(uuid.uuid4())
    })
    assert response.status_code == 401
