"""
API integration tests for quality validation endpoints (Phase 009).
"""

import pytest
from fastapi.testclient import TestClient
from applications.api.main import app
from packages.core.db.models import (
    User, Organization, Membership, Project,
    Dataset, DatasetVersion, DataQualityReport, Base,
)
from packages.core.auth.tokens import create_access_token
from packages.core.db.session import get_db
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
def setup_data(db):
    user = User(id=uuid.uuid4(), email=f"user-{uuid.uuid4()}@example.com", password_hash="hash", status="ACTIVE")
    org = Organization(id=uuid.uuid4(), name=f"Org {uuid.uuid4()}", slug=f"org-{uuid.uuid4().hex}")
    mem = Membership(id=uuid.uuid4(), user_id=user.id, organization_id=org.id, role="OWNER", status="ACTIVE")
    project = Project(id=uuid.uuid4(), organization_id=org.id, name="Test Project", slug="test-proj")

    db.add_all([user, org, mem, project])
    db.commit()
    token = create_access_token({"sub": str(user.id)})
    return {"user": user, "org": org, "project": project, "token": token}


def _upload_csv(client, token, org_id, proj_id, dataset_id, csv_bytes):
    """Helper: upload CSV and return version response."""
    file_payload = {"file": ("data.csv", io.BytesIO(csv_bytes), "text/csv")}
    return client.post(
        f"/v1/projects/{proj_id}/datasets/{dataset_id}/versions",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id},
        files=file_payload,
    )


def test_quality_validation_clean_data(setup_data, db):
    """Clean temporal data should produce PASS verdict."""
    token = setup_data["token"]
    org_id = str(setup_data["org"].id)
    proj_id = str(setup_data["project"].id)
    client = TestClient(app)

    # Create dataset
    res = client.post(
        f"/v1/projects/{proj_id}/datasets",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id},
        json={"name": "Clean Data"},
    )
    assert res.status_code == 201
    dataset_id = res.json()["id"]

    # Upload clean CSV
    csv = b"timestamp,series_id,value\n2026-01-01T00:00:00Z,A,10.0\n2026-01-02T00:00:00Z,A,20.0\n2026-01-03T00:00:00Z,A,30.0\n"
    ver_res = _upload_csv(client, token, org_id, proj_id, dataset_id, csv)
    assert ver_res.status_code == 201
    version_id = ver_res.json()["id"]

    # Run validation (default config)
    qr = client.post(
        f"/v1/projects/{proj_id}/datasets/{dataset_id}/versions/{version_id}/quality",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id},
    )
    assert qr.status_code == 201
    report = qr.json()
    assert report["verdict"] in ("PASS", "WARN")
    assert report["critical_count"] == 0
    assert report["error_count"] == 0
    assert report["dataset_version_id"] == version_id
    assert report["organization_id"] == org_id

    # GET should return same report
    get_res = client.get(
        f"/v1/projects/{proj_id}/datasets/{dataset_id}/versions/{version_id}/quality",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id},
    )
    assert get_res.status_code == 200
    assert get_res.json()["id"] == report["id"]


def test_quality_validation_with_issues(setup_data, db):
    """Data with missing columns, duplicates, and inf should FAIL."""
    token = setup_data["token"]
    org_id = str(setup_data["org"].id)
    proj_id = str(setup_data["project"].id)
    client = TestClient(app)

    res = client.post(
        f"/v1/projects/{proj_id}/datasets",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id},
        json={"name": "Bad Data"},
    )
    dataset_id = res.json()["id"]

    # CSV with duplicates, no series_id column
    csv = b"timestamp,value\n2026-01-01,10.0\n2026-01-01,10.0\n2026-01-02,inf\n"
    ver_res = _upload_csv(client, token, org_id, proj_id, dataset_id, csv)
    version_id = ver_res.json()["id"]

    # Run validation with required_columns that includes series_id
    qr = client.post(
        f"/v1/projects/{proj_id}/datasets/{dataset_id}/versions/{version_id}/quality",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id},
        json={"required_columns": ["timestamp", "series_id", "value"]},
    )
    assert qr.status_code == 201
    report = qr.json()
    assert report["verdict"] == "FAIL"
    assert report["error_count"] >= 1

    # Verify findings contain expected rule_ids
    rule_ids = [f["rule_id"] for f in report["findings"]]
    assert "SCHEMA_REQUIRED_COLUMN" in rule_ids


def test_quality_validation_configured_bounds(setup_data, db):
    """Configured value bounds should flag out-of-range values."""
    token = setup_data["token"]
    org_id = str(setup_data["org"].id)
    proj_id = str(setup_data["project"].id)
    client = TestClient(app)

    res = client.post(
        f"/v1/projects/{proj_id}/datasets",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id},
        json={"name": "Bounded Data"},
    )
    dataset_id = res.json()["id"]

    csv = b"timestamp,series_id,value\n2026-01-01T00:00:00Z,A,-50.0\n2026-01-02T00:00:00Z,A,200.0\n2026-01-03T00:00:00Z,A,50.0\n"
    ver_res = _upload_csv(client, token, org_id, proj_id, dataset_id, csv)
    version_id = ver_res.json()["id"]

    qr = client.post(
        f"/v1/projects/{proj_id}/datasets/{dataset_id}/versions/{version_id}/quality",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id},
        json={"value_bounds": {"value": {"min": 0.0, "max": 100.0}}},
    )
    assert qr.status_code == 201
    report = qr.json()
    assert report["verdict"] == "FAIL"
    bound_findings = [f for f in report["findings"] if f["rule_id"] == "VALUE_OUT_OF_BOUNDS"]
    assert len(bound_findings) == 1
    assert bound_findings[0]["details"]["violation_count"] == 2


def test_quality_report_not_found(setup_data, db):
    """GET quality report before running validation returns 404."""
    token = setup_data["token"]
    org_id = str(setup_data["org"].id)
    proj_id = str(setup_data["project"].id)
    client = TestClient(app)

    res = client.post(
        f"/v1/projects/{proj_id}/datasets",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id},
        json={"name": "No Quality"},
    )
    dataset_id = res.json()["id"]

    csv = b"timestamp,series_id,value\n2026-01-01T00:00:00Z,A,10.0\n"
    ver_res = _upload_csv(client, token, org_id, proj_id, dataset_id, csv)
    version_id = ver_res.json()["id"]

    get_res = client.get(
        f"/v1/projects/{proj_id}/datasets/{dataset_id}/versions/{version_id}/quality",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id},
    )
    assert get_res.status_code == 404
