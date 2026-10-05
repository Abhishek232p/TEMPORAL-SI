"""
API integration tests for causal safety endpoints (Phase 010).
"""

import pytest
from fastapi.testclient import TestClient
from applications.api.main import app
from packages.core.db.models import (
    User, Organization, Membership, Project,
    Dataset, DatasetVersion, CausalSafetyReportModel, Base,
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
    file_payload = {"file": ("data.csv", io.BytesIO(csv_bytes), "text/csv")}
    return client.post(
        f"/v1/projects/{proj_id}/datasets/{dataset_id}/versions",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id},
        files=file_payload,
    )


def test_causal_safety_insufficient_data(setup_data, db):
    """Test that a tiny dataset returns INSUFFICIENT_EVIDENCE."""
    token = setup_data["token"]
    org_id = str(setup_data["org"].id)
    proj_id = str(setup_data["project"].id)
    client = TestClient(app)

    res = client.post(
        f"/v1/projects/{proj_id}/datasets",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id},
        json={"name": "Tiny Data"},
    )
    dataset_id = res.json()["id"]

    # Only 3 rows, min required is 10
    csv = b"timestamp,series_id,value\n2026-01-01T00:00:00Z,A,10.0\n2026-01-02T00:00:00Z,A,20.0\n2026-01-03T00:00:00Z,A,30.0\n"
    ver_res = _upload_csv(client, token, org_id, proj_id, dataset_id, csv)
    version_id = ver_res.json()["id"]

    csr = client.post(
        f"/v1/projects/{proj_id}/datasets/{dataset_id}/versions/{version_id}/causal-safety",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id},
    )
    assert csr.status_code == 201
    report = csr.json()
    assert report["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert report["total_findings"] >= 1
    
    # GET endpoint should retrieve the same report
    get_res = client.get(
        f"/v1/projects/{proj_id}/datasets/{dataset_id}/versions/{version_id}/causal-safety",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id},
    )
    assert get_res.status_code == 200
    assert get_res.json()["id"] == report["id"]


def test_causal_safety_target_leakage(setup_data, db):
    """Target leakage is HEURISTIC → SAFE_WITH_WARNINGS, not CAUSAL_UNSAFE."""
    token = setup_data["token"]
    org_id = str(setup_data["org"].id)
    proj_id = str(setup_data["project"].id)
    client = TestClient(app)

    res = client.post(
        f"/v1/projects/{proj_id}/datasets",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id},
        json={"name": "Leaky Data"},
    )
    dataset_id = res.json()["id"]

    # 12 rows to pass sufficiency check.
    # feature_x is perfectly correlated with value (target)
    csv = b"timestamp,series_id,value,feature_x\n"
    for i in range(12):
        csv += f"2026-01-{i+1:02d}T00:00:00Z,A,{i*10.0},{i*10.0}\n".encode()

    ver_res = _upload_csv(client, token, org_id, proj_id, dataset_id, csv)
    version_id = ver_res.json()["id"]

    csr = client.post(
        f"/v1/projects/{proj_id}/datasets/{dataset_id}/versions/{version_id}/causal-safety",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id},
    )
    assert csr.status_code == 201
    report = csr.json()
    # HEURISTIC-only → SAFE_WITH_WARNINGS, NOT CAUSAL_UNSAFE
    assert report["verdict"] == "SAFE_WITH_WARNINGS"
    
    findings = report["findings"]
    leak_finding = next((f for f in findings if f["rule_id"] == "TARGET_LEAKAGE"), None)
    assert leak_finding is not None
    assert leak_finding["column"] == "feature_x"
    # Verify new fields are present and correct
    assert leak_finding["detection_type"] == "HEURISTIC"
    assert leak_finding["status"] == "SUSPECTED"
    assert 0.0 <= leak_finding["confidence"] <= 1.0
    assert "evidence" in leak_finding
    assert leak_finding["evidence"]["statistic_name"] == "pearson_correlation_with_target"
    assert leak_finding["evidence"]["statistic_value"] == 1.0


def test_causality_train_test_contamination(setup_data, db):
    """Test that train/test overlapping timestamps trigger a CRITICAL finding."""
    token = setup_data["token"]
    org_id = str(setup_data["org"].id)
    proj_id = str(setup_data["project"].id)
    client = TestClient(app)

    res = client.post(
        f"/v1/projects/{proj_id}/datasets",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id},
        json={"name": "Contaminated Data"},
    )
    dataset_id = res.json()["id"]

    csv = b"timestamp,series_id,value,partition\n"
    for i in range(15):
        part = "train" if i < 10 else "test"
        ts = f"2026-01-{i+1:02d}T00:00:00Z"
        csv += f"{ts},A,{i*10.0},{part}\n".encode()
    
    # Introduce contamination: add a train row with a timestamp far in the future
    csv += b"2026-01-20T00:00:00Z,A,100.0,train\n"

    ver_res = _upload_csv(client, token, org_id, proj_id, dataset_id, csv)
    version_id = ver_res.json()["id"]

    csr = client.post(
        f"/v1/projects/{proj_id}/datasets/{dataset_id}/versions/{version_id}/causal-safety",
        headers={"Authorization": f"Bearer {token}", "X-Organization-ID": org_id},
        json={"partition_column": "partition"}
    )
    assert csr.status_code == 201
    report = csr.json()
    # EXACT violation → CAUSAL_UNSAFE
    assert report["verdict"] == "CAUSAL_UNSAFE"
    assert report["critical_count"] >= 1
    
    findings = report["findings"]
    overlap_finding = next((f for f in findings if f["rule_id"] == "TRAIN_TEST_TEMPORAL_OVERLAP"), None)
    assert overlap_finding is not None
    # Verify EXACT structural detection
    assert overlap_finding["detection_type"] == "EXACT"
    assert overlap_finding["status"] == "DETECTED"
    assert overlap_finding["confidence"] == 1.0
    assert overlap_finding["evidence"]["statistic_value"] >= 1
