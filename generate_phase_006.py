import os

base_dir = r"C:\Users\abhis\.gemini\antigravity-ide\scratch\temporal-intelligence"

def write_file(path, content):
    full_path = os.path.join(base_dir, path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, 'w', encoding='utf-8') as f:
        f.write(content.lstrip())

# 1. Update Schemas
schemas_append = """
# Project schemas
class ProjectCreate(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None

class ProjectResponse(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    slug: str
    description: Optional[str] = None
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True
"""
with open(os.path.join(base_dir, "applications/api/schemas.py"), "a", encoding="utf-8") as f:
    f.write("\n" + schemas_append.lstrip())

# 2. Update Policies
policies_append = """
    @staticmethod
    def can_manage_projects(auth: AuthContext):
        if auth.role not in ['OWNER', 'ADMIN']:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requires OWNER or ADMIN role to manage projects")
"""
with open(os.path.join(base_dir, "packages/core/auth/policies.py"), "a", encoding="utf-8") as f:
    f.write(policies_append)

# 3. Project Router
project_router = """
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List

from packages.core.db.session import get_db
from applications.api.dependencies import get_auth_context
from packages.core.auth.context import AuthContext
from packages.core.db.models import Project, AuditLog
from applications.api.schemas import ProjectCreate, ProjectUpdate, ProjectResponse
from packages.core.auth.policies import Policy
import uuid

router = APIRouter(prefix="/v1/projects", tags=["projects"])

def log_audit(db, org_id, actor_id, action, resource_type, resource_id):
    audit = AuditLog(
        id=uuid.uuid4(),
        organization_id=org_id,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id
    )
    db.add(audit)

@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(project_in: ProjectCreate, auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    Policy.can_manage_projects(auth)
    
    # Enforce uniqueness within the organization
    existing = db.query(Project).filter(
        Project.organization_id == auth.organization_id,
        Project.slug == project_in.slug
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Project slug already exists in this organization")
        
    project = Project(
        id=uuid.uuid4(),
        organization_id=auth.organization_id,
        name=project_in.name,
        slug=project_in.slug,
        description=project_in.description,
        status="ACTIVE"
    )
    
    db.add(project)
    log_audit(db, auth.organization_id, auth.user_id, "CREATE", "PROJECT", project.id)
    db.commit()
    db.refresh(project)
    return project

@router.get("", response_model=List[ProjectResponse])
def list_projects(auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    Policy.can_view(auth)
    projects = db.query(Project).filter(Project.organization_id == auth.organization_id).all()
    return projects

@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: UUID, auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    Policy.can_view(auth)
    # Strict boundary: must belong to the requested organization
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.organization_id == auth.organization_id
    ).first()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    return project

@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(project_id: UUID, project_in: ProjectUpdate, auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    Policy.can_manage_projects(auth)
    
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.organization_id == auth.organization_id
    ).first()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    if project_in.name is not None:
        project.name = project_in.name
    if project_in.description is not None:
        project.description = project_in.description
    if project_in.status is not None:
        project.status = project_in.status
        
    log_audit(db, auth.organization_id, auth.user_id, "UPDATE", "PROJECT", project.id)
    db.commit()
    db.refresh(project)
    return project

@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: UUID, auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    Policy.can_manage_projects(auth)
    
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.organization_id == auth.organization_id
    ).first()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    db.delete(project)
    log_audit(db, auth.organization_id, auth.user_id, "DELETE", "PROJECT", project.id)
    db.commit()
    return None
"""
write_file("applications/api/routers/projects.py", project_router)

# 4. Update Main to include projects
main_api = """
from fastapi import FastAPI
from applications.api.routers import organizations, projects

app = FastAPI(title="Temporal Intelligence API", version="0.1.0")

app.include_router(organizations.router)
app.include_router(projects.router)

@app.get("/health")
def health():
    return {"status": "ok"}
"""
write_file("applications/api/main.py", main_api)

# 5. Write Tests for Projects
test_projects = """
import pytest
from fastapi.testclient import TestClient
from applications.api.main import app
from packages.core.db.session import Base
from packages.core.db.models import User, Organization, Membership, Project
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
"""
write_file("tests/api/test_projects.py", test_projects)

print("Phase 006 files generated.")
