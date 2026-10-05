import os

base_dir = r"C:\Users\abhis\.gemini\antigravity-ide\scratch\temporal-intelligence"

def write_file(path, content):
    full_path = os.path.join(base_dir, path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, 'w', encoding='utf-8') as f:
        f.write(content.lstrip())

# 8. Schemas
schemas_append = """
from typing import Dict, Any, Optional

class DataSourceCreate(BaseModel):
    category: str
    metadata_: Dict[str, Any]

class DataSourceResponse(BaseModel):
    id: UUID
    organization_id: UUID
    dataset_id: UUID
    category: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class IngestionJobResponse(BaseModel):
    id: UUID
    dataset_id: UUID
    source_id: UUID
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    rows_ingested: Optional[int] = None
    dataset_version_id: Optional[UUID] = None
    created_at: datetime
    
    class Config:
        from_attributes = True
"""
with open(os.path.join(base_dir, "applications/api/schemas.py"), "a", encoding="utf-8") as f:
    f.write("\n" + schemas_append.lstrip())

# 9. API Routes for Datasets (append)
datasets_api_append = """
from packages.core.db.models import DataSource, IngestionJob
from applications.api.schemas import DataSourceCreate, DataSourceResponse, IngestionJobResponse

@router.post("/{dataset_id}/sources", response_model=DataSourceResponse, status_code=status.HTTP_201_CREATED)
def create_data_source(project_id: UUID, dataset_id: UUID, source_in: DataSourceCreate, auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    Policy.can_manage_datasets(auth)
    verify_project_access(project_id, auth, db)
    
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id, Dataset.project_id == project_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
        
    source = DataSource(
        id=uuid.uuid4(),
        organization_id=auth.organization_id,
        dataset_id=dataset.id,
        category=source_in.category,
        metadata_=source_in.metadata_
    )
    db.add(source)
    log_audit(db, auth.organization_id, auth.user_id, "CREATE", "DATA_SOURCE", source.id)
    db.commit()
    db.refresh(source)
    return source

@router.post("/{dataset_id}/ingestions", response_model=IngestionJobResponse, status_code=status.HTTP_201_CREATED)
def create_ingestion_job(project_id: UUID, dataset_id: UUID, source_id: UUID, auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    Policy.can_manage_datasets(auth)
    verify_project_access(project_id, auth, db)
    
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id, Dataset.project_id == project_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
        
    source = db.query(DataSource).filter(DataSource.id == source_id, DataSource.dataset_id == dataset_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
        
    # Prevent overlapping
    existing_job = db.query(IngestionJob).filter(IngestionJob.source_id == source_id, IngestionJob.status.in_(['PENDING', 'RUNNING'])).first()
    if existing_job:
        raise HTTPException(status_code=400, detail="An ingestion job is already running or pending for this source")
        
    job = IngestionJob(
        id=uuid.uuid4(),
        dataset_id=dataset.id,
        source_id=source.id,
        status='PENDING'
    )
    db.add(job)
    log_audit(db, auth.organization_id, auth.user_id, "CREATE", "INGESTION_JOB", job.id)
    db.commit()
    db.refresh(job)
    
    # We could trigger the scheduler immediately for local dev
    from packages.core.data.engine import IngestionEngine
    engine = IngestionEngine(db)
    # Using run_ingestion synchronously for testing, in real-world it's async
    import os
    if os.environ.get("SYNC_INGESTION") == "1":
        engine.run_ingestion(job.id)
        db.refresh(job)
        
    return job
"""
with open(os.path.join(base_dir, "applications/api/routers/datasets.py"), "a", encoding="utf-8") as f:
    f.write("\n" + datasets_api_append.lstrip())

# 10. Write Security & Connectors tests
test_connectors = """
import pytest
from packages.core.data.connectors.rest import RESTConnector, SecurityError
from packages.core.data.connectors.postgres import PostgreSQLConnector
import os

def test_rest_ssrf_protection():
    os.environ["ALLOW_LOCAL_REST"] = "0"
    connector = RESTConnector()
    
    # File scheme rejection
    with pytest.raises(SecurityError):
        connector.validate_config({"url": "file:///etc/passwd"})
        
    # Loopback rejection
    with pytest.raises(SecurityError):
        connector.validate_config({"url": "http://127.0.0.1:8000"})
        
    # Valid url
    assert connector.validate_config({"url": "https://api.weather.gov"}) == True

def test_postgres_readonly_protection():
    connector = PostgreSQLConnector()
    
    with pytest.raises(Exception, match="Unsafe operation detected: UPDATE "):
        connector.validate_config({
            "connection_string": "sqlite:///:memory:",
            "query": "UPDATE users SET active=1"
        })
        
    with pytest.raises(Exception, match="Unsafe operation detected: DROP "):
        connector.validate_config({
            "connection_string": "sqlite:///:memory:",
            "query": "DROP TABLE datasets"
        })
        
    assert connector.validate_config({
        "connection_string": "sqlite:///:memory:",
        "query": "SELECT * FROM data"
    }) == True
"""
write_file("tests/data/test_connectors.py", test_connectors)

print("Part 3 generation done.")
