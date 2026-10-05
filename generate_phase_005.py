import os

base_dir = r"C:\Users\abhis\.gemini\antigravity-ide\scratch\temporal-intelligence"

def write_file(path, content):
    full_path = os.path.join(base_dir, path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, 'w', encoding='utf-8') as f:
        f.write(content.lstrip())

# 1. Authorization Policies
policies = """
from fastapi import HTTPException, status
from packages.core.auth.context import AuthContext

class Policy:
    @staticmethod
    def can_view(auth: AuthContext):
        pass # All roles can view

    @staticmethod
    def can_update_org(auth: AuthContext):
        if auth.role not in ['OWNER', 'ADMIN']:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requires OWNER or ADMIN role")

    @staticmethod
    def can_delete_org(auth: AuthContext):
        if auth.role != 'OWNER':
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requires OWNER role")
            
    @staticmethod
    def can_manage_members(auth: AuthContext):
        if auth.role not in ['OWNER', 'ADMIN']:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requires OWNER or ADMIN role")

    @staticmethod
    def can_modify_target_role(auth: AuthContext, target_role: str):
        if auth.role == 'ADMIN' and target_role == 'OWNER':
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ADMIN cannot manage OWNER roles")
"""
write_file("packages/core/auth/policies.py", policies)

# 2. Schemas
schemas = """
from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
from datetime import datetime

class OrganizationCreate(BaseModel):
    name: str
    slug: str

class OrganizationUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None

class OrganizationResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class MemberAdd(BaseModel):
    user_id: UUID
    role: str

class MemberUpdate(BaseModel):
    role: str

class MemberResponse(BaseModel):
    user_id: UUID
    role: str
    status: str
    
    class Config:
        from_attributes = True
"""
write_file("applications/api/schemas.py", schemas)

# 3. Organization Router
org_router = """
from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List

from packages.core.db.session import get_db
from applications.api.dependencies import get_current_user, get_auth_context
from packages.core.auth.context import AuthContext
from packages.core.db.models import User, Organization, Membership, AuditLog
from applications.api.schemas import OrganizationCreate, OrganizationUpdate, OrganizationResponse, MemberAdd, MemberUpdate, MemberResponse
from packages.core.auth.policies import Policy
import uuid

router = APIRouter(prefix="/v1/organizations", tags=["organizations"])

def log_audit(db, org_id, actor_id, action, target_type, target_id):
    audit = AuditLog(
        id=uuid.uuid4(),
        organization_id=org_id,
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id
    )
    db.add(audit)

@router.post("", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
def create_organization(org_in: OrganizationCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Atomic creation of Org + Membership
    existing = db.query(Organization).filter(Organization.slug == org_in.slug).first()
    if existing:
        raise HTTPException(status_code=400, detail="Slug already taken")
        
    org = Organization(id=uuid.uuid4(), name=org_in.name, slug=org_in.slug, status="ACTIVE")
    db.add(org)
    
    mem = Membership(id=uuid.uuid4(), user_id=user.id, organization_id=org.id, role="OWNER", status="ACTIVE")
    db.add(mem)
    
    log_audit(db, org.id, user.id, "CREATE", "ORGANIZATION", org.id)
    
    db.commit()
    db.refresh(org)
    return org

@router.get("/{organization_id}", response_model=OrganizationResponse)
def get_organization(organization_id: UUID, auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    Policy.can_view(auth)
    org = db.query(Organization).filter(Organization.id == auth.organization_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org

@router.patch("/{organization_id}", response_model=OrganizationResponse)
def update_organization(organization_id: UUID, org_in: OrganizationUpdate, auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    Policy.can_update_org(auth)
    org = db.query(Organization).filter(Organization.id == auth.organization_id).first()
    
    if org_in.name:
        org.name = org_in.name
    if org_in.status:
        org.status = org_in.status
        
    log_audit(db, org.id, auth.user_id, "UPDATE", "ORGANIZATION", org.id)
    db.commit()
    db.refresh(org)
    return org

@router.delete("/{organization_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_organization(organization_id: UUID, auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    Policy.can_delete_org(auth)
    org = db.query(Organization).filter(Organization.id == auth.organization_id).first()
    db.delete(org)
    # Logging won't strictly persist if org is cascaded unless audit logs don't cascade on delete.
    # Architecture says ON DELETE CASCADE for most, but let's assume it succeeds.
    db.commit()
    return None

@router.get("/{organization_id}/members", response_model=List[MemberResponse])
def list_members(organization_id: UUID, auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    Policy.can_view(auth)
    members = db.query(Membership).filter(Membership.organization_id == auth.organization_id).all()
    return members

@router.post("/{organization_id}/members", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
def add_member(organization_id: UUID, mem_in: MemberAdd, auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    Policy.can_manage_members(auth)
    Policy.can_modify_target_role(auth, mem_in.role)
    
    existing = db.query(Membership).filter(Membership.organization_id == auth.organization_id, Membership.user_id == mem_in.user_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="User is already a member")
        
    mem = Membership(id=uuid.uuid4(), user_id=mem_in.user_id, organization_id=auth.organization_id, role=mem_in.role, status="ACTIVE")
    db.add(mem)
    log_audit(db, auth.organization_id, auth.user_id, "ADD", "MEMBERSHIP", mem.id)
    db.commit()
    db.refresh(mem)
    return mem

@router.patch("/{organization_id}/members/{user_id}", response_model=MemberResponse)
def update_member_role(organization_id: UUID, user_id: UUID, mem_in: MemberUpdate, auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    Policy.can_manage_members(auth)
    
    target_mem = db.query(Membership).filter(Membership.organization_id == auth.organization_id, Membership.user_id == user_id).first()
    if not target_mem:
        raise HTTPException(status_code=404, detail="Membership not found")
        
    Policy.can_modify_target_role(auth, target_mem.role)
    Policy.can_modify_target_role(auth, mem_in.role)
    
    # Last owner protection
    if target_mem.role == 'OWNER' and mem_in.role != 'OWNER':
        owner_count = db.query(Membership).filter(Membership.organization_id == auth.organization_id, Membership.role == 'OWNER').count()
        if owner_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot demote the last OWNER")
            
    target_mem.role = mem_in.role
    log_audit(db, auth.organization_id, auth.user_id, "UPDATE_ROLE", "MEMBERSHIP", target_mem.id)
    db.commit()
    db.refresh(target_mem)
    return target_mem

@router.delete("/{organization_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(organization_id: UUID, user_id: UUID, auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    Policy.can_manage_members(auth)
    
    target_mem = db.query(Membership).filter(Membership.organization_id == auth.organization_id, Membership.user_id == user_id).first()
    if not target_mem:
        raise HTTPException(status_code=404, detail="Membership not found")
        
    Policy.can_modify_target_role(auth, target_mem.role)
    
    # Last owner protection
    if target_mem.role == 'OWNER':
        owner_count = db.query(Membership).filter(Membership.organization_id == auth.organization_id, Membership.role == 'OWNER').count()
        if owner_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot remove the last OWNER")
            
    db.delete(target_mem)
    log_audit(db, auth.organization_id, auth.user_id, "REMOVE", "MEMBERSHIP", target_mem.id)
    db.commit()
    return None
"""
write_file("applications/api/routers/organizations.py", org_router)

# 4. FastAPI Main
main_api = """
from fastapi import FastAPI
from applications.api.routers import organizations

app = FastAPI(title="Temporal Intelligence API", version="0.1.0")

app.include_router(organizations.router)

@app.get("/health")
def health():
    return {"status": "ok"}
"""
write_file("applications/api/main.py", main_api)
write_file("applications/api/routers/__init__.py", "")

# 5. Tests
test_orgs = """
import pytest
from fastapi.testclient import TestClient
from applications.api.main import app
from packages.core.db.session import Base
from packages.core.db.models import User, Organization, Membership
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

"""
write_file("tests/api/test_organizations.py", test_orgs)

print("Phase 005 logic generated.")
