import os
import requests
import io
import time
import pandas as pd
import numpy as np

API_URL = "http://127.0.0.1:8000/v1"

def print_step(msg):
    print(f"\n[{time.strftime('%X')}] {msg}")

def test_live_system():
    print_step("1. POST /v1/auth/login")
    login_res = requests.post(f"{API_URL}/auth/login", json={"email": "smoke@example.com", "password": "password"})
    login_res.raise_for_status()
    token = login_res.json()["access_token"]
    user_id = login_res.json()["user_id"]
    headers = {"Authorization": f"Bearer {token}"}
    print(f"Logged in successfully: user_id={user_id}")

    print_step("2. POST /v1/organizations")
    org_res = requests.post(f"{API_URL}/organizations", headers=headers, json={"name": "Smoke Test Org", "slug": f"smoke-org-{int(time.time())}"})
    org_res.raise_for_status()
    org_id = org_res.json()["id"]
    org_headers = {**headers, "X-Organization-ID": org_id}
    print(f"Organization created: {org_id}")

    print_step("3. POST /v1/projects")
    proj_res = requests.post(f"{API_URL}/projects", headers=org_headers, json={"name": "Smoke Project", "slug": f"smoke-proj-{int(time.time())}", "description": "E2E Test"})
    proj_res.raise_for_status()
    proj_id = proj_res.json()["id"]
    print(f"Project created: {proj_id}")

    print_step("4. Create/upload a DatasetVersion (with clean and leaky features)")
    # Generate dataset
    rows = 50
    dates = [pd.to_datetime("2026-01-01T00:00:00Z") + pd.Timedelta(days=i) for i in range(rows)]
    np.random.seed(42)
    # Use noise for target to prevent autocorrelated false positives on the lag
    target = np.random.normal(0, 1, rows)

    df = pd.DataFrame({
        "timestamp": dates,
        "series_id": ["A"] * rows,
        "value": target,
    })

    # Legitimate lagged feature
    df["legitimate_lag1"] = df["value"].shift(1)

    # Deliberately leaked feature (Target leakage)
    df["leaky_target_copy"] = df["value"] * 2.0

    # Deliberate future leak (Lookahead bias / Future Leakage)
    df["leaky_future_shift"] = df["value"].shift(-1)

    csv_bytes = df.to_csv(index=False).encode('utf-8')

    ds_res = requests.post(f"{API_URL}/projects/{proj_id}/datasets", headers=org_headers, json={"name": "Smoke Dataset"})
    ds_res.raise_for_status()
    dataset_id = ds_res.json()["id"]

    upload_res = requests.post(
        f"{API_URL}/projects/{proj_id}/datasets/{dataset_id}/versions",
        headers=org_headers,
        files={"file": ("smoke.csv", io.BytesIO(csv_bytes), "text/csv")}
    )
    upload_res.raise_for_status()
    version_id = upload_res.json()["id"]
    print(f"DatasetVersion uploaded: {version_id}")

    print_step("5. Retrieve the DatasetVersion")
    get_ver = requests.get(f"{API_URL}/projects/{proj_id}/datasets/{dataset_id}/versions", headers=org_headers)
    get_ver.raise_for_status()
    versions = get_ver.json()
    assert any(v["id"] == version_id for v in versions), "Uploaded version not present in listing"
    this_version = next(v for v in versions if v["id"] == version_id)
    print(f"DatasetVersion retrieved: version={this_version['version']}, rows={this_version['row_count']}")

    print_step("6. Generate /profile")
    prof_res = requests.post(f"{API_URL}/projects/{proj_id}/datasets/{dataset_id}/versions/{version_id}/profile", headers=org_headers)
    prof_res.raise_for_status()
    profile_id = prof_res.json()["id"]
    print(f"Profile generated: {profile_id}")

    print_step("7. Generate quality report")
    qual_res = requests.post(f"{API_URL}/projects/{proj_id}/datasets/{dataset_id}/versions/{version_id}/quality", headers=org_headers)
    qual_res.raise_for_status()
    quality_id = qual_res.json()["id"]
    print(f"Quality report generated: {quality_id}, verdict={qual_res.json()['verdict']}")

    print_step("8. Generate causal-safety report")
    causal_res = requests.post(f"{API_URL}/projects/{proj_id}/datasets/{dataset_id}/versions/{version_id}/causal-safety", headers=org_headers)
    causal_res.raise_for_status()
    causal_id = causal_res.json()["id"]
    causal_data = causal_res.json()
    print(f"Causal safety generated: {causal_id}, verdict={causal_data['verdict']}")

    print_step("9. Retrieve each persisted result")
    r1 = requests.get(f"{API_URL}/projects/{proj_id}/datasets/{dataset_id}/versions/{version_id}/profile", headers=org_headers)
    r1.raise_for_status()
    r2 = requests.get(f"{API_URL}/projects/{proj_id}/datasets/{dataset_id}/versions/{version_id}/quality", headers=org_headers)
    r2.raise_for_status()
    r3 = requests.get(f"{API_URL}/projects/{proj_id}/datasets/{dataset_id}/versions/{version_id}/causal-safety", headers=org_headers)
    r3.raise_for_status()
    print(f"Persisted results successfully retrieved via GET.")

    print_step("10. Confirm tenant isolation with a second organization")
    org2_res = requests.post(f"{API_URL}/organizations", headers=headers, json={"name": "Org 2", "slug": f"smoke-org2-{int(time.time())}"})
    org2_id = org2_res.json()["id"]
    org2_headers = {**headers, "X-Organization-ID": org2_id}
    
    # Try to access proj_id with org2_headers
    iso_res = requests.get(f"{API_URL}/projects/{proj_id}", headers=org2_headers)
    if iso_res.status_code in [403, 404]:
         print(f"Tenant isolation working. Request returned {iso_res.status_code}.")
    else:
         print(f"Tenant isolation FAILED. Request returned {iso_res.status_code}.")
         raise Exception("Isolation fail")

    print_step("11. Confirm deliberately leaked feature produces the expected causal warning")
    findings = causal_data["findings"]
    leaky_target = [f for f in findings if f["column"] == "leaky_target_copy"]
    assert len(leaky_target) > 0, "No finding for leaky_target_copy"
    assert leaky_target[0]["rule_id"] == "TARGET_LEAKAGE"
    assert leaky_target[0]["detection_type"] == "HEURISTIC"
    print(f"Target leakage correctly detected for leaky_target_copy.")
    
    leaky_future = [f for f in findings if f["column"] == "leaky_future_shift"]
    assert len(leaky_future) > 0, "No finding for leaky_future_shift"
    assert leaky_future[0]["rule_id"] == "FUTURE_VALUE_LEAKAGE"
    assert leaky_future[0]["detection_type"] == "HEURISTIC"
    print(f"Future leakage correctly detected for leaky_future_shift.")

    print_step("12. Confirm legitimate lagged feature does NOT produce CAUSAL_UNSAFE")
    legit_lag = [f for f in findings if f["column"] == "legitimate_lag1" and f["rule_id"] in ["TARGET_LEAKAGE", "FUTURE_VALUE_LEAKAGE", "LOOKAHEAD_BIAS"]]
    assert len(legit_lag) == 0, f"False positive triggered for legitimate lag! {legit_lag}"
    assert causal_data["verdict"] == "SAFE_WITH_WARNINGS", f"Verdict was {causal_data['verdict']} instead of SAFE_WITH_WARNINGS"
    print(f"Legitimate lag passed. Verdict correctly evaluated to SAFE_WITH_WARNINGS.")

    print_step("All Phase 010 live smoke tests passed!")

if __name__ == "__main__":
    test_live_system()
