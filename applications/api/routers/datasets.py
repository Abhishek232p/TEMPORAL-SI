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

from packages.core.db.models import DataProfile
from packages.core.data.profiler import DataProfiler
import json
import pandas as pd
import io

from typing import Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel
class DataProfileResponse(BaseModel):
    id: UUID
    dataset_version_id: UUID
    row_count: Optional[int] = None
    column_count: Optional[int] = None
    schema_summary: Optional[Dict[str, Any]] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

@router.post("/{dataset_id}/versions/{version_id}/profile", response_model=DataProfileResponse, status_code=status.HTTP_201_CREATED)
def create_dataset_profile(project_id: UUID, dataset_id: UUID, version_id: UUID, auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    Policy.can_manage_datasets(auth)
    verify_project_access(project_id, auth, db)
    
    version = db.query(DatasetVersion).filter(
        DatasetVersion.id == version_id,
        DatasetVersion.dataset_id == dataset_id
    ).first()
    
    if not version:
        raise HTTPException(status_code=404, detail="Dataset version not found")
        
    # Check if profile already exists
    existing = db.query(DataProfile).filter(DataProfile.dataset_version_id == version_id).first()
    if existing:
        return existing
        
    # Retrieve raw bytes via Storage (rebuilding path logically)
    # Using LocalDiskStorage abstraction
    from packages.core.storage.local import LocalDiskStorage
    storage = LocalDiskStorage()
    
    path = storage.base_path / str(auth.organization_id) / str(project_id) / str(dataset_id) / str(version.version) / "data.csv"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Artifact not found on storage")
        
    with open(path, "rb") as f:
        raw_bytes = f.read()
        
    df = pd.read_csv(io.BytesIO(raw_bytes))
    
    profiler = DataProfiler()
    profile_data = profiler.profile_dataframe(df)
    
    # Store profile
    profile = DataProfile(
        id=uuid.uuid4(),
        dataset_version_id=version.id,
        row_count=profile_data["general_statistics"]["row_count"],
        column_count=profile_data["general_statistics"]["column_count"],
        schema_summary=profile_data
    )
    db.add(profile)
    log_audit(db, auth.organization_id, auth.user_id, "CREATE", "DATA_PROFILE", profile.id)
    db.commit()
    db.refresh(profile)
    
    return profile

@router.get("/{dataset_id}/versions/{version_id}/profile", response_model=DataProfileResponse)
def get_dataset_profile(project_id: UUID, dataset_id: UUID, version_id: UUID, auth: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)):
    Policy.can_view(auth)
    verify_project_access(project_id, auth, db)
    
    version = db.query(DatasetVersion).filter(
        DatasetVersion.id == version_id,
        DatasetVersion.dataset_id == dataset_id
    ).first()
    if not version:
        raise HTTPException(status_code=404, detail="Dataset version not found")
        
    profile = db.query(DataProfile).filter(DataProfile.dataset_version_id == version_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
        
    return profile

# ---------------------------------------------------------------------------
# Phase 009 — Data Quality & Validation
# ---------------------------------------------------------------------------

from packages.core.db.models import DataQualityReport
from packages.core.quality.engine import ValidationEngine, ValidationConfig
from applications.api.schemas import QualityValidationRequest, QualityReportResponse


@router.post(
    "/{dataset_id}/versions/{version_id}/quality",
    response_model=QualityReportResponse,
    status_code=status.HTTP_201_CREATED,
)
def run_quality_validation(
    project_id: UUID,
    dataset_id: UUID,
    version_id: UUID,
    validation_request: Optional[QualityValidationRequest] = None,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """Run data quality validation against a specific DatasetVersion.

    Reads the immutable artifact, runs deterministic rules, and stores
    findings as a DataQualityReport. Never mutates the DatasetVersion.
    """
    Policy.can_manage_datasets(auth)
    verify_project_access(project_id, auth, db)

    version = db.query(DatasetVersion).filter(
        DatasetVersion.id == version_id,
        DatasetVersion.dataset_id == dataset_id,
    ).first()
    if not version:
        raise HTTPException(status_code=404, detail="Dataset version not found")

    # Load the immutable artifact
    local_storage = LocalDiskStorage()
    path = local_storage.base_path / str(auth.organization_id) / str(project_id) / str(dataset_id) / str(version.version) / "data.csv"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Artifact not found on storage")

    with open(path, "rb") as f:
        raw_bytes = f.read()
    df = pd.read_csv(io.BytesIO(raw_bytes))

    # Build validation config from request
    if validation_request:
        vr = validation_request
        val_config = ValidationConfig(
            required_columns=vr.required_columns,
            expected_dtypes=vr.expected_dtypes,
            max_null_fraction=vr.max_null_fraction,
            null_check_columns=vr.null_check_columns,
            max_duplicate_fraction=vr.max_duplicate_fraction,
            timestamp_column=vr.timestamp_column,
            series_column=vr.series_column,
            value_column=vr.value_column,
            gap_multiplier=vr.gap_multiplier,
            min_series_observations=vr.min_series_observations,
            value_bounds=vr.value_bounds,
        )
        config_dict = vr.model_dump()
    else:
        val_config = ValidationConfig()
        config_dict = {}

    # Run engine
    engine = ValidationEngine()
    report = engine.validate(df, config=val_config)

    # Persist
    dq_report = DataQualityReport(
        id=uuid.uuid4(),
        dataset_version_id=version.id,
        organization_id=auth.organization_id,
        verdict=report.verdict,
        total_findings=report.total_findings,
        critical_count=report.critical_count,
        error_count=report.error_count,
        warning_count=report.warning_count,
        info_count=report.info_count,
        findings=report.to_dict()["findings"],
        rule_config=config_dict,
    )
    db.add(dq_report)
    log_audit(db, auth.organization_id, auth.user_id, "CREATE", "DATA_QUALITY_REPORT", dq_report.id)
    db.commit()
    db.refresh(dq_report)

    return dq_report


@router.get(
    "/{dataset_id}/versions/{version_id}/quality",
    response_model=QualityReportResponse,
)
def get_quality_report(
    project_id: UUID,
    dataset_id: UUID,
    version_id: UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """Retrieve the latest quality report for a DatasetVersion."""
    Policy.can_view(auth)
    verify_project_access(project_id, auth, db)

    version = db.query(DatasetVersion).filter(
        DatasetVersion.id == version_id,
        DatasetVersion.dataset_id == dataset_id,
    ).first()
    if not version:
        raise HTTPException(status_code=404, detail="Dataset version not found")

    report = db.query(DataQualityReport).filter(
        DataQualityReport.dataset_version_id == version_id,
    ).order_by(DataQualityReport.created_at.desc()).first()

    if not report:
        raise HTTPException(status_code=404, detail="Quality report not found")

    return report

# ---------------------------------------------------------------------------
# Phase 010 — Temporal Causal Safety
# ---------------------------------------------------------------------------

from packages.core.db.models import CausalSafetyReportModel
from packages.core.causality.engine import CausalSafetyEngine, CausalSafetyConfig
from applications.api.schemas import CausalSafetyRequest, CausalSafetyReportResponse


@router.post(
    "/{dataset_id}/versions/{version_id}/causal-safety",
    response_model=CausalSafetyReportResponse,
    status_code=status.HTTP_201_CREATED,
)
def run_causal_safety_validation(
    project_id: UUID,
    dataset_id: UUID,
    version_id: UUID,
    safety_request: Optional[CausalSafetyRequest] = None,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """Run temporal causal safety validation against a specific DatasetVersion.

    Reads the immutable artifact, runs causality rules, and stores
    findings as a CausalSafetyReport. Never mutates the DatasetVersion.
    """
    Policy.can_manage_datasets(auth)
    verify_project_access(project_id, auth, db)

    version = db.query(DatasetVersion).filter(
        DatasetVersion.id == version_id,
        DatasetVersion.dataset_id == dataset_id,
    ).first()
    if not version:
        raise HTTPException(status_code=404, detail="Dataset version not found")

    # Load the immutable artifact
    local_storage = LocalDiskStorage()
    path = local_storage.base_path / str(auth.organization_id) / str(project_id) / str(dataset_id) / str(version.version) / "data.csv"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Artifact not found on storage")

    with open(path, "rb") as f:
        raw_bytes = f.read()
    df = pd.read_csv(io.BytesIO(raw_bytes))

    # Build safety config from request
    if safety_request:
        sr = safety_request
        config = CausalSafetyConfig(
            timestamp_column=sr.timestamp_column,
            target_column=sr.target_column,
            series_column=sr.series_column,
            feature_columns=sr.feature_columns,
            feature_timestamp_columns=sr.feature_timestamp_columns,
            partition_column=sr.partition_column,
            train_value=sr.train_value,
            test_value=sr.test_value,
            correlation_threshold=sr.correlation_threshold,
            min_observations_per_series=sr.min_observations_per_series,
            min_series_count=sr.min_series_count,
        )
        config_dict = sr.model_dump()
    else:
        config = CausalSafetyConfig()
        config_dict = {}

    # Run causal safety engine
    engine = CausalSafetyEngine()
    report = engine.analyze(df, config=config)

    # Persist
    cs_report = CausalSafetyReportModel(
        id=uuid.uuid4(),
        dataset_version_id=version.id,
        organization_id=auth.organization_id,
        verdict=report.verdict,
        total_findings=report.total_findings,
        critical_count=report.critical_count,
        unsafe_count=report.unsafe_count,
        warning_count=report.warning_count,
        info_count=report.info_count,
        findings=report.to_dict()["findings"],
        rule_config=config_dict,
    )
    db.add(cs_report)
    log_audit(db, auth.organization_id, auth.user_id, "CREATE", "CAUSAL_SAFETY_REPORT", cs_report.id)
    db.commit()
    db.refresh(cs_report)

    return cs_report


@router.get(
    "/{dataset_id}/versions/{version_id}/causal-safety",
    response_model=CausalSafetyReportResponse,
)
def get_causal_safety_report(
    project_id: UUID,
    dataset_id: UUID,
    version_id: UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    """Retrieve the latest causal safety report for a DatasetVersion."""
    Policy.can_view(auth)
    verify_project_access(project_id, auth, db)

    version = db.query(DatasetVersion).filter(
        DatasetVersion.id == version_id,
        DatasetVersion.dataset_id == dataset_id,
    ).first()
    if not version:
        raise HTTPException(status_code=404, detail="Dataset version not found")

    report = db.query(CausalSafetyReportModel).filter(
        CausalSafetyReportModel.dataset_version_id == version_id,
    ).order_by(CausalSafetyReportModel.created_at.desc()).first()

    if not report:
        raise HTTPException(status_code=404, detail="Causal safety report not found")

    return report
