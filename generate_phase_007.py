import os

base_dir = r"C:\Users\abhis\.gemini\antigravity-ide\scratch\temporal-intelligence"

def write_file(path, content):
    full_path = os.path.join(base_dir, path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, 'w', encoding='utf-8') as f:
        f.write(content.lstrip())

# 1. Update Schemas
schemas_append = """
# Dataset schemas
class DatasetCreate(BaseModel):
    name: str
    description: Optional[str] = None
    source_type: str = "FILE"

class DatasetResponse(BaseModel):
    id: UUID
    organization_id: UUID
    project_id: UUID
    name: str
    description: Optional[str] = None
    source_type: str
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class DatasetVersionResponse(BaseModel):
    id: UUID
    dataset_id: UUID
    organization_id: UUID
    version: int
    content_hash: str
    schema_hash: Optional[str] = None
    row_count: Optional[int] = None
    column_count: Optional[int] = None
    created_at: datetime
    created_by: UUID
    
    class Config:
        from_attributes = True
"""
with open(os.path.join(base_dir, "applications/api/schemas.py"), "a", encoding="utf-8") as f:
    f.write("\n" + schemas_append.lstrip())

# 2. Update Policies
policies_append = """
    @staticmethod
    def can_manage_datasets(auth: AuthContext):
        if auth.role not in ['OWNER', 'ADMIN']:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requires OWNER or ADMIN role to manage datasets")
"""
with open(os.path.join(base_dir, "packages/core/auth/policies.py"), "a", encoding="utf-8") as f:
    f.write(policies_append)

# 3. Storage Abstraction
storage_code = """
import os
import shutil
from pathlib import Path
from fastapi import UploadFile
import hashlib

class LocalDiskStorage:
    def __init__(self, base_path: str = ".storage"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        
    def save_artifact(self, org_id: str, project_id: str, dataset_id: str, version: int, file: UploadFile) -> str:
        # Immutable path
        path = self.base_path / str(org_id) / str(project_id) / str(dataset_id) / str(version)
        path.mkdir(parents=True, exist_ok=True)
        
        file_path = path / file.filename
        
        # Reset file pointer before reading
        file.file.seek(0)
        
        sha256_hash = hashlib.sha256()
        with open(file_path, "wb") as buffer:
            while chunk := file.file.read(8192):
                buffer.write(chunk)
                sha256_hash.update(chunk)
                
        # Reset again for downstream pandas parsing
        file.file.seek(0)
        
        return sha256_hash.hexdigest()
"""
write_file("packages/core/storage/local.py", storage_code)

# 4. Data Parser
parser_code = """
import pandas as pd
from fastapi import UploadFile
import json
import hashlib

def parse_dataset_metadata(file: UploadFile):
    filename = file.filename.lower()
    
    if filename.endswith(".csv"):
        df = pd.read_csv(file.file)
    elif filename.endswith(".parquet"):
        df = pd.read_parquet(file.file)
    else:
        raise ValueError("Unsupported file format. Must be CSV or Parquet.")
        
    row_count = len(df)
    column_count = len(df.columns)
    
    # Generate a schema hash based on column names and dtypes
    schema_dict = {col: str(dtype) for col, dtype in zip(df.columns, df.dtypes)}
    schema_str = json.dumps(schema_dict, sort_keys=True)
    schema_hash = hashlib.sha256(schema_str.encode()).hexdigest()
    
    # Reset file pointer again just in case
    file.file.seek(0)
    
    return {
        "row_count": row_count,
        "column_count": column_count,
        "schema_hash": schema_hash
    }
"""
write_file("packages/core/data/parser.py", parser_code)

# 5. Dataset Router
dataset_router = """
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List

from packages.core.db.session import get_db
from applications.api.dependencies import get_auth_context
from packages.core.auth.context import AuthContext
from packages.core.db.models import Project, Dataset, DatasetVersion, AuditLog
from applications.api.schemas import DatasetCreate, DatasetResponse, DatasetVersionResponse
from packages.core.auth.policies import Policy
from packages.core.storage.local import LocalDiskStorage
from packages.core.data.parser import parse_dataset_metadata
import uuid

router = APIRouter(prefix="/v1/projects/{project_id}/datasets", tags=["datasets"])
storage = LocalDiskStorage()

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

def verify_project_access(project_id: UUID, auth: AuthContext, db: Session):
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.organization_id == auth.organization_id
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

@router.post("", response_model=DatasetResponse, status_code=status.HTTP_201_CREATED)
def create_dataset(project_id: UUID, dataset_in: DatasetCreate, auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    Policy.can_manage_datasets(auth)
    verify_project_access(project_id, auth, db)
    
    dataset = Dataset(
        id=uuid.uuid4(),
        organization_id=auth.organization_id,
        project_id=project_id,
        name=dataset_in.name,
        description=dataset_in.description,
        source_type=dataset_in.source_type,
        status="ACTIVE"
    )
    db.add(dataset)
    log_audit(db, auth.organization_id, auth.user_id, "CREATE", "DATASET", dataset.id)
    db.commit()
    db.refresh(dataset)
    return dataset

@router.get("", response_model=List[DatasetResponse])
def list_datasets(project_id: UUID, auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    Policy.can_view(auth)
    verify_project_access(project_id, auth, db)
    
    datasets = db.query(Dataset).filter(Dataset.project_id == project_id).all()
    return datasets

@router.post("/{dataset_id}/versions", response_model=DatasetVersionResponse, status_code=status.HTTP_201_CREATED)
def upload_dataset_version(project_id: UUID, dataset_id: UUID, file: UploadFile = File(...), auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    Policy.can_manage_datasets(auth)
    verify_project_access(project_id, auth, db)
    
    dataset = db.query(Dataset).filter(
        Dataset.id == dataset_id,
        Dataset.project_id == project_id
    ).first()
    
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
        
    # Validation
    if not (file.filename.lower().endswith(".csv") or file.filename.lower().endswith(".parquet")):
        raise HTTPException(status_code=400, detail="Only CSV and Parquet files are supported")
        
    # Get latest version number
    latest_version = db.query(DatasetVersion).filter(DatasetVersion.dataset_id == dataset_id).order_by(DatasetVersion.version.desc()).first()
    next_version = (latest_version.version + 1) if latest_version else 1
    
    # Save raw artifact and hash
    try:
        content_hash = storage.save_artifact(str(auth.organization_id), str(project_id), str(dataset_id), next_version, file)
        metadata = parse_dataset_metadata(file)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to process file: {str(e)}")
        
    version_record = DatasetVersion(
        id=uuid.uuid4(),
        dataset_id=dataset.id,
        organization_id=auth.organization_id,
        version=next_version,
        content_hash=content_hash,
        schema_hash=metadata["schema_hash"],
        row_count=metadata["row_count"],
        column_count=metadata["column_count"],
        created_by=auth.user_id
    )
    
    db.add(version_record)
    log_audit(db, auth.organization_id, auth.user_id, "CREATE", "DATASET_VERSION", version_record.id)
    db.commit()
    db.refresh(version_record)
    return version_record

@router.get("/{dataset_id}/versions", response_model=List[DatasetVersionResponse])
def list_dataset_versions(project_id: UUID, dataset_id: UUID, auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    Policy.can_view(auth)
    verify_project_access(project_id, auth, db)
    
    # Verify dataset exists in project
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id, Dataset.project_id == project_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
        
    versions = db.query(DatasetVersion).filter(DatasetVersion.dataset_id == dataset_id).all()
    return versions
"""
write_file("applications/api/routers/datasets.py", dataset_router)

# 6. Update Main API
main_api = """
from fastapi import FastAPI
from applications.api.routers import organizations, projects, datasets

app = FastAPI(title="Temporal Intelligence API", version="0.1.0")

app.include_router(organizations.router)
app.include_router(projects.router)
app.include_router(datasets.router)

@app.get("/health")
def health():
    return {"status": "ok"}
"""
write_file("applications/api/main.py", main_api)

# 7. Write Tests for Datasets
test_datasets = """
import pytest
from fastapi.testclient import TestClient
from applications.api.main import app
from packages.core.db.session import Base
from packages.core.db.models import User, Organization, Membership, Project, Dataset, DatasetVersion
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
    csv_content = b"time,value\\n2026-01-01,10\\n2026-01-02,20"
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
"""
write_file("tests/api/test_datasets.py", test_datasets)

print("Phase 007 files generated.")
