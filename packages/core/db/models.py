import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Boolean, CheckConstraint, UniqueConstraint, JSON, Float
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.types import JSON

JSON_VARIANT = JSON().with_variant(JSONB, 'postgresql')

Base = declarative_base()

def generate_uuid():
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = 'users'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String)
    display_name = Column(String)
    status = Column(String, default='ACTIVE')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Organization(Base):
    __tablename__ = 'organizations'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False, index=True)
    status = Column(String, default='ACTIVE')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Membership(Base):
    __tablename__ = 'memberships'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    role = Column(String, nullable=False) # OWNER, ADMIN, MEMBER, VIEWER
    status = Column(String, default='ACTIVE')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint('user_id', 'organization_id', name='uq_user_org'),
        CheckConstraint("role IN ('OWNER', 'ADMIN', 'MEMBER', 'VIEWER')", name='check_valid_role')
    )

class Project(Base):
    __tablename__ = 'projects'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False)
    description = Column(String)
    status = Column(String, default='ACTIVE')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint('organization_id', 'slug', name='uq_org_project_slug'),
    )

class Dataset(Base):
    __tablename__ = 'datasets'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey('projects.id', ondelete='CASCADE'), nullable=False)
    name = Column(String, nullable=False)
    description = Column(String)
    source_type = Column(String)
    status = Column(String, default='ACTIVE')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class DatasetVersion(Base):
    __tablename__ = 'dataset_versions'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_id = Column(UUID(as_uuid=True), ForeignKey('datasets.id', ondelete='RESTRICT'), nullable=False)
    organization_id = Column(UUID(as_uuid=True), nullable=False) # Denormalized for security checks
    version = Column(Integer, nullable=False)
    content_hash = Column(String, nullable=False)
    schema_hash = Column(String)
    row_count = Column(Integer)
    column_count = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True))
    
    __table_args__ = (
        UniqueConstraint('dataset_id', 'version', name='uq_dataset_version'),
    )

class DataProfile(Base):
    __tablename__ = 'data_profiles'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_version_id = Column(UUID(as_uuid=True), ForeignKey('dataset_versions.id', ondelete='CASCADE'), nullable=False)
    row_count = Column(Integer)
    column_count = Column(Integer)
    schema_summary = Column(JSON_VARIANT)
    created_at = Column(DateTime, default=datetime.utcnow)

class Model(Base):
    __tablename__ = 'models'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'))
    name = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    model_type = Column(String)
    status = Column(String, default='ACTIVE')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ModelVersion(Base):
    __tablename__ = 'model_versions'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id = Column(UUID(as_uuid=True), ForeignKey('models.id', ondelete='RESTRICT'), nullable=False)
    version = Column(Integer, nullable=False)
    artifact_uri = Column(String)
    artifact_hash = Column(String)
    configuration = Column(JSON_VARIANT)
    code_commit = Column(String)
    environment_hash = Column(String)
    status = Column(String, default='EXPERIMENTAL')
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('model_id', 'version', name='uq_model_version'),
        CheckConstraint(
            "status IN ('DRAFT', 'EXPERIMENTAL', 'VALIDATED', 'SHADOW', 'PRODUCTION', 'DEPRECATED', 'RETIRED')", 
            name='check_model_status'
        )
    )

class ForecastRun(Base):
    __tablename__ = 'forecast_runs'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), nullable=False)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    dataset_version_id = Column(UUID(as_uuid=True), ForeignKey('dataset_versions.id', ondelete='RESTRICT'), nullable=False)
    model_version_id = Column(UUID(as_uuid=True), ForeignKey('model_versions.id', ondelete='RESTRICT'), nullable=False)
    status = Column(String, default='QUEUED')
    horizon = Column(Integer, nullable=False)
    configuration = Column(JSON_VARIANT)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

class ForecastPoint(Base):
    __tablename__ = 'forecast_points'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    forecast_run_id = Column(UUID(as_uuid=True), ForeignKey('forecast_runs.id', ondelete='CASCADE'), nullable=False)
    timestamp = Column(DateTime, nullable=False)
    target = Column(String, nullable=False)
    predicted_value = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class PredictionInterval(Base):
    __tablename__ = 'prediction_intervals'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    forecast_point_id = Column(UUID(as_uuid=True), ForeignKey('forecast_points.id', ondelete='CASCADE'), nullable=False)
    level = Column(Float, nullable=False)
    lower_value = Column(Float, nullable=False)
    upper_value = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint('lower_value <= upper_value', name='check_interval_bounds'),
    )

class GraphNode(Base):
    __tablename__ = 'graph_nodes'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), nullable=False)
    node_type = Column(String, nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    metadata_ = Column(JSON_VARIANT)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        CheckConstraint(
            "node_type IN ('USER', 'ORGANIZATION', 'PROJECT', 'DATASET', 'DATASET_VERSION', 'FEATURE', 'MODEL', 'MODEL_VERSION', 'EXPERIMENT', 'EVALUATION', 'FORECAST', 'EVIDENCE', 'PROOF', 'ALERT', 'OUTCOME')", 
            name='check_node_type'
        ),
    )

class GraphEdge(Base):
    __tablename__ = 'graph_edges'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), nullable=False)
    source_node_id = Column(UUID(as_uuid=True), ForeignKey('graph_nodes.id', ondelete='CASCADE'), nullable=False, index=True)
    target_node_id = Column(UUID(as_uuid=True), ForeignKey('graph_nodes.id', ondelete='CASCADE'), nullable=False, index=True)
    edge_type = Column(String, nullable=False)
    metadata_ = Column(JSON_VARIANT)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        CheckConstraint(
            "edge_type IN ('BELONGS_TO', 'DERIVED_FROM', 'VERSION_OF', 'USES', 'PREDICTS', 'EVALUATED_BY', 'SUPPORTED_BY', 'OBSERVED_AS', 'TRIGGERS', 'DEPENDS_ON', 'RELATED_TO')", 
            name='check_edge_type'
        ),
        UniqueConstraint('source_node_id', 'target_node_id', 'edge_type', name='uq_graph_edge'),
    )

# ... (Additional tables like Evidence, ProofObject, AuditLog, etc. elided for brevity in this snippet, but would be added similarly to fulfill the spec)

class DataSource(Base):
    __tablename__ = 'data_sources'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    dataset_id = Column(UUID(as_uuid=True), ForeignKey('datasets.id', ondelete='CASCADE'), nullable=False)
    category = Column(String, nullable=False)
    metadata_ = Column(JSON_VARIANT)
    created_at = Column(DateTime, default=datetime.utcnow)

class DataQualityReport(Base):
    __tablename__ = 'data_quality_reports'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_version_id = Column(UUID(as_uuid=True), ForeignKey('dataset_versions.id', ondelete='CASCADE'), nullable=False)
    organization_id = Column(UUID(as_uuid=True), nullable=False)
    verdict = Column(String, nullable=False)  # PASS, WARN, FAIL
    total_findings = Column(Integer, default=0)
    critical_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    warning_count = Column(Integer, default=0)
    info_count = Column(Integer, default=0)
    findings = Column(JSON_VARIANT)
    rule_config = Column(JSON_VARIANT)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint("verdict IN ('PASS', 'WARN', 'FAIL')", name='check_quality_verdict'),
    )

class CausalSafetyReportModel(Base):
    __tablename__ = 'causal_safety_reports'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_version_id = Column(UUID(as_uuid=True), ForeignKey('dataset_versions.id', ondelete='CASCADE'), nullable=False)
    organization_id = Column(UUID(as_uuid=True), nullable=False)
    verdict = Column(String, nullable=False)  # CAUSAL_SAFE, SAFE_WITH_WARNINGS, CAUSAL_UNSAFE, INSUFFICIENT_EVIDENCE
    total_findings = Column(Integer, default=0)
    critical_count = Column(Integer, default=0)
    unsafe_count = Column(Integer, default=0)
    warning_count = Column(Integer, default=0)
    info_count = Column(Integer, default=0)
    findings = Column(JSON_VARIANT)
    rule_config = Column(JSON_VARIANT)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint(
            "verdict IN ('CAUSAL_SAFE', 'SAFE_WITH_WARNINGS', 'CAUSAL_UNSAFE', 'INSUFFICIENT_EVIDENCE')",
            name='check_causal_verdict'
        ),
    )

class Feature(Base):
    __tablename__ = 'features'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey('projects.id', ondelete='CASCADE'), nullable=False)
    dataset_version_id = Column(UUID(as_uuid=True), ForeignKey('dataset_versions.id', ondelete='CASCADE'), nullable=False)
    name = Column(String, nullable=False)
    data_type = Column(String, nullable=False)
    semantic_type = Column(String)
    role = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Experiment(Base):
    __tablename__ = 'experiments'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey('projects.id', ondelete='CASCADE'), nullable=False)
    name = Column(String, nullable=False)
    description = Column(String)
    status = Column(String, default='ACTIVE')
    configuration = Column(JSON_VARIANT)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Evaluation(Base):
    __tablename__ = 'evaluations'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey('projects.id', ondelete='CASCADE'), nullable=False)
    dataset_version_id = Column(UUID(as_uuid=True), ForeignKey('dataset_versions.id', ondelete='RESTRICT'), nullable=False)
    model_version_id = Column(UUID(as_uuid=True), ForeignKey('model_versions.id', ondelete='RESTRICT'), nullable=False)
    experiment_id = Column(UUID(as_uuid=True), ForeignKey('experiments.id', ondelete='CASCADE'))
    configuration = Column(JSON_VARIANT)
    status = Column(String, default='COMPLETED')
    metrics = Column(JSON_VARIANT)
    calibration_metrics = Column(JSON_VARIANT)
    evaluation_window = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class ProvenanceRecord(Base):
    __tablename__ = 'provenance_records'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_hash = Column(String)
    dataset_version_id = Column(UUID(as_uuid=True), ForeignKey('dataset_versions.id', ondelete='RESTRICT'))
    model_version_id = Column(UUID(as_uuid=True), ForeignKey('model_versions.id', ondelete='RESTRICT'))
    code_commit = Column(String)
    configuration_hash = Column(String)
    environment_hash = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class Evidence(Base):
    __tablename__ = 'evidence'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    forecast_run_id = Column(UUID(as_uuid=True), ForeignKey('forecast_runs.id', ondelete='CASCADE'), nullable=False)
    dataset_version_id = Column(UUID(as_uuid=True), ForeignKey('dataset_versions.id', ondelete='RESTRICT'))
    model_version_id = Column(UUID(as_uuid=True), ForeignKey('model_versions.id', ondelete='RESTRICT'))
    evaluation_id = Column(UUID(as_uuid=True), ForeignKey('evaluations.id', ondelete='RESTRICT'))
    provenance_id = Column(UUID(as_uuid=True), ForeignKey('provenance_records.id', ondelete='RESTRICT'))
    metadata_ = Column(JSON_VARIANT)
    created_at = Column(DateTime, default=datetime.utcnow)

class ProofObject(Base):
    __tablename__ = 'proof_objects'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    forecast_run_id = Column(UUID(as_uuid=True), ForeignKey('forecast_runs.id', ondelete='RESTRICT'), nullable=False)
    payload = Column(JSON_VARIANT)
    created_at = Column(DateTime, default=datetime.utcnow)

class Alert(Base):
    __tablename__ = 'alerts'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey('projects.id', ondelete='CASCADE'), nullable=False)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)
    condition = Column(JSON_VARIANT)
    status = Column(String, default='ACTIVE')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class AuditLog(Base):
    __tablename__ = 'audit_logs'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='RESTRICT'), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey('projects.id', ondelete='RESTRICT'))
    actor_id = Column(UUID(as_uuid=True))
    action = Column(String, nullable=False)
    resource_type = Column(String)
    resource_id = Column(UUID(as_uuid=True))
    metadata_ = Column(JSON_VARIANT)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

class UsageRecord(Base):
    __tablename__ = 'usage_records'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey('organizations.id', ondelete='RESTRICT'), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey('projects.id', ondelete='RESTRICT'))
    actor_id = Column(UUID(as_uuid=True))
    resource_type = Column(String)
    operation = Column(String)
    quantity = Column(Float)
    unit = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    metadata_ = Column(JSON_VARIANT)

class IngestionJob(Base):
    __tablename__ = 'ingestion_jobs'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_id = Column(UUID(as_uuid=True), ForeignKey('datasets.id', ondelete='CASCADE'), nullable=False)
    source_id = Column(UUID(as_uuid=True), ForeignKey('data_sources.id', ondelete='CASCADE'), nullable=False)
    status = Column(String, default='PENDING') # PENDING, RUNNING, SUCCEEDED, FAILED
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    error_message = Column(String)
    rows_ingested = Column(Integer)
    dataset_version_id = Column(UUID(as_uuid=True), ForeignKey('dataset_versions.id', ondelete='SET NULL'))
    created_at = Column(DateTime, default=datetime.utcnow)

class IngestionCheckpoint(Base):
    __tablename__ = 'ingestion_checkpoints'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_id = Column(UUID(as_uuid=True), ForeignKey('datasets.id', ondelete='CASCADE'), nullable=False)
    source_id = Column(UUID(as_uuid=True), ForeignKey('data_sources.id', ondelete='CASCADE'), nullable=False)
    last_successful_timestamp = Column(DateTime)
    last_successful_cursor = Column(String)
    last_successful_content_hash = Column(String)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
