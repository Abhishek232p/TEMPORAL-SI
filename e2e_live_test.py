"""End-to-end live render test: exercises the FULL user journey against the running server.
Login -> Org -> Project -> Dataset -> CSV upload -> Profile -> Quality -> Causality."""
import io, json, sys, urllib.request, urllib.error

BASE = "http://localhost:8000"

def call(path, method="GET", data=None, token=None, org=None, files=None, raw=False):
    headers = {}
    if token: headers["Authorization"] = "Bearer " + token
    if org: headers["X-Organization-ID"] = org
    body = None
    if files:
        import uuid as _u
        boundary = "----tip" + _u.uuid4().hex
        fname, content = files
        part = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{fname}\"\r\n"
                f"Content-Type: text/csv\r\n\r\n").encode() + content + f"\r\n--{boundary}--\r\n".encode()
        body = part
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    elif data is not None:
        body = json.dumps(data).encode(); headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            txt = r.read().decode()
            return r.status, (txt if raw else (json.loads(txt) if txt else None))
    except urllib.error.HTTPError as e:
        txt = e.read().decode()
        try: return e.code, json.loads(txt)
        except Exception: return e.code, txt

ok = True
def check(name, cond, extra=""):
    global ok
    print(("PASS " if cond else "FAIL ") + name + (" | " + str(extra)[:160] if extra else ""))
    if not cond: ok = False

import uuid as _uuid
RUN = _uuid.uuid4().hex[:8]  # unique per run so the live test is idempotent against persistent DB

# 1. Live render of home page (HTML shell for every device)
st, html = call("/", raw=True)
check("live render GET / returns HTML", st == 200 and "<!DOCTYPE html>" in html and 'name="viewport"' in html, st)
check("responsive CSS linked", "/static/css/styles.css" in html)
check("console JS linked", "/static/js/app.js" in html)

# 2. Auth (real bcrypt now)
st, r = call("/v1/auth/login", "POST", {"email": f"founder-{RUN}@acme.io", "password": "supersecret"})
check("login/auto-register 200 + token", st == 200 and "access_token" in (r or {}), st)
token = (r or {}).get("access_token")
st2, _ = call("/v1/auth/login", "POST", {"email": f"founder-{RUN}@acme.io", "password": "WRONGpass"})
check("wrong password rejected 401", st2 == 401, st2)
st3, _ = call("/v1/auth/login", "POST", {"email": f"founder-{RUN}@acme.io", "password": "supersecret"})
check("re-login with bcrypt hash works", st3 == 200, st3)

# 3. Organization
st, org = call("/v1/organizations", "POST", {"name": "Acme Analytics", "slug": f"acme-analytics-{RUN}"}, token=token)
check("create organization 201", st == 201, (st, org))
org_id = (org or {}).get("id")
if org_id is None:  # slug collision fallback: reuse first existing org
    st, lst = call("/v1/organizations", token=token)
    if st == 200 and lst: org_id = lst[0]["id"] if isinstance(lst, list) else lst.get("items", [{}])[0].get("id")

# 4. Project
st, proj = call("/v1/projects", "POST", {"name": "Demand Forecasting", "slug": f"demand-forecasting-{RUN}"}, token=token, org=org_id)
check("create project 201", st == 201, (st, proj))
proj_id = (proj or {}).get("id")
st, lst = call("/v1/projects", token=token, org=org_id)
check("list projects shows created project", st == 200 and any(p["id"] == proj_id for p in lst), st)

# 5. Tenant isolation: another user cannot see this org's projects
st, tok2 = call("/v1/auth/login", "POST", {"email": f"intruder-{RUN}@evil.io", "password": "hunter22"})
st2, forb = call("/v1/projects", token=tok2.get("access_token"), org=org_id)
check("cross-tenant access blocked 403", st2 == 403, (st2, forb))

# 6. Dataset
st, ds = call(f"/v1/projects/{proj_id}/datasets", "POST", {"name": "Daily Sales", "source_type": "FILE"}, token=token, org=org_id)
check("create dataset 201", st == 201, (st, ds))
ds_id = (ds or {}).get("id")

# 7. Upload CSV version
csv = b"date,sales,region\n2026-01-01,120,north\n2026-01-02,135,north\n2026-01-03,98,south\n2026-01-04,144,south\n2026-01-05,150,north\n"
st, ver = call(f"/v1/projects/{proj_id}/datasets/{ds_id}/versions", "POST", files=("sales.csv", csv), token=token, org=org_id)
check("upload CSV version 201 w/ row+col counts", st == 201 and ver.get("row_count") == 5 and ver.get("column_count") == 3, (st, ver))
ver_id = (ver or {}).get("id")

# 8. Profile the version
st, prof = call(f"/v1/projects/{proj_id}/datasets/{ds_id}/versions/{ver_id}/profile", "POST", token=token, org=org_id)
check("data profile created", st in (200, 201), (st, prof))

# 9. Quality validation on the uploaded version
st, q = call(f"/v1/projects/{proj_id}/datasets/{ds_id}/versions/{ver_id}/quality", "POST",
             {"required_columns": ["date", "sales"], "timestamp_column": "date"}, token=token, org=org_id)
check("quality report generated", st == 201 and "verdict" in (q or {}), (st, q))

# 10. Causal safety scan
st, cs = call(f"/v1/projects/{proj_id}/datasets/{ds_id}/versions/{ver_id}/causal-safety", "POST",
              {"timestamp_column": "date", "target_column": "sales"}, token=token, org=org_id)
check("causal-safety report generated", st == 201 and "verdict" in (cs or {}), (st, cs))

# 11. Read-back endpoints (GET profile/quality/causal-safety)
st, gp = call(f"/v1/projects/{proj_id}/datasets/{ds_id}/versions/{ver_id}/profile", token=token, org=org_id)
check("profile read-back", st == 200, st)
st, gq = call(f"/v1/projects/{proj_id}/datasets/{ds_id}/versions/{ver_id}/quality", token=token, org=org_id)
check("quality read-back", st == 200, st)
st, gc = call(f"/v1/projects/{proj_id}/datasets/{ds_id}/versions/{ver_id}/causal-safety", token=token, org=org_id)
check("causal-safety read-back", st == 200, st)

print("\nRESULT:", "ALL PASS" if ok else "FAILURES PRESENT")
sys.exit(0 if ok else 1)
