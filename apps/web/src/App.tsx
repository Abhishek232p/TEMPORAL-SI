import { useCallback, useEffect, useMemo, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import './App.css';

type Organization = { id: string; name: string; slug: string; status: string };
type Project = { id: string; name: string; slug: string; description?: string };
type Dataset = { id: string; name: string; description?: string; created_at: string };
type DatasetVersion = {
  id: string;
  version: number;
  row_count?: number;
  column_count?: number;
  content_hash: string;
  created_at: string;
};
type Finding = {
  rule_id: string;
  severity: string;
  message: string;
  column?: string;
  status?: string;
  detection_type?: string;
  confidence?: number;
  evidence?: { description?: string; statistic_name?: string; statistic_value?: number; threshold?: number };
};
type Report = {
  id: string;
  verdict: string;
  total_findings: number;
  critical_count?: number;
  error_count?: number;
  unsafe_count?: number;
  warning_count?: number;
  info_count?: number;
  findings?: Finding[];
  created_at: string;
};
type Profile = {
  id: string;
  created_at?: string;
  row_count?: number;
  column_count?: number;
  schema_summary?: {
    general_statistics?: { duplicate_rows?: number; columns?: Record<string, { type?: string; null_count?: number; null_percentage?: number; unique_count?: number }> };
    temporal_statistics?: { series_count?: number; min_timestamp?: string; max_timestamp?: string; gap_count_sample?: number; irregular_series_sample_count?: number };
  };
};
type ServiceHealth = {
  status: string;
  services?: Record<string, { status: string; persistence?: string }>;
};

const API_BASE = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '');
const TOKEN_KEY = 'temporal.access-token';

class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  path: string,
  token?: string,
  organizationId?: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (organizationId) headers.set('X-Organization-ID', organizationId);
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      message = typeof body.detail === 'string' ? body.detail : message;
    } catch {
      // Keep the HTTP status message when the server did not return JSON.
    }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function slugify(value: string) {
  return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
}

function formatDate(value?: string) {
  if (!value) return '—';
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
}

function App() {
  const [token, setToken] = useState(() => sessionStorage.getItem(TOKEN_KEY) ?? '');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [health, setHealth] = useState<ServiceHealth | null>(null);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [organization, setOrganization] = useState<Organization | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState<Project | null>(null);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [versions, setVersions] = useState<DatasetVersion[]>([]);
  const [version, setVersion] = useState<DatasetVersion | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [quality, setQuality] = useState<Report | null>(null);
  const [causal, setCausal] = useState<Report | null>(null);
  const [workspaceName, setWorkspaceName] = useState('');
  const [projectName, setProjectName] = useState('');
  const [datasetName, setDatasetName] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [busyAction, setBusyAction] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [authReady, setAuthReady] = useState(() => !sessionStorage.getItem(TOKEN_KEY));
  const [today] = useState(() => new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date()));

  const signedIn = Boolean(token);
  const dataPath = useMemo(
    () => project && dataset ? `/v1/projects/${project.id}/datasets/${dataset.id}` : '',
    [project, dataset],
  );

  const loadHealth = useCallback(async () => {
    try {
      setHealth(await request<ServiceHealth>('/health'));
    } catch {
      setHealth({ status: 'unavailable', services: { api: { status: 'unavailable' } } });
    }
  }, []);

  const loadOrganizations = useCallback(async (accessToken: string) => {
    const items = await request<Organization[]>('/v1/organizations', accessToken);
    setOrganizations(items);
    const first = items[0] ?? null;
    setOrganization(first);
    setProjects([]);
    setProject(null);
    setDatasets([]);
    setDataset(null);
    setVersions([]);
    setVersion(null);
    setProfile(null);
    setQuality(null);
    setCausal(null);
    if (first) {
      const nextProjects = await request<Project[]>('/v1/projects', accessToken, first.id);
      setProjects(nextProjects);
      setProject(nextProjects[0] ?? null);
      if (nextProjects[0]) {
        const nextDatasets = await request<Dataset[]>(
          `/v1/projects/${nextProjects[0].id}/datasets`,
          accessToken,
          first.id,
        );
        setDatasets(nextDatasets);
        setDataset(nextDatasets[0] ?? null);
      }
    }
    setAuthReady(true);
  }, []);

  useEffect(() => {
    void loadHealth();
    const timer = window.setInterval(() => void loadHealth(), 30_000);
    return () => window.clearInterval(timer);
  }, [loadHealth]);

  useEffect(() => {
    if (!token) return;
    let active = true;
    void loadOrganizations(token).catch((reason: unknown) => {
      if (!active) return;
      if (reason instanceof ApiError && reason.status === 401) {
        sessionStorage.removeItem(TOKEN_KEY);
        setToken('');
      } else {
        setError(reason instanceof Error ? reason.message : 'Could not load your workspaces.');
      }
      setAuthReady(true);
    });
    return () => { active = false; };
  }, [token, loadOrganizations]);

  useEffect(() => {
    if (!token || !organization || !project || !dataset) return;
    let active = true;
    void request<DatasetVersion[]>(`${dataPath}/versions`, token, organization.id)
      .then(async (items) => {
        if (!active) return;
        setVersions(items);
        const selected = items[0] ?? null;
        setVersion(selected);
        if (!selected) return;
        const versionPath = `${dataPath}/versions/${selected.id}`;
        const optional = <T,>(suffix: string) => request<T>(`${versionPath}/${suffix}`, token, organization.id)
          .catch((reason: unknown) => {
            if (reason instanceof ApiError && reason.status === 404) return null;
            throw reason;
          });
        const [nextProfile, nextQuality, nextCausal] = await Promise.all([
          optional<Profile>('profile'),
          optional<Report>('quality'),
          optional<Report>('causal-safety'),
        ]);
        if (!active) return;
        setProfile(nextProfile);
        setQuality(nextQuality);
        setCausal(nextCausal);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : 'Could not load dataset versions.');
      });
    return () => { active = false; };
  }, [token, organization, project, dataset, dataPath]);

  function clearMessages() {
    setError('');
    setNotice('');
  }

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    clearMessages();
    setBusy(true);
    try {
      const result = await request<{ access_token: string; user_id: string }>('/v1/auth/login', undefined, undefined, {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      });
      sessionStorage.setItem(TOKEN_KEY, result.access_token);
      setAuthReady(false);
      setToken(result.access_token);
      setPassword('');
      await loadOrganizations(result.access_token);
      setNotice('Signed in successfully.');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Sign-in failed.');
    } finally {
      setBusy(false);
    }
  }

  async function createWorkspace(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    clearMessages();
    setBusy(true);
    try {
      const created = await request<Organization>('/v1/organizations', token, undefined, {
        method: 'POST',
        body: JSON.stringify({ name: workspaceName.trim(), slug: slugify(workspaceName) }),
      });
      setOrganizations([created]);
      setOrganization(created);
      setWorkspaceName('');
      setNotice('Workspace created. Add a project to start organizing datasets.');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Workspace creation failed.');
    } finally {
      setBusy(false);
    }
  }

  async function changeOrganization(id: string) {
    clearMessages();
    const selected = organizations.find((item) => item.id === id) ?? null;
    setOrganization(selected);
    setProject(null);
    setDataset(null);
    setVersions([]);
    setVersion(null);
    setProfile(null);
    setQuality(null);
    setCausal(null);
    if (!selected) return;
    setBusy(true);
    try {
      const items = await request<Project[]>('/v1/projects', token, selected.id);
      setProjects(items);
      setProject(items[0] ?? null);
      if (items[0]) {
        const nextDatasets = await request<Dataset[]>(`/v1/projects/${items[0].id}/datasets`, token, selected.id);
        setDatasets(nextDatasets);
        setDataset(nextDatasets[0] ?? null);
      } else {
        setDatasets([]);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not switch workspace.');
    } finally {
      setBusy(false);
    }
  }

  async function createProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!organization) return;
    clearMessages();
    setBusy(true);
    try {
      const created = await request<Project>('/v1/projects', token, organization.id, {
        method: 'POST',
        body: JSON.stringify({
          name: projectName.trim(),
          slug: slugify(projectName),
          description: 'Time-series validation workspace',
        }),
      });
      setProjects((current) => [...current, created]);
      setProject(created);
      setDatasets([]);
      setDataset(null);
      setProjectName('');
      setNotice('Project created. Create a dataset and upload a CSV or Parquet file.');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Project creation failed.');
    } finally {
      setBusy(false);
    }
  }

  async function changeProject(id: string) {
    if (!organization) return;
    clearMessages();
    const selected = projects.find((item) => item.id === id) ?? null;
    setProject(selected);
    setDataset(null);
    setVersions([]);
    setVersion(null);
    setProfile(null);
    setQuality(null);
    setCausal(null);
    if (!selected) return;
    setBusy(true);
    try {
      const items = await request<Dataset[]>(`/v1/projects/${selected.id}/datasets`, token, organization.id);
      setDatasets(items);
      setDataset(items[0] ?? null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not load project datasets.');
    } finally {
      setBusy(false);
    }
  }

  async function createDataset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!organization || !project) return;
    clearMessages();
    setBusy(true);
    try {
      const created = await request<Dataset>(`/v1/projects/${project.id}/datasets`, token, organization.id, {
        method: 'POST',
        body: JSON.stringify({ name: datasetName.trim(), source_type: 'FILE' }),
      });
      setDatasets((current) => [created, ...current]);
      setDataset(created);
      setDatasetName('');
      setNotice('Dataset created. Choose a CSV or Parquet file to create version 1.');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Dataset creation failed.');
    } finally {
      setBusy(false);
    }
  }

  async function uploadVersion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!organization || !project || !dataset || !file) return;
    clearMessages();
    setBusy(true);
    setBusyAction('upload');
    const form = new FormData();
    form.append('file', file);
    try {
      const created = await request<DatasetVersion>(
        `${dataPath}/versions`,
        token,
        organization.id,
        { method: 'POST', body: form },
      );
      setVersions((current) => [created, ...current]);
      setVersion(created);
      setProfile(null);
      setQuality(null);
      setCausal(null);
      setFile(null);
      setNotice(`Version ${created.version} uploaded. It contains ${created.row_count ?? 'an unknown number of'} rows across ${created.column_count ?? 'an unknown number of'} columns.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The upload failed.');
    } finally {
      setBusy(false);
      setBusyAction('');
    }
  }

  async function runAnalysis(kind: 'profile' | 'quality' | 'causal-safety') {
    if (!organization || !version) return;
    clearMessages();
    setBusyAction(kind);
    try {
      const result = await request<Profile | Report>(
        `${dataPath}/versions/${version.id}/${kind}`,
        token,
        organization.id,
        { method: 'POST' },
      );
      if (kind === 'profile') setProfile(result as Profile);
      if (kind === 'quality') setQuality(result as Report);
      if (kind === 'causal-safety') setCausal(result as Report);
      const label = kind === 'causal-safety' ? 'Temporal safety review' : kind === 'quality' ? 'Data quality check' : 'Dataset profile';
      setNotice(`${label} completed and saved for version ${version.version}.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The analysis could not be completed.');
    } finally {
      setBusyAction('');
    }
  }

  async function signOut() {
    sessionStorage.removeItem(TOKEN_KEY);
    setToken('');
    setOrganizations([]);
    setOrganization(null);
    setProjects([]);
    setProject(null);
    setDatasets([]);
    setDataset(null);
    clearMessages();
  }

  if (!authReady) {
    return <div className="boot-screen"><span className="signal-mark">T</span><p>Restoring your workspace…</p></div>;
  }

  if (!signedIn) {
    return (
      <div className="auth-page">
        <div className="auth-rail">
          <Brand />
          <div className="auth-rail-copy">
            <h1>Trust the timeline.<br /><span>Inspect the evidence.</span></h1>
            <p>Profile time-series data, check quality, and surface temporal leakage risks before they reach a forecasting workflow.</p>
            <div className="auth-checks">
              <span><i className="dot dot-blue" />Versioned dataset evidence</span>
              <span><i className="dot dot-green" />Repeatable quality checks</span>
              <span><i className="dot dot-amber" />Heuristics clearly marked for review</span>
            </div>
          </div>
          <p className="auth-footnote">No forecast is called safe by default. Every result stays tied to the data it inspected.</p>
        </div>
        <main className="auth-panel">
          <div className="auth-form-wrap">
            <div className="auth-mobile-brand"><Brand /></div>
            <h2>Sign in to continue</h2>
            <p className="subtle">New here? Submitting a new email creates your account.</p>
            {error && <Notice tone="error">{error}</Notice>}
            <form onSubmit={handleLogin} className="form-stack">
              <label>Email address<input type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@team.com" /></label>
              <label>Password<input type="password" autoComplete="current-password" required minLength={1} value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Enter your password" /></label>
              <button className="button button-primary button-wide" type="submit" disabled={busy}>{busy ? 'Checking credentials…' : 'Continue to workspace'}<span aria-hidden="true">→</span></button>
            </form>
            <p className="auth-secure">Your session is stored for this browser tab and expires automatically.</p>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Brand />
        <div className="workspace-switch">
          <span className="section-label">WORKSPACE</span>
          {organizations.length > 0 ? (
            <select aria-label="Select workspace" value={organization?.id ?? ''} onChange={(event) => void changeOrganization(event.target.value)}>
              <option value="">Choose a workspace</option>
              {organizations.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          ) : <p className="empty-select">Set up your first workspace</p>}
        </div>
        <nav className="side-nav" aria-label="Workspace navigation">
          <span className="section-label">WORKBENCH</span>
          <a className="nav-link active" href="#overview"><span className="nav-glyph">⌂</span>Overview</a>
          <a className="nav-link" href="#datasets"><span className="nav-glyph">▤</span>Datasets<span className="nav-count">{datasets.length}</span></a>
          <a className="nav-link" href="#analysis"><span className="nav-glyph">⌁</span>Analysis</a>
        </nav>
        <div className="sidebar-bottom">
          <div className="service-mini">
            <span className={`status-light ${health?.status === 'ok' ? 'is-live' : 'is-warning'}`} />
            <span>{health?.status === 'ok' ? 'Services operational' : 'Service attention'}</span>
            <button type="button" aria-label="Refresh service status" title="Refresh service status" onClick={() => void loadHealth()}>↻</button>
          </div>
          <button className="profile-button" type="button" onClick={() => void signOut()}>
            <span className="avatar">{email.slice(0, 1).toUpperCase() || 'U'}</span>
            <span className="profile-copy"><strong>{email || 'Signed-in user'}</strong><small>Sign out</small></span>
            <span className="profile-arrow">↗</span>
          </button>
        </div>
      </aside>

      <main className="main-panel" id="overview">
        <header className="topbar">
          <div className="breadcrumbs"><span>Workbench</span><b>/</b><strong>{project?.name ?? organization?.name ?? 'Workspace setup'}</strong></div>
          <div className="topbar-right"><ServiceBadge health={health} /><span className="header-date">{today}</span></div>
        </header>

        <div className="page-content">
          {error && <Notice tone="error">{error}</Notice>}
          {notice && <Notice tone="success" onDismiss={() => setNotice('')}>{notice}</Notice>}

          {!organization && organizations.length > 0 ? (
            <section className="setup-panel">
              <h1>Choose where to work.</h1>
              <p>Select one of your existing workspaces from the navigation to load its projects and datasets.</p>
            </section>
          ) : !organization ? (
            <section className="setup-panel">
              <div className="setup-index">01 / WORKSPACE</div>
              <h1>Give your work a home.</h1>
              <p>Create an organization workspace to keep projects, datasets, and validation evidence together.</p>
              <form className="inline-create" onSubmit={createWorkspace}>
                <label htmlFor="workspace-name">Workspace name</label>
                <div className="input-action"><input id="workspace-name" required maxLength={120} value={workspaceName} onChange={(event) => setWorkspaceName(event.target.value)} placeholder="e.g. Forecasting research" /><button className="button button-primary" disabled={busy}>Create workspace <span aria-hidden="true">→</span></button></div>
              </form>
            </section>
          ) : (
            <>
              <section className="page-heading">
                <div>
                  <h1>Know what’s in your data before you forecast.</h1>
                  <p className="page-intro">Inspect the dataset, validate its shape, and review temporal leakage signals before using it in a forecasting workflow.</p>
                </div>
                <div className="heading-stamp"><span>ACTIVE WORKSPACE</span><strong>{organization.name}</strong><small>{project?.name ?? 'No project selected'}</small></div>
              </section>

              <section className="service-strip" aria-label="Service status">
                {Object.entries(health?.services ?? { api: { status: 'checking' }, database: { status: 'checking' }, storage: { status: 'checking' } }).map(([name, service]) => (
                  <div className="service-cell" key={name}>
                    <span className={`status-light ${service.status === 'ok' ? 'is-live' : service.status === 'checking' ? 'is-checking' : 'is-warning'}`} />
                    <span className="service-name">{name === 'api' ? 'API' : name === 'database' ? 'Database' : 'Artifact storage'}</span>
                    <strong>{service.status === 'ok' ? 'Available' : service.status === 'checking' ? 'Checking' : service.status === 'unavailable' ? 'Unavailable' : 'Attention'}</strong>
                    {service.persistence === 'ephemeral' && <small>Ephemeral</small>}
                  </div>
                ))}
                {health?.status === 'degraded' && <p className="service-note">Production persistence is not fully configured. Results may not survive a serverless restart.</p>}
              </section>

              <section className="flow-toolbar" aria-label="Project and dataset selection">
                <label>Project<select value={project?.id ?? ''} onChange={(event) => void changeProject(event.target.value)} disabled={!projects.length || busy}><option value="">Select a project</option>{projects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
                <label>Dataset<select value={dataset?.id ?? ''} onChange={(event) => { setDataset(datasets.find((item) => item.id === event.target.value) ?? null); setVersions([]); setVersion(null); setProfile(null); setQuality(null); setCausal(null); }} disabled={!datasets.length || busy}><option value="">Select a dataset</option>{datasets.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
                <label>Version<select value={version?.id ?? ''} onChange={(event) => setVersion(versions.find((item) => item.id === event.target.value) ?? null)} disabled={!versions.length || busy}><option value="">Latest available</option>{versions.map((item) => <option key={item.id} value={item.id}>Version {item.version} · {item.row_count ?? '?'} rows</option>)}</select></label>
              </section>

              <div className="workbench-grid">
                <div className="workbench-primary">
                  {!projects.length ? (
                    <section className="empty-work">
                      <div className="empty-mark">+</div><h2>Start with a project</h2>
                      <p>Projects keep dataset versions and their analysis results grouped by workflow.</p>
                      <form className="inline-create compact" onSubmit={createProject}><label htmlFor="project-name">Project name</label><div className="input-action"><input id="project-name" required maxLength={120} value={projectName} onChange={(event) => setProjectName(event.target.value)} placeholder="e.g. Demand forecast validation" /><button className="button button-primary" disabled={busy}>Create project <span aria-hidden="true">→</span></button></div></form>
                    </section>
                  ) : !datasets.length ? (
                    <section className="empty-work" id="datasets">
                      <div className="empty-mark">↗</div><h2>Bring in a dataset.</h2>
                      <p>Create a dataset record first, then upload a CSV or Parquet version. Each upload stays traceable.</p>
                      <form className="inline-create compact" onSubmit={createDataset}><label htmlFor="dataset-name">Dataset name</label><div className="input-action"><input id="dataset-name" required maxLength={120} value={datasetName} onChange={(event) => setDatasetName(event.target.value)} placeholder="e.g. Daily demand by region" /><button className="button button-primary" disabled={busy}>Create dataset <span aria-hidden="true">→</span></button></div></form>
                    </section>
                  ) : (
                    <>
                      <section className="dataset-section" id="datasets">
                        <div className="section-heading"><div><h2>{dataset?.name ?? 'Choose a dataset'}</h2><p>{dataset?.description || 'Versioned source data for repeatable inspection.'}</p></div><span className="dataset-count">{versions.length} {versions.length === 1 ? 'version' : 'versions'}</span></div>
                        {version ? (
                          <div className="version-summary">
                            <div className="version-token">V{version.version.toString().padStart(2, '0')}</div>
                            <div className="version-details"><strong>{version.row_count?.toLocaleString() ?? '—'} rows <span>·</span> {version.column_count ?? '—'} columns</strong><small>Uploaded {formatDate(version.created_at)}</small></div>
                            <div className="hash-detail"><span>CONTENT HASH</span><code title={version.content_hash}>{version.content_hash.slice(0, 12)}…</code></div>
                          </div>
                        ) : <div className="empty-version">No versions yet. Upload a time-series CSV or Parquet file below.</div>}
                        {version && <div className="analysis-actions" id="analysis">
                          <button className="analysis-action" type="button" disabled={Boolean(busyAction)} onClick={() => void runAnalysis('profile')}><span className="action-index">01</span><span><strong>Profile dataset</strong><small>Schema, nulls, ranges, temporal coverage</small></span><span className="action-arrow">{busyAction === 'profile' ? '…' : '→'}</span></button>
                          <button className="analysis-action" type="button" disabled={Boolean(busyAction)} onClick={() => void runAnalysis('quality')}><span className="action-index">02</span><span><strong>Check data quality</strong><small>Missing values, duplicates, gaps, constraints</small></span><span className="action-arrow">{busyAction === 'quality' ? '…' : '→'}</span></button>
                          <button className="analysis-action" type="button" disabled={Boolean(busyAction)} onClick={() => void runAnalysis('causal-safety')}><span className="action-index">03</span><span><strong>Review temporal safety</strong><small>Leakage and look-ahead risk signals</small></span><span className="action-arrow">{busyAction === 'causal-safety' ? '…' : '→'}</span></button>
                        </div>}
                        <form className="upload-row" onSubmit={uploadVersion}>
                          <label className="file-picker"><span>{file ? file.name : 'Choose CSV or Parquet file'}</span><input type="file" accept=".csv,.parquet" onChange={(event) => setFile(event.target.files?.[0] ?? null)} /></label>
                          <button className="button button-secondary" type="submit" disabled={!file || busy}>{busyAction === 'upload' ? 'Uploading…' : 'Upload new version'}</button>
                        </form>
                      </section>
                      <Results profile={profile} quality={quality} causal={causal} />
                    </>
                  )}
                </div>
                <aside className="workbench-aside">
                  <section className="aside-section"><p className="section-label">PROJECTS</p><h3>Organize your work</h3>
                    {projects.length > 0 && <div className="project-list">{projects.map((item) => <button type="button" key={item.id} className={`project-row ${item.id === project?.id ? 'selected' : ''}`} onClick={() => void changeProject(item.id)}><span className="project-glyph">⌗</span><span><strong>{item.name}</strong><small>{item.description || item.slug}</small></span><span className="row-chevron">›</span></button>)}</div>}
                    <form className="create-mini" onSubmit={createProject}><label htmlFor="project-name-side">New project</label><div><input id="project-name-side" required maxLength={120} value={projectName} onChange={(event) => setProjectName(event.target.value)} placeholder="Project name" /><button type="submit" disabled={busy} aria-label="Create project">+</button></div></form>
                  </section>
                  <section className="aside-section guidance"><p className="section-label">READ THE RESULT</p><h3>Evidence before verdict.</h3><p>Exact structural violations are separated from statistical heuristics. A heuristic warning is a review signal—not proof that data leaked.</p><a href="#analysis">Review analyses <span aria-hidden="true">↗</span></a></section>
                  <section className="aside-section workspace-info"><p className="section-label">CURRENT SCOPE</p><dl><dt>Workspace</dt><dd>{organization.name}</dd><dt>Project</dt><dd>{project?.name ?? 'Not selected'}</dd><dt>Dataset</dt><dd>{dataset?.name ?? 'Not selected'}</dd><dt>Version</dt><dd>{version ? `v${version.version}` : 'Not uploaded'}</dd></dl></section>
                </aside>
              </div>
            </>
          )}
        </div>
        <footer className="page-footer"><span>TEMPORAL INTELLIGENCE</span><span>Analysis describes the uploaded data; it does not guarantee forecast accuracy.</span></footer>
      </main>
    </div>
  );
}

function Brand() {
  return <div className="brand-lockup"><span className="brand-symbol" aria-hidden="true"><i /><i /><i /></span><span className="brand-name">temporal<span> / </span>intelligence<small>DATA WORKBENCH</small></span></div>;
}

function Notice({ children, tone, onDismiss }: { children: ReactNode; tone: 'error' | 'success'; onDismiss?: () => void }) {
  return <div className={`notice notice-${tone}`} role={tone === 'error' ? 'alert' : 'status'}>{children}{onDismiss && <button type="button" onClick={onDismiss} aria-label="Dismiss message">×</button>}</div>;
}

function ServiceBadge({ health }: { health: ServiceHealth | null }) {
  const ok = health?.status === 'ok';
  return <span className={`service-badge ${ok ? 'badge-ok' : 'badge-warning'}`}><i className="status-light" />{ok ? 'All services responding' : health?.status === 'degraded' ? 'Persistence needs attention' : 'Checking services'}</span>;
}

function Results({ profile, quality, causal }: { profile: Profile | null; quality: Report | null; causal: Report | null }) {
  const temporal = profile?.schema_summary?.temporal_statistics;
  const columns = Object.entries(profile?.schema_summary?.general_statistics?.columns ?? {});
  const hasResults = profile || quality || causal;
  if (!hasResults) return <section className="results-empty"><span className="empty-rail" /><p>Results appear here with the evidence attached.</p></section>;

  return (
    <section className="results-section">
      <div className="section-heading"><div><h2>Evidence &amp; findings</h2><p>Reports are saved against the selected dataset version.</p></div></div>
      {profile && <div className="profile-report">
        <div className="report-title"><span className="report-mark mark-blue">P</span><div><h3>Dataset profile</h3><small>Structure and temporal coverage</small></div><span className="report-date">{formatDate(profile.created_at)}</span></div>
        <div className="profile-metrics"><div><strong>{profile.row_count?.toLocaleString() ?? '—'}</strong><small>rows</small></div><div><strong>{profile.column_count ?? '—'}</strong><small>columns</small></div><div><strong>{temporal?.series_count ?? '—'}</strong><small>series</small></div><div><strong>{temporal?.gap_count_sample ?? '—'}</strong><small>sampled gaps</small></div></div>
        {columns.length > 0 && <div className="column-table"><div className="column-head"><span>FIELD</span><span>TYPE</span><span>NULLS</span><span>UNIQUE</span></div>{columns.map(([name, item]) => <div className="column-row" key={name}><strong>{name}</strong><span>{item.type ?? '—'}</span><span>{item.null_percentage ?? 0}%</span><span>{item.unique_count ?? '—'}</span></div>)}</div>}
      </div>}
      {quality && <ReportPanel title="Data quality" letter="Q" report={quality} detail={`${quality.error_count ?? 0} errors · ${quality.warning_count ?? 0} warnings`} />}
      {causal && <ReportPanel title="Temporal safety" letter="T" report={causal} detail={`${causal.unsafe_count ?? 0} structural risks · ${causal.warning_count ?? 0} review signals`} />
      }
    </section>
  );
}

function ReportPanel({ title, letter, report, detail }: { title: string; letter: string; report: Report; detail: string }) {
  const findings = report.findings ?? [];
  return <details className="report-panel" open><summary><span className="report-mark mark-amber">{letter}</span><span className="report-heading"><strong>{title}</strong><small>{detail}</small></span><span className={`verdict verdict-${report.verdict.toLowerCase().replaceAll('_', '-')}`}>{report.verdict.replaceAll('_', ' ')}</span><span className="finding-total">{report.total_findings} findings</span><span className="details-toggle">⌄</span></summary>
    {findings.length > 0 ? <div className="findings-list">{findings.map((finding, index) => <article className="finding" key={`${finding.rule_id}-${index}`}><div className="finding-topline"><span className={`severity severity-${finding.severity.toLowerCase()}`}>{finding.severity}</span><code>{finding.rule_id}</code>{finding.column && <span className="field-tag">{finding.column}</span>}</div><p>{finding.message}</p>{finding.evidence?.description && <blockquote>{finding.evidence.description}</blockquote>}{finding.evidence?.statistic_value !== undefined && <small className="finding-stat">{finding.evidence.statistic_name?.replaceAll('_', ' ')}: {finding.evidence.statistic_value}{finding.evidence.threshold !== undefined ? ` · threshold ${finding.evidence.threshold}` : ''}</small>}<div className="finding-meta"><span>{finding.detection_type ?? 'RULE'}</span>{finding.confidence !== undefined && <span>{Math.round(finding.confidence * 100)}% confidence</span>}{finding.status && <span>{finding.status.replaceAll('_', ' ')}</span>}</div></article>)}</div> : <div className="no-findings">No findings from this check. This means no configured rule triggered; it is not a guarantee of forecast performance.</div>}
    <small className="report-timestamp">Saved report · {formatDate(report.created_at)}</small>
  </details>;
}

export default App;
