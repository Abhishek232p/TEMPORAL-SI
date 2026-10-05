/* ==========================================================================
   Temporal Intelligence Platform — live console client (end-to-end).
   Talks to the real REST API served by the same origin. No mocks.
   ========================================================================== */
"use strict";

const API = {
  login: "/v1/auth/login",
  orgs: "/v1/organizations",
  projects: (orgId) => `/v1/projects`,
  datasets: (projectId) => `/v1/projects/${projectId}/datasets`,
  upload: (projectId, datasetId) =>
    `/v1/projects/${projectId}/datasets/${datasetId}/versions`,
};

const state = {
  token: localStorage.getItem("tip_token") || null,
  userId: localStorage.getItem("tip_user_id") || null,
  orgId: localStorage.getItem("tip_org_id") || null,
  projectId: localStorage.getItem("tip_project_id") || null,
  datasetId: localStorage.getItem("tip_dataset_id") || null,
};

function saveState() {
  localStorage.setItem("tip_token", state.token || "");
  localStorage.setItem("tip_user_id", state.userId || "");
  localStorage.setItem("tip_org_id", state.orgId || "");
  localStorage.setItem("tip_project_id", state.projectId || "");
  localStorage.setItem("tip_dataset_id", state.datasetId || "");
}

async function api(path, opts = {}) {
  const headers = opts.headers || {};
  if (state.token) headers["Authorization"] = "Bearer " + state.token;
  if (state.orgId) headers["X-Organization-ID"] = state.orgId;
  if (!(opts.body instanceof FormData)) headers["Content-Type"] = "application/json";

  const res = await fetch(path, { ...opts, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  if (res.status === 204) return null;
  return res.json();
}

const $ = (id) => document.getElementById(id);
function note(el, msg, ok = false) {
  el.textContent = msg;
  el.classList.toggle("ok", !!msg && ok);
  el.classList.toggle("err", !!msg && !ok);
}

/* ------------------------------- Nav ------------------------------------ */
document.addEventListener("DOMContentLoaded", () => {
  $("year").textContent = new Date().getFullYear();

  const toggle = $("navToggle"), nav = $("primaryNav");
  toggle.addEventListener("click", () => {
    const open = nav.classList.toggle("open");
    toggle.setAttribute("aria-expanded", String(open));
    toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
  });
  nav.querySelectorAll("a").forEach((a) =>
    a.addEventListener("click", () => {
      nav.classList.remove("open");
      toggle.setAttribute("aria-expanded", "false");
    })
  );

  checkHealth();
  bindForms();
  if (state.token) restoreSession();
});

async function checkHealth() {
  const dot = $("healthDot");
  try {
    const h = await (await fetch("/health")).json();
    dot.textContent = "live";
    dot.classList.add("ok");
    dot.classList.remove("err");
  } catch (_) {
    dot.textContent = "offline";
    dot.classList.add("err");
  }
}

/* ------------------------------ Forms ----------------------------------- */
function bindForms() {
  $("loginForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const msg = $("loginMsg");
    const btn = $("loginBtn");
    const email = $("email").value.trim();
    const password = $("password").value;
    if (!email || password.length < 6) {
      note(msg, "Enter a valid email and a password of at least 6 characters.");
      return;
    }
    btn.disabled = true;
    note(msg, "Signing in…");
    try {
      const data = await api(API.login, {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      state.token = data.access_token;
      state.userId = data.user_id;
      saveState();
      note(msg, "Signed in.", true);
      showWorkspace();
    } catch (err) {
      note(msg, "Sign-in failed: " + err.message);
    } finally {
      btn.disabled = false;
    }
  });

  $("orgForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const org = await api(API.orgs, {
        method: "POST",
        body: JSON.stringify({ name: $("orgName").value.trim(), slug: $("orgSlug").value.trim() }),
      });
      state.orgId = org.id;
      saveState();
      renderList($("memberHint"), [`${org.name} (${org.slug}) — active org`], "ORG");
      showWorkspace();
    } catch (err) {
      alert("Create organization failed: " + err.message);
    }
  });

  $("projectForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!state.orgId) return alert("Create an organization first.");
    try {
      const proj = await api(API.projects(), {
        method: "POST",
        body: JSON.stringify({ name: $("projName").value.trim(), slug: $("projSlug").value.trim() }),
      });
      state.projectId = proj.id;
      saveState();
      await refreshProjects();
    } catch (err) {
      alert("Create project failed: " + err.message);
    }
  });

  $("datasetForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!state.projectId) return alert("Create a project first.");
    try {
      const ds = await api(API.datasets(state.projectId), {
        method: "POST",
        body: JSON.stringify({ name: $("dsName").value.trim(), source_type: "FILE" }),
      });
      state.datasetId = ds.id;
      saveState();
      await refreshDatasets();
    } catch (err) {
      alert("Create dataset failed: " + err.message);
    }
  });

  $("uploadForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!state.projectId || !state.datasetId) return alert("Create a dataset first.");
    const input = $("csvFile");
    if (!input.files.length) return note($("uploadMsg"), "Choose a .csv or .parquet file.");
    const fd = new FormData();
    fd.append("file", input.files[0]);
    note($("uploadMsg"), "Uploading…");
    try {
      const v = await api(API.upload(state.projectId, state.datasetId), { method: "POST", body: fd });
      note($("uploadMsg"), `Version ${v.version} stored — ${v.row_count} rows × ${v.column_count} cols (hash ${String(v.content_hash).slice(0, 10)}…).`, true);
      input.value = "";
    } catch (err) {
      note($("uploadMsg"), "Upload failed: " + err.message);
    }
  });
}

/* --------------------------- Rendering ---------------------------------- */
function showWorkspace() {
  $("workspace").hidden = false;
  $("authCard").style.display = "none";
  refreshProjects();
  refreshDatasets();
}

function renderList(el, items, tag) {
  el.innerHTML = "";
  items.forEach((text) => {
    const li = document.createElement("li");
    const b = document.createElement("span");
    b.className = "tag";
    b.textContent = tag;
    li.appendChild(b);
    li.appendChild(document.createTextNode(text));
    el.appendChild(li);
  });
}

async function refreshProjects() {
  if (!state.orgId) return;
  try {
    const projects = await api(API.projects());
    renderList($("projectList"), projects.map((p) => `${p.name} — /${p.slug} [${p.status}]`), "PROJECT");
    if (!state.projectId && projects.length) {
      state.projectId = projects[0].id;
      saveState();
    }
  } catch (_) {/* token expired or no org yet */}
}

async function refreshDatasets() {
  if (!state.projectId) return;
  try {
    const sets = await api(API.datasets(state.projectId));
    renderList($("datasetList"), sets.map((d) => `${d.name} — ${d.source_type} [${d.status}]`), "DATASET");
    if (!state.datasetId && sets.length) {
      state.datasetId = sets[0].id;
      saveState();
    }
  } catch (_) {}
}

async function restoreSession() {
  // Verify token still valid against the live API before rendering workspace.
  try {
    if (state.orgId) {
      await api(API.projects());
      showWorkspace();
    }
  } catch (_) {
    state.token = null;
    saveState();
  }
}
