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
    created_by: Optional[UUID] = None
    
    class Config:
        from_attributes = True

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

# Quality report schemas
class QualityValidationRequest(BaseModel):
    required_columns: Optional[List[str]] = None
    expected_dtypes: Optional[Dict[str, str]] = None
    max_null_fraction: float = 1.0
    null_check_columns: Optional[List[str]] = None
    max_duplicate_fraction: float = 0.0
    timestamp_column: str = "timestamp"
    series_column: str = "series_id"
    value_column: str = "value"
    gap_multiplier: float = 2.0
    min_series_observations: int = 2
    value_bounds: Optional[Dict[str, Dict[str, float]]] = None

class QualityFindingResponse(BaseModel):
    rule_id: str
    severity: str
    message: str
    column: Optional[str] = None
    row_indices: Optional[List[int]] = None
    measurement_type: str = "EXACT"
    details: Optional[Dict[str, Any]] = None

class QualityReportResponse(BaseModel):
    id: UUID
    dataset_version_id: UUID
    organization_id: UUID
    verdict: str
    total_findings: int
    critical_count: int
    error_count: int
    warning_count: int
    info_count: int
    findings: Optional[List[Dict[str, Any]]] = None
    rule_config: Optional[Dict[str, Any]] = None
    created_at: datetime

    class Config:
        from_attributes = True

# ---------------------------------------------------------------------------
# Phase 010 — Temporal Causal Safety
# ---------------------------------------------------------------------------

class CausalSafetyRequest(BaseModel):
    timestamp_column: str = "timestamp"
    target_column: str = "value"
    series_column: str = "series_id"
    feature_columns: Optional[List[str]] = None
    feature_timestamp_columns: Optional[Dict[str, str]] = None
    partition_column: Optional[str] = None
    train_value: str = "train"
    test_value: str = "test"
    correlation_threshold: float = 0.95
    min_observations_per_series: int = 10
    min_series_count: int = 1

class CausalEvidenceResponse(BaseModel):
    description: str
    columns_involved: Optional[List[str]] = None
    sample_rows: Optional[List[int]] = None
    statistic_name: Optional[str] = None
    statistic_value: Optional[float] = None
    threshold: Optional[float] = None
    additional: Optional[Dict[str, Any]] = None

class CausalFindingResponse(BaseModel):
    rule_id: str
    severity: str
    status: str  # DETECTED, SUSPECTED, REQUIRES_REVIEW, INSUFFICIENT_EVIDENCE
    detection_type: str  # EXACT, HEURISTIC
    confidence: float  # 0.0–1.0
    message: str
    evidence: CausalEvidenceResponse
    column: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

class CausalSafetyReportResponse(BaseModel):
    id: UUID
    dataset_version_id: UUID
    organization_id: UUID
    verdict: str
    total_findings: int
    critical_count: int
    unsafe_count: int
    warning_count: int
    info_count: int
    findings: Optional[List[Dict[str, Any]]] = None
    rule_config: Optional[Dict[str, Any]] = None
    created_at: datetime

    class Config:
        from_attributes = True
