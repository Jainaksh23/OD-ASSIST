/* ─── OD Assist — Admin JavaScript ──────────────────────────────────────────
   JWT stored in sessionStorage (cleared on tab close).
   Polls /admin/sources every 5 s while dashboard is visible.
   All fetch errors surface as toasts — no raw alert() calls.
   ─────────────────────────────────────────────────────────────────────────── */

'use strict';

const API = window.location.origin;
let token = sessionStorage.getItem('odAdminToken');
let pollInterval = null;
let pendingDeleteId = null;
let modalAction    = null;   // 'delete' | 'retry-all'
let currentSourceFilter = 'all';
let cachedSources = [];

// ── DOM refs ──────────────────────────────────────────────────────────────────
const loginScreen    = document.getElementById('login-screen');
const dashboard      = document.getElementById('dashboard');
const loginForm      = document.getElementById('login-form');
const loginError     = document.getElementById('login-error');
const loginBtn       = document.getElementById('login-btn');
const loginBtnLabel  = document.getElementById('login-btn-label');
const loginSpinner   = document.getElementById('login-spinner');
const logoutBtn      = document.getElementById('logout-btn');
const topbarUser     = document.getElementById('topbar-user');

const dropzone       = document.getElementById('dropzone');
const pdfFileInput   = document.getElementById('pdf-file-input');
const pdfFilename    = document.getElementById('pdf-filename');
const pdfSubmit      = document.getElementById('pdf-submit');
const pdfTitle       = document.getElementById('pdf-title');
const pdfBtnLabel    = document.getElementById('pdf-btn-label');
const pdfSpinner     = document.getElementById('pdf-spinner');

const driveUrl       = document.getElementById('drive-url');
const driveTitle     = document.getElementById('drive-title');
const driveType      = document.getElementById('drive-type');
const driveSubmit    = document.getElementById('drive-submit');
const driveBtnLabel  = document.getElementById('drive-btn-label');
const driveSpinner   = document.getElementById('drive-spinner');

const textTitle      = document.getElementById('text-title');
const textContent    = document.getElementById('text-content');
const textSubmit     = document.getElementById('text-submit');
const textBtnLabel   = document.getElementById('text-btn-label');
const textSpinner    = document.getElementById('text-spinner');

const bulkContent    = document.getElementById('bulk-content');
const bulkSubmit     = document.getElementById('bulk-submit');
const bulkBtnLabel   = document.getElementById('bulk-btn-label');
const bulkSpinner    = document.getElementById('bulk-spinner');

const createUserForm = document.getElementById('create-user-form');
const newUsername    = document.getElementById('new-username');
const newPassword    = document.getElementById('new-password');
const newRole        = document.getElementById('new-role');
const userSubmit     = document.getElementById('user-submit');
const userBtnLabel   = document.getElementById('user-btn-label');
const userSpinner    = document.getElementById('user-spinner');
const usersLoading   = document.getElementById('users-loading');
const usersList      = document.getElementById('users-list');

const insightsGapsLoading = document.getElementById('insights-gaps-loading');
const insightsGapsList = document.getElementById('insights-gaps-list');
const insightsRareLoading = document.getElementById('insights-rare-loading');
const insightsRareList = document.getElementById('insights-rare-list');
const refreshInsightsBtn = document.getElementById('refresh-insights-btn');
const clearCacheBtn = document.getElementById('clear-cache-btn');
const cacheLoading = document.getElementById('cache-loading');
const cacheEmpty = document.getElementById('cache-empty');
const cacheTableContainer = document.getElementById('cache-table-container');
const cacheList = document.getElementById('cache-list');

const ingestBanner   = document.getElementById('ingest-banner');
const sourcesLoading = document.getElementById('sources-loading');
const sourcesEmpty   = document.getElementById('sources-empty');
const sourcesGrid    = document.getElementById('sources-grid');
const sidebarSources = document.getElementById('sidebar-sources');
const statTotal      = document.getElementById('stat-total');
const statCompleted  = document.getElementById('stat-completed');
const themeToggle    = document.getElementById('theme-toggle');

const confirmModal   = document.getElementById('confirm-modal');
const modalTitle     = document.getElementById('modal-title');
const modalCancel    = document.getElementById('modal-cancel');
const modalConfirm   = document.getElementById('modal-confirm');
const retryAllBtn    = document.getElementById('retry-all-btn');
const retryAllCount  = document.getElementById('retry-all-count');

// ── Init ──────────────────────────────────────────────────────────────────────
if (token) showDashboard();

// ── Auth ──────────────────────────────────────────────────────────────────────
loginForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const username = document.getElementById('lg-username').value.trim();
  const password = document.getElementById('lg-password').value;

  setLoading(loginBtn, loginBtnLabel, loginSpinner, true, 'Signing in…');
  loginError.classList.add('hidden');

  try {
    const res = await fetch(`${API}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json();

    if (!res.ok) {
      showLoginError(data.detail || 'Invalid credentials');
      return;
    }
    if (data.role !== 'admin') {
      showLoginError('This account does not have admin access.');
      return;
    }

    token = data.access_token;
    sessionStorage.setItem('odAdminToken', token);
    topbarUser.textContent = username;
    showDashboard();
  } catch {
    showLoginError('Connection error — is the server running?');
  } finally {
    setLoading(loginBtn, loginBtnLabel, loginSpinner, false, 'Sign In');
  }
});

logoutBtn.addEventListener('click', () => {
  sessionStorage.removeItem('odAdminToken');
  token = null;
  clearInterval(pollInterval);
  pollInterval = null;
  dashboard.classList.add('hidden');
  loginScreen.classList.remove('hidden');
  loginForm.reset();
});

function showLoginError(msg) {
  loginError.textContent = msg;
  loginError.classList.remove('hidden');
}

function showDashboard() {
  loginScreen.classList.add('hidden');
  dashboard.classList.remove('hidden');
  const stored = sessionStorage.getItem('odAdminToken');
  if (stored) {
    try {
      const payload = JSON.parse(atob(stored.split('.')[1]));
      topbarUser.textContent = payload.sub || 'odadmin';
    } catch { topbarUser.textContent = 'odadmin'; }
  }
  fetchSources();
  fetchUsers();
  loadInsights();
  pollInterval = setInterval(fetchSources, 5000);
}

// ── Tab switching ─────────────────────────────────────────────────────────────
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => {
      b.classList.remove('active'); b.setAttribute('aria-selected', 'false');
    });
    document.querySelectorAll('.tab-panel').forEach(p => {
      p.classList.remove('active');
      p.classList.add('hidden');
    });
    btn.classList.add('active'); btn.setAttribute('aria-selected', 'true');
    const targetPanel = document.getElementById(`tab-${btn.dataset.tab}`);
    targetPanel.classList.add('active');
    targetPanel.classList.remove('hidden');
    hideBanner();
  });
});

// ── Filter switching ──────────────────────────────────────────────────────────
document.querySelectorAll('.filter-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.filter-btn').forEach(b => {
      b.classList.remove('active'); b.setAttribute('aria-selected', 'false');
    });
    btn.classList.add('active'); btn.setAttribute('aria-selected', 'true');
    currentSourceFilter = btn.dataset.filter;
    if (cachedSources) {
      renderSources(cachedSources);
    }
  });
});

// ── Dropzone ──────────────────────────────────────────────────────────────────
dropzone.addEventListener('click', () => pdfFileInput.click());
dropzone.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') pdfFileInput.click(); });

dropzone.addEventListener('dragover', (e) => { e.preventDefault(); dropzone.classList.add('drag-over'); });
dropzone.addEventListener('dragleave', () => dropzone.classList.remove('drag-over'));
dropzone.addEventListener('drop', (e) => {
  e.preventDefault(); dropzone.classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (file) setSelectedFile(file);
});

pdfFileInput.addEventListener('change', () => {
  if (pdfFileInput.files[0]) setSelectedFile(pdfFileInput.files[0]);
});

function setSelectedFile(file) {
  if (!file.name.toLowerCase().endsWith('.pdf')) {
    showBanner('Only PDF files are accepted.', 'error'); return;
  }
  pdfFilename.textContent = `📄 ${file.name}`;
  pdfFilename.classList.remove('hidden');
  pdfSubmit.disabled = false;
}

// ── PDF ingest ────────────────────────────────────────────────────────────────
pdfSubmit.addEventListener('click', async () => {
  const file = pdfFileInput.files[0];
  if (!file) return;

  const fd = new FormData();
  fd.append('file', file);
  fd.append('title', pdfTitle.value.trim());

  setLoading(pdfSubmit, pdfBtnLabel, pdfSpinner, true, 'Uploading…');
  hideBanner();

  const ok = await doIngest(`${API}/admin/upload_pdf`, { method: 'POST', headers: auth(), body: fd });
  setLoading(pdfSubmit, pdfBtnLabel, pdfSpinner, false, 'Ingest PDF');
  if (ok) {
    pdfTitle.value = '';
    pdfFileInput.value = '';
    pdfFilename.classList.add('hidden');
    pdfSubmit.disabled = true;
    showBanner('PDF queued for processing — status will update below.', 'success');
  }
});

// ── Drive ingest ──────────────────────────────────────────────────────────────
driveSubmit.addEventListener('click', async () => {
  const url = driveUrl.value.trim();
  if (!url) { showBanner('Please enter a Drive share link.', 'error'); return; }

  setLoading(driveSubmit, driveBtnLabel, driveSpinner, true, 'Queuing…');
  hideBanner();

  const ok = await doIngest(`${API}/admin/ingest`, {
    method: 'POST',
    headers: { ...auth(), 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title: driveTitle.value.trim(),
      source_type: driveType.value,
      source_url: url,
    }),
  });
  setLoading(driveSubmit, driveBtnLabel, driveSpinner, false, 'Ingest Drive Link');
  if (ok) { driveUrl.value = ''; driveTitle.value = ''; showBanner('Drive link queued for processing.', 'success'); }
});

// ── Raw text ingest ───────────────────────────────────────────────────────────
textSubmit.addEventListener('click', async () => {
  const text = textContent.value.trim();
  if (!text) { showBanner('Please paste some text content.', 'error'); return; }

  setLoading(textSubmit, textBtnLabel, textSpinner, true, 'Queuing…');
  hideBanner();

  const ok = await doIngest(`${API}/admin/ingest`, {
    method: 'POST',
    headers: { ...auth(), 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title: textTitle.value.trim(),
      source_type: 'raw_text',
      source_url: text,   // orchestrator reads text from source_url for raw_text type
    }),
  });
  setLoading(textSubmit, textBtnLabel, textSpinner, false, 'Ingest Text');
  if (ok) { textContent.value = ''; textTitle.value = ''; showBanner('Text queued for processing.', 'success'); }
});

// ── Bulk ingest ───────────────────────────────────────────────────────────────
bulkSubmit.addEventListener('click', async () => {
  const text = bulkContent.value.trim();
  if (!text) { showBanner('Please paste bulk content.', 'error'); return; }

  setLoading(bulkSubmit, bulkBtnLabel, bulkSpinner, true, 'Queuing…');
  hideBanner();

  const ok = await doIngest(`${API}/admin/bulk_ingest`, {
    method: 'POST',
    headers: { ...auth(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ bulk_text: text }),
  });
  setLoading(bulkSubmit, bulkBtnLabel, bulkSpinner, false, 'Ingest Bulk Data');
  if (ok) {
    bulkContent.value = '';
    if (ok.skipped && ok.skipped.length > 0) {
      showBanner(`Queued successfully, but skipped ${ok.skipped.length} items (Folder links are not supported).`, 'error');
    } else {
      showBanner('Bulk data queued for processing.', 'success');
    }
  }
});

// ── Ingest helper ─────────────────────────────────────────────────────────────
async function doIngest(url, options) {
  try {
    const res = await fetch(url, options);
    if (res.status === 401) { handleExpiredToken(); return false; }
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      showBanner(err.detail || 'Ingest failed. Check server logs.', 'error');
      return false;
    }
    fetchSources();
    return await res.json().catch(() => true);
  } catch {
    showBanner('Network error — server unreachable.', 'error');
    return false;
  }
}

// ── Sources table ─────────────────────────────────────────────────────────────
async function fetchSources() {
  if (!token) return;
  try {
    const res = await fetch(`${API}/admin/sources`, { headers: auth() });
    if (res.status === 401) { handleExpiredToken(); return; }
    if (!res.ok) return;
    const sources = await res.json();
    cachedSources = sources;
    renderSources(sources);
  } catch { /* silent on poll errors */ }
}

function renderSources(sources) {
  sourcesLoading.classList.add('hidden');

  let completedCount = 0;
  let failedCount = 0;
  sources.forEach(s => {
    if (s.status === 'completed') completedCount++;
    if (s.status === 'failed') failedCount++;
  });
  statTotal.textContent = sources.length;
  statCompleted.textContent = completedCount;

  // Update Retry All Failed button
  retryAllCount.textContent = failedCount;
  if (failedCount > 0) {
    retryAllBtn.classList.remove('hidden');
    retryAllBtn.disabled = false;
  } else {
    retryAllBtn.classList.add('hidden');
  }

  const filteredSources = currentSourceFilter === 'all' 
    ? sources 
    : sources.filter(s => s.status === currentSourceFilter);

  if (!filteredSources || filteredSources.length === 0) {
    sourcesEmpty.textContent = currentSourceFilter === 'all' 
      ? 'No sources yet. Add one above.' 
      : 'No sources in this category.';
    sourcesEmpty.classList.remove('hidden');
    sourcesGrid.classList.add('hidden');
    sidebarSources.innerHTML = '';
    return;
  }

  sourcesEmpty.classList.add('hidden');
  sourcesGrid.classList.remove('hidden');
  sourcesGrid.innerHTML = '';
  sidebarSources.innerHTML = '';

  filteredSources.forEach(s => {
    const date = s.created_at ? new Date(s.created_at).toLocaleString() : '—';
    const typeLabel = { pdf:'PDF', drive_doc:'Drive Doc', drive_video:'Drive Video', raw_text:'Raw Text' }[s.source_type] || s.source_type;
    const stClass   = { processing:'processing', completed:'completed', failed:'failed' }[s.status] || '';

    // Render sidebar item
    const navItem = document.createElement('div');
    navItem.className = 'nav-item';
    navItem.innerHTML = `<span>${esc(s.title || 'Untitled')}</span> <span class="badge">${s.chunk_count ?? 0} chunks</span>`;
    sidebarSources.appendChild(navItem);

    // Render main card
    const card = document.createElement('div');
    card.className = 'source-card';
    if (s.status === 'failed') card.classList.add('failed-card');
    
    let errorHtml = '';
    let retryHtml = '';
    if (s.status === 'failed') {
      errorHtml = `<div class="sc-error-text">${esc(s.error_message || 'Unknown error')}</div>`;
      retryHtml = `<button class="btn-retry" data-id="${s.id}" title="Retry processing">Retry</button>`;
    }

    card.innerHTML = `
      <div class="sc-header">
        <div class="sc-title">${esc(s.title || '—')}</div>
        <button class="btn-row-del" data-id="${s.id}" data-title="${esc(s.title || 'this source')}" title="Delete source">🗑</button>
      </div>
      <div class="sc-type">${esc(typeLabel)}</div>
      ${errorHtml}
      <div class="sc-footer">
        <span class="status-pill ${stClass}">${esc(s.status || '?')}</span>
        ${retryHtml || `<span style="color:var(--text-muted);font-size:.75rem">${date}</span>`}
      </div>
    `;
    sourcesGrid.appendChild(card);

    // 3D Tilt Effect
    card.addEventListener('mousemove', (e) => {
      if (window.innerWidth <= 768) return;
      const rect = card.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const centerX = rect.width / 2;
      const centerY = rect.height / 2;
      const rotateX = ((y - centerY) / centerY) * -4;
      const rotateY = ((x - centerX) / centerX) * 4;
      card.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) scale3d(1.02, 1.02, 1.02)`;
    });
    card.addEventListener('mouseleave', () => {
      card.style.transform = '';
    });
  });

  // Wire delete buttons
  sourcesGrid.querySelectorAll('.btn-row-del').forEach(btn => {
    btn.addEventListener('click', () => openDeleteModal(Number(btn.dataset.id), btn.dataset.title));
  });

  // Wire retry buttons
  sourcesGrid.querySelectorAll('.btn-retry').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.target.disabled = true;
      e.target.textContent = 'Retrying...';
      try {
        const res = await fetch(`${API}/admin/sources/${btn.dataset.id}/retry`, { method: 'POST', headers: auth() });
        if (res.status === 401) { handleExpiredToken(); return; }
        fetchSources();
      } catch {
        toast('Network error.', 'error');
      }
    });
  });
}

// ── Delete modal ──────────────────────────────────────────────────────────────
function openDeleteModal(id, title) {
  pendingDeleteId = id;
  modalAction = 'delete';
  modalTitle.textContent = 'Delete Source?';
  document.getElementById('modal-body').textContent =
    `"${title}" and all its indexed chunks will be permanently removed.`;
  modalConfirm.textContent = 'Delete';
  modalConfirm.className = 'btn-danger';
  confirmModal.classList.remove('hidden');
}

modalCancel.addEventListener('click', () => {
  confirmModal.classList.add('hidden');
  pendingDeleteId = null;
  modalAction = null;
});

confirmModal.addEventListener('click', (e) => {
  if (e.target === confirmModal) { confirmModal.classList.add('hidden'); pendingDeleteId = null; modalAction = null; }
});

modalConfirm.addEventListener('click', async () => {
  confirmModal.classList.add('hidden');

  if (modalAction === 'clear-cache') {
    modalAction = null;
    try {
      const res = await fetch(`${API}/admin/cache/clear`, {
        method: 'POST',
        headers: auth(),
      });
      if (res.status === 401) { handleExpiredToken(); return; }
      if (!res.ok) {
        const data = await res.json();
        toast(data.detail || 'Failed to clear cache', 'error');
        return;
      }
      
      toast('Semantic cache cleared successfully', 'success');
      loadCache();
      if (typeof loadAnalytics === 'function') {
        loadAnalytics();
      }
    } catch {
      toast('Connection error', 'error');
    }
    return;
  }

  if (modalAction === 'retry-all') {
    modalAction = null;
    retryAllBtn.disabled = true;
    retryAllBtn.textContent = '⏳ Retrying…';
    try {
      const res = await fetch(`${API}/admin/sources/retry-all`, { method: 'POST', headers: auth() });
      if (res.status === 401) { handleExpiredToken(); return; }
      if (res.ok) {
        const data = await res.json();
        toast(`${data.queued_count} sources queued for retry.`, 'success');
        fetchSources();
      } else {
        toast('Failed to retry sources.', 'error');
      }
    } catch {
      toast('Network error.', 'error');
    } finally {
      retryAllBtn.textContent = `🔄 Retry All Failed (0)`;
      // fetchSources will update the button properly
    }
    return;
  }

  if (!pendingDeleteId) return;
  const id = pendingDeleteId;
  pendingDeleteId = null;
  modalAction = null;

  try {
    const res = await fetch(`${API}/admin/sources/${id}`, { method: 'DELETE', headers: auth() });
    if (res.status === 401) { handleExpiredToken(); return; }
    if (res.ok) {
      toast('Source deleted successfully.', 'success');
      fetchSources();
    } else {
      toast('Failed to delete source.', 'error');
    }
  } catch { toast('Network error.', 'error'); }
});

// ── Helpers ───────────────────────────────────────────────────────────────────
function auth() { return { 'Authorization': `Bearer ${token}` }; }

function setLoading(btn, label, spinner, loading, text) {
  btn.disabled = loading;
  label.textContent = text;
  spinner.classList.toggle('hidden', !loading);
}

function showBanner(msg, type) {
  ingestBanner.textContent = msg;
  ingestBanner.className = `banner ${type}`;
  ingestBanner.classList.remove('hidden');
}
function hideBanner() {
  ingestBanner.classList.add('hidden');
  ingestBanner.className = 'banner hidden';
}

function toast(msg, type = 'info') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  document.getElementById('toasts').appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

function esc(str) {
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function handleExpiredToken() {
  sessionStorage.removeItem('odAdminToken');
  token = null;
  clearInterval(pollInterval);
  dashboard.classList.add('hidden');
  loginScreen.classList.remove('hidden');
  showLoginError('Session expired — please sign in again.');
}

// Dark mode toggle
themeToggle.addEventListener('click', () => {
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  if (isDark) {
    document.documentElement.removeAttribute('data-theme');
    themeToggle.textContent = '🌙';
  } else {
    document.documentElement.setAttribute('data-theme', 'dark');
    themeToggle.textContent = '☀️';
  }
});

// ── Retry All Failed ──────────────────────────────────────────────────────────
retryAllBtn.addEventListener('click', () => {
  const count = parseInt(retryAllCount.textContent, 10) || 0;
  if (count === 0) return;
  modalAction = 'retry-all';
  pendingDeleteId = null;
  modalTitle.textContent = 'Retry All Failed Sources?';
  document.getElementById('modal-body').textContent =
    `This will re-process ${count} failed source${count !== 1 ? 's' : ''}. Old chunks will be cleared first to prevent duplicates.`;
  modalConfirm.textContent = `Retry ${count} Source${count !== 1 ? 's' : ''}`;
  modalConfirm.className = 'btn-primary';
  confirmModal.classList.remove('hidden');
});

// ── Users Management ──────────────────────────────────────────────────────────
async function fetchUsers() {
  if (!token) return;
  try {
    const res = await fetch(`${API}/admin/users`, { headers: auth() });
    if (res.status === 401) { handleExpiredToken(); return; }
    if (!res.ok) return;
    const users = await res.json();
    
    usersLoading.classList.add('hidden');
    usersList.classList.remove('hidden');
    usersList.innerHTML = '';
    
    users.forEach(u => {
      const item = document.createElement('div');
      item.className = 'nav-item';
      item.innerHTML = `<span>${esc(u.username)}</span> <span class="badge">${esc(u.role)}</span>`;
      usersList.appendChild(item);
    });
  } catch { /* silent on poll errors */ }
}

if (createUserForm) {
  createUserForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = newUsername.value.trim();
    const password = newPassword.value;
    const role = newRole.value;

    setLoading(userSubmit, userBtnLabel, userSpinner, true, 'Creating…');

    try {
      const res = await fetch(`${API}/admin/users`, {
        method: 'POST',
        headers: { ...auth(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password, role }),
      });
      
      if (res.status === 401) { handleExpiredToken(); return; }
      if (!res.ok) {
        const data = await res.json();
        toast(data.detail || 'Failed to create user', 'error');
        return;
      }
      
      toast('User created successfully', 'success');
      createUserForm.reset();
      fetchUsers();
    } catch {
      toast('Connection error', 'error');
    } finally {
      setLoading(userSubmit, userBtnLabel, userSpinner, false, 'Create User');
    }
  });
}

// ── Insights ──────────────────────────────────────────────────────────────────
async function loadInsights() {
  if (!token) return;
  
  if (insightsGapsLoading) {
    insightsGapsLoading.classList.remove('hidden');
    insightsGapsList.classList.add('hidden');
    insightsRareLoading.classList.remove('hidden');
    insightsRareList.classList.add('hidden');
  }
  
  try {
    const res = await fetch(`${API}/admin/insights`, { headers: auth() });
    if (res.status === 401) { handleExpiredToken(); return; }
    if (!res.ok) return;
    
    const data = await res.json();
    
    if (insightsGapsLoading) {
      insightsGapsLoading.classList.add('hidden');
      insightsGapsList.classList.remove('hidden');
      insightsGapsList.innerHTML = '';
      
      if (data.frequent_gaps.length === 0) {
        insightsGapsList.innerHTML = '<div style="color:var(--text-muted);">No frequent gaps found yet.</div>';
      } else {
        data.frequent_gaps.forEach(item => {
          const date = new Date(item.last_asked).toLocaleString();
          const el = document.createElement('div');
          el.className = 'nav-item';
          el.style.flexDirection = 'column';
          el.style.alignItems = 'flex-start';
          el.style.padding = '0.75rem';
          el.style.border = '1px solid var(--border-color)';
          el.innerHTML = `
            <div style="display:flex; justify-content:space-between; width:100%; margin-bottom:0.25rem;">
              <span style="font-weight:600; color:var(--text-color);">${esc(item.query)}</span>
              <span class="badge" style="background:#ff5252; color:white;">${item.count} times</span>
            </div>
            <div style="font-size:0.75rem; color:var(--text-muted);">Last asked: ${date}</div>
          `;
          insightsGapsList.appendChild(el);
        });
      }
      
      insightsRareLoading.classList.add('hidden');
      insightsRareList.classList.remove('hidden');
      insightsRareList.innerHTML = '';
      
      if (data.rare_questions.length === 0) {
        insightsRareList.innerHTML = '<div style="color:var(--text-muted);">No rare questions found yet.</div>';
      } else {
        data.rare_questions.forEach(item => {
          const date = new Date(item.last_asked).toLocaleString();
          const el = document.createElement('div');
          el.className = 'nav-item';
          el.style.flexDirection = 'column';
          el.style.alignItems = 'flex-start';
          el.style.padding = '0.75rem';
          el.style.border = '1px solid var(--border-color)';
          
          let confColor = 'var(--text-muted)';
          if (item.confidence === 'low') confColor = '#ff5252';
          else if (item.confidence === 'medium') confColor = '#ffb300';
          else if (item.confidence === 'high') confColor = '#4caf50';
          
          el.innerHTML = `
            <div style="display:flex; justify-content:space-between; width:100%; margin-bottom:0.25rem;">
              <span style="color:var(--text-color);">${esc(item.query)}</span>
              <span style="font-size:0.75rem; color:${confColor}; border:1px solid ${confColor}; padding:2px 6px; border-radius:10px;">${esc(item.confidence)}</span>
            </div>
            <div style="font-size:0.75rem; color:var(--text-muted);">Asked: ${date}</div>
          `;
          insightsRareList.appendChild(el);
        });
      }
    }
  } catch (err) {
    console.error(err);
    toast('Error loading insights', 'error');
  }
}

if (refreshInsightsBtn) {
  refreshInsightsBtn.addEventListener('click', loadInsights);
}

// ── Semantic Cache Management ──────────────────────────────────────────────────
async function loadCache() {
  if (!token) return;

  if (cacheLoading) {
    cacheLoading.classList.remove('hidden');
    cacheEmpty.classList.add('hidden');
    cacheTableContainer.classList.add('hidden');
  }

  try {
    const res = await fetch(`${API}/admin/cache`, { headers: auth() });
    if (res.status === 401) { handleExpiredToken(); return; }
    if (!res.ok) return;

    const data = await res.json();

    if (cacheLoading) {
      cacheLoading.classList.add('hidden');
      if (data.length === 0) {
        cacheEmpty.classList.remove('hidden');
        cacheTableContainer.classList.add('hidden');
      } else {
        cacheEmpty.classList.add('hidden');
        cacheTableContainer.classList.remove('hidden');
        cacheList.innerHTML = '';

        data.forEach(item => {
          const lastHit = item.last_hit_at ? new Date(item.last_hit_at).toLocaleString() : 'Never';
          const tr = document.createElement('tr');
          tr.style.borderBottom = '1px solid var(--border-color)';
          tr.innerHTML = `
            <td style="padding: 0.75rem 0.5rem; word-break: break-word; font-weight: 500;">${esc(item.query_text)}</td>
            <td style="padding: 0.75rem 0.5rem; color: var(--text-muted); word-break: break-word;">${esc(item.answer_text.substring(0, 150))}${item.answer_text.length > 150 ? '...' : ''}</td>
            <td style="padding: 0.75rem 0.5rem; text-align: center;"><span class="badge" style="background: var(--primary-soft); color: var(--primary-accent); border: 1px solid var(--primary-accent); padding: 2px 6px;">${item.hit_count}</span></td>
            <td style="padding: 0.75rem 0.5rem; font-size: 0.8rem; color: var(--text-muted);">${lastHit}</td>
          `;
          cacheList.appendChild(tr);
        });
      }
    }
  } catch (err) {
    console.error(err);
    toast('Error loading semantic cache', 'error');
  }
}

function openClearCacheModal() {
  modalAction = 'clear-cache';
  modalTitle.textContent = 'Clear Semantic Cache?';
  const modalBody = document.getElementById('modal-body');
  if (modalBody) {
    modalBody.textContent = 'Are you sure you want to clear the entire semantic cache? This will cause all subsequent queries to hit the LLM directly until cached again.';
  }
  modalConfirm.textContent = 'Clear Cache';
  modalConfirm.className = 'btn-danger';
  confirmModal.classList.remove('hidden');
}

if (clearCacheBtn) {
  clearCacheBtn.addEventListener('click', openClearCacheModal);
}

// ── Mobile Menu Toggle ────────────────────────────────────────────────────────
const mobileMenuBtn = document.getElementById('mobile-menu-btn');
const sidebar = document.querySelector('.sidebar');
const sidebarOverlay = document.getElementById('sidebar-overlay');

function openSidebar() {
  if (sidebar) sidebar.classList.add('open');
  if (sidebarOverlay) sidebarOverlay.classList.add('active');
}

function closeSidebar() {
  if (sidebar) sidebar.classList.remove('open');
  if (sidebarOverlay) sidebarOverlay.classList.remove('active');
}

if (mobileMenuBtn && sidebar) {
  mobileMenuBtn.addEventListener('click', () => {
    if (sidebar.classList.contains('open')) {
      closeSidebar();
    } else {
      openSidebar();
    }
  });

  // Close sidebar when overlay is tapped
  if (sidebarOverlay) {
    sidebarOverlay.addEventListener('click', closeSidebar);
  }

  // Close sidebar on outside click
  document.addEventListener('click', (e) => {
    if (window.innerWidth <= 768 && !sidebar.contains(e.target) && e.target !== mobileMenuBtn && e.target !== sidebarOverlay) {
      closeSidebar();
    }
  });
}

// ── Analytics ────────────────────────────────────────────────────────────────
let usageChartInstance = null;
let confidenceChartInstance = null;
let peakTimeChartInstance = null;

function renderChartFallback(id) {
  const canvas = document.getElementById(id);
  if (canvas && canvas.tagName.toLowerCase() === 'canvas') {
    const fallback = document.createElement('div');
    fallback.style.padding = '3rem 1rem';
    fallback.style.textAlign = 'center';
    fallback.style.color = 'var(--text-muted)';
    fallback.style.fontSize = '0.9rem';
    fallback.style.border = '1px dashed var(--border-color)';
    fallback.style.borderRadius = '8px';
    fallback.style.background = 'var(--bg-color)';
    fallback.innerHTML = '📊 Chart rendering unavailable (Chart.js library not loaded)';
    canvas.replaceWith(fallback);
  }
}

async function loadAnalytics() {
  if (!token) return;

  const btn = document.getElementById('refresh-analytics-btn');
  if (btn) btn.textContent = '🔄 Loading...';

  try {
    const res = await fetch(`${API}/admin/analytics`, { headers: auth() });
    if (res.status === 401) { handleExpiredToken(); return; }
    if (!res.ok) return;

    const data = await res.json();

    // 1. Top Stat Cards
    if (document.getElementById('analytics-total')) document.getElementById('analytics-total').textContent = data.top_stats.total_queries;
    if (document.getElementById('analytics-today')) document.getElementById('analytics-today').textContent = data.top_stats.queries_today;
    if (document.getElementById('analytics-week')) document.getElementById('analytics-week').textContent = data.top_stats.queries_this_week;
    if (document.getElementById('analytics-conf')) document.getElementById('analytics-conf').textContent = `${data.top_stats.avg_confidence_rate}%`;

    // 1b. Cache Stats
    if (data.cache_stats) {
      if (document.getElementById('analytics-cache-rate'))
        document.getElementById('analytics-cache-rate').textContent = `${data.cache_stats.hit_rate}%`;
      if (document.getElementById('analytics-cache-time')) {
        const cached = data.cache_stats.avg_cached_time_ms || 0;
        const fresh = data.cache_stats.avg_fresh_time_ms || 0;
        document.getElementById('analytics-cache-time').textContent = `Cached: ${cached}ms | Fresh: ${fresh}ms`;
      }
    }

    // 2. Usage Trend (Last 14 Days)
    const ctxUsage = document.getElementById('usageChart');
    if (ctxUsage) {
      if (typeof Chart === 'undefined') {
        renderChartFallback('usageChart');
      } else {
        if (usageChartInstance) usageChartInstance.destroy();
        const labels = data.usage_trend.map(d => {
          const parts = d.date.split('-');
          return parts.length >= 3 ? `${parts[1]}/${parts[2]}` : d.date;
        });
        const counts = data.usage_trend.map(d => d.count);
        usageChartInstance = new Chart(ctxUsage.getContext('2d'), {
          type: 'bar',
          data: {
            labels: labels,
            datasets: [{
              label: 'Queries',
              data: counts,
              backgroundColor: '#C2410C',
              borderRadius: 4
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: { y: { beginAtZero: true, ticks: { precision: 0 } } }
          }
        });
      }
    }

    // 3. Peak Usage Time
    const ctxPeak = document.getElementById('peakTimeChart');
    if (ctxPeak) {
      if (typeof Chart === 'undefined') {
        renderChartFallback('peakTimeChart');
      } else {
        if (peakTimeChartInstance) peakTimeChartInstance.destroy();
        const hours = Array.from({length: 24}, (_, i) => i);
        const counts = new Array(24).fill(0);
        data.peak_usage_time.forEach(item => {
          if (item.hour >= 0 && item.hour < 24) counts[item.hour] = item.count;
        });
        
        peakTimeChartInstance = new Chart(ctxPeak.getContext('2d'), {
          type: 'bar',
          data: {
            labels: hours.map(h => `${h}:00`),
            datasets: [{
              label: 'Queries',
              data: counts,
              backgroundColor: '#42a5f5',
              borderRadius: 4
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: { y: { beginAtZero: true, ticks: { precision: 0 } } }
          }
        });
      }
    }

    // 4. Confidence Distribution
    const ctxConf = document.getElementById('confidenceChart');
    if (ctxConf) {
      if (typeof Chart === 'undefined') {
        renderChartFallback('confidenceChart');
      } else {
        if (confidenceChartInstance) confidenceChartInstance.destroy();
        const confData = data.confidence_distribution;
        const high = confData.high || 0;
        const medium = confData.medium || 0;
        const low = confData.low || 0;
        confidenceChartInstance = new Chart(ctxConf.getContext('2d'), {
          type: 'doughnut',
          data: {
            labels: ['High', 'Medium', 'Low'],
            datasets: [{
              data: [high, medium, low],
              backgroundColor: ['#4caf50', '#ffb300', '#ff5252'],
              borderWidth: 0
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '70%',
            plugins: { legend: { position: 'bottom' } }
          }
        });
      }
    }

    // 5. Feedback Stats
    const fTotal = data.feedback_stats.total;
    const fPos = data.feedback_stats.up;
    const fNeg = data.feedback_stats.down;
    document.getElementById('feedback-total').textContent = `${fTotal} total feedback`;
    
    if (fTotal > 0) {
      const posPct = Math.round((fPos / fTotal) * 100);
      document.getElementById('feedback-pos-pct').textContent = `${posPct}%`;
      document.getElementById('feedback-pos-bar').style.width = `${posPct}%`;
    } else {
      document.getElementById('feedback-pos-pct').textContent = `0%`;
      document.getElementById('feedback-pos-bar').style.width = `0%`;
    }

    const dislikedList = document.getElementById('disliked-list');
    dislikedList.innerHTML = '';
    if (data.feedback_stats.most_disliked.length === 0) {
      dislikedList.innerHTML = '<li>No negative feedback yet.</li>';
    } else {
      data.feedback_stats.most_disliked.forEach(item => {
        const li = document.createElement('li');
        li.style.marginBottom = '0.5rem';
        li.innerHTML = `👎 <strong>${item.count}</strong> - ${esc(item.query)}`;
        dislikedList.appendChild(li);
      });
    }

    // 6. Top Questions
    const topQList = document.getElementById('top-questions-list');
    topQList.innerHTML = '';
    if (data.top_questions.length === 0) {
      topQList.innerHTML = '<li>No queries found.</li>';
    } else {
      data.top_questions.forEach(item => {
        const li = document.createElement('li');
        li.style.display = 'flex';
        li.style.justifyContent = 'space-between';
        li.style.padding = '0.5rem 0';
        li.style.borderBottom = '1px solid var(--border)';
        li.innerHTML = `<span>${esc(item.query)}</span> <span class="badge" style="background:var(--accent); color:white;">${item.count}</span>`;
        topQList.appendChild(li);
      });
    }

    // 7. Most Cited Sources
    const citedList = document.getElementById('most-cited-list');
    citedList.innerHTML = '';
    if (data.most_cited_sources.length === 0) {
      citedList.innerHTML = '<li>No sources cited yet.</li>';
    } else {
      data.most_cited_sources.forEach(item => {
        const li = document.createElement('li');
        li.style.display = 'flex';
        li.style.justifyContent = 'space-between';
        li.style.padding = '0.5rem 0';
        li.style.borderBottom = '1px solid var(--border)';
        li.innerHTML = `<span><span style="color:var(--text-muted);">#${item.id}</span> ${esc(item.title)}</span> <span class="badge" style="background:#42a5f5; color:white;">${item.count} cites</span>`;
        citedList.appendChild(li);
      });
    }

  } catch (err) {
    console.error(err);
    toast('Error loading analytics', 'error');
  } finally {
    if (btn) btn.textContent = '🔄 Refresh';
  }
}

if (document.getElementById('refresh-analytics-btn')) {
  document.getElementById('refresh-analytics-btn').addEventListener('click', loadAnalytics);
}

// ── View Switching Logic ──────────────────────────────────────────────────────
const navButtons = document.querySelectorAll('.sidebar-nav-btn');
const viewPanels = document.querySelectorAll('.view-panel');
const sidebarStatsSection = document.getElementById('sidebar-stats-section');
const sourcesHeading = document.getElementById('sources-heading');
const sidebarSourcesList = document.getElementById('sidebar-sources');

function switchView(viewName) {
  // Hide all view panels
  viewPanels.forEach(panel => panel.classList.add('hidden'));
  
  // Show target panel
  const targetPanel = document.getElementById(`view-${viewName}`);
  if (targetPanel) {
    targetPanel.classList.remove('hidden');
  }
  
  // Update header title dynamically
  const headerMap = {
    'knowledge': 'Manage Knowledge Base',
    'analytics': 'Analytics Dashboard',
    'insights': 'Insights & Gaps',
    'users': 'Manage Users',
    'cache': 'Semantic Cache',
    'paths': 'System Paths',
    'faqs': 'Manage FAQs'
  };
  const headerTitle = document.getElementById('page-header-title');
  if (headerTitle && headerMap[viewName]) {
    headerTitle.textContent = headerMap[viewName];
  }
  
  // Update active state on nav buttons
  navButtons.forEach(btn => {
    if (btn.getAttribute('data-view') === viewName) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });

  // Sidebar dynamic layout based on active view:
  // Hide sources stats/list on other views to keep it clean
  if (viewName === 'knowledge') {
    if (sidebarStatsSection) sidebarStatsSection.classList.remove('hidden');
    if (sourcesHeading) sourcesHeading.classList.remove('hidden');
    if (sidebarSourcesList) sidebarSourcesList.classList.remove('hidden');
    fetchSources();
  } else {
    if (sidebarStatsSection) sidebarStatsSection.classList.add('hidden');
    if (sourcesHeading) sourcesHeading.classList.add('hidden');
    if (sidebarSourcesList) sidebarSourcesList.classList.add('hidden');
  }

  // Load view-specific data
  if (viewName === 'analytics') {
    loadAnalytics();
  } else if (viewName === 'insights') {
    loadInsights();
  } else if (viewName === 'users') {
    fetchUsers();
  } else if (viewName === 'cache') {
    loadCache();
  } else if (viewName === 'paths') {
    loadSourcesForSelect();
    loadPaths();
  } else if (viewName === 'faqs') {
    loadFaqs();
    loadSuggestedFaqs();
    loadSourcesForFaqSelect();
  }
}

navButtons.forEach(btn => {
  btn.addEventListener('click', () => {
    const viewName = btn.getAttribute('data-view');
    switchView(viewName);
    
    // Close mobile menu if open
    if (window.innerWidth <= 768) {
      closeSidebar();
    }
  });
});

// Hook into showDashboard to set active view on load
const origShowDashboard = showDashboard;
showDashboard = function() {
  origShowDashboard();
  switchView('knowledge');
};


// ── System Paths Section ──────────────────────────────────────────────────────

async function loadSourcesForSelect() {
  const select = document.getElementById('path-sources-select');
  if (!select) return;
  
  if (cachedSources.length === 0) {
    try {
      const res = await fetch(`${API}/admin/sources`, { headers: auth() });
      if (res.ok) {
        cachedSources = await res.json();
      }
    } catch (e) {
      console.error("Error loading sources for path picker:", e);
    }
  }
  
  select.innerHTML = '';
  cachedSources.forEach(src => {
    const opt = document.createElement('option');
    opt.value = src.id;
    opt.textContent = `[#${src.id}] ${src.title || 'Untitled'}`;
    select.appendChild(opt);
  });
}

function addStepInput(value = '') {
  const container = document.getElementById('steps-container');
  if (!container) return;

  const row = document.createElement('div');
  row.className = 'step-input-row';
  row.style.display = 'flex';
  row.style.gap = '0.5rem';
  row.style.alignItems = 'center';

  const input = document.createElement('input');
  input.type = 'text';
  input.className = 'step-label-input';
  input.value = value;
  input.placeholder = `Step ${container.children.length + 1}`;
  input.required = true;
  input.style.flex = '1';
  input.style.padding = '0.4rem 0.6rem';
  input.style.borderRadius = '6px';
  input.style.border = '1px solid var(--border-color)';
  input.style.background = 'var(--bg-color)';
  input.style.color = 'var(--text-main)';
  input.addEventListener('input', renderLivePreview);

  const btnUp = document.createElement('button');
  btnUp.type = 'button';
  btnUp.className = 'btn-ghost';
  btnUp.textContent = '▲';
  btnUp.style.padding = '0.2rem 0.4rem';
  btnUp.addEventListener('click', () => {
    if (row.previousElementSibling) {
      container.insertBefore(row, row.previousElementSibling);
      renderLivePreview();
      updateStepPlaceholders();
    }
  });

  const btnDown = document.createElement('button');
  btnDown.type = 'button';
  btnDown.className = 'btn-ghost';
  btnDown.textContent = '▼';
  btnDown.style.padding = '0.2rem 0.4rem';
  btnDown.addEventListener('click', () => {
    if (row.nextElementSibling) {
      container.insertBefore(row.nextElementSibling, row);
      renderLivePreview();
      updateStepPlaceholders();
    }
  });

  const btnDel = document.createElement('button');
  btnDel.type = 'button';
  btnDel.className = 'btn-ghost';
  btnDel.textContent = '❌';
  btnDel.style.padding = '0.2rem 0.4rem';
  btnDel.addEventListener('click', () => {
    row.remove();
    renderLivePreview();
    updateStepPlaceholders();
  });

  row.appendChild(input);
  row.appendChild(btnUp);
  row.appendChild(btnDown);
  row.appendChild(btnDel);

  container.appendChild(row);
  renderLivePreview();
}

function updateStepPlaceholders() {
  const container = document.getElementById('steps-container');
  if (!container) return;
  Array.from(container.children).forEach((row, idx) => {
    const input = row.querySelector('.step-label-input');
    if (input) input.placeholder = `Step ${idx + 1}`;
  });
}

function renderLivePreview() {
  const previewContainer = document.getElementById('path-live-preview');
  if (!previewContainer) return;

  const container = document.getElementById('steps-container');
  const rows = container ? container.querySelectorAll('.step-label-input') : [];
  const steps = Array.from(rows).map(input => input.value.trim()).filter(val => val !== '');

  if (steps.length === 0) {
    previewContainer.innerHTML = `
      <div style="color: var(--text-muted); font-size: 0.9rem; font-style: italic;">
        Type step labels in the form to see the flow preview.
      </div>
    `;
    return;
  }

  let stepsHtml = steps.map(step => `
    <div class="system-path-step-box" style="
      border: 2px solid var(--primary-accent);
      border-radius: 8px;
      padding: 0.5rem 1rem;
      background: var(--card-bg);
      color: var(--primary-accent);
      font-weight: 700;
      font-size: 0.85rem;
      box-shadow: 0 2px 4px rgba(194, 65, 12, 0.08);
      white-space: nowrap;
    ">
      ${esc(step)}
    </div>
  `).join(`
    <div class="system-path-arrow" style="
      color: var(--primary-accent);
      font-weight: 700;
      font-size: 1.25rem;
      margin: 0 0.25rem;
    ">→</div>
  `);

  previewContainer.innerHTML = `
    <div style="display: flex; align-items: center; justify-content: center; flex-wrap: wrap; gap: 0.5rem; width: 100%;">
      ${stepsHtml}
    </div>
  `;
}

async function loadPaths() {
  if (!token) return;
  
  const loadingEl = document.getElementById('paths-loading');
  const emptyEl = document.getElementById('paths-empty');
  const gridEl = document.getElementById('paths-grid');
  
  if (loadingEl) loadingEl.classList.remove('hidden');
  if (emptyEl) emptyEl.classList.add('hidden');
  if (gridEl) gridEl.classList.add('hidden');

  try {
    const res = await fetch(`${API}/admin/system-paths`, { headers: auth() });
    if (res.status === 401) { handleExpiredToken(); return; }
    if (!res.ok) return;

    const paths = await res.json();
    if (loadingEl) loadingEl.classList.add('hidden');

    if (paths.length === 0) {
      if (emptyEl) emptyEl.classList.remove('hidden');
      if (gridEl) gridEl.innerHTML = '';
      return;
    }

    if (gridEl) {
      gridEl.classList.remove('hidden');
      gridEl.innerHTML = '';

      paths.forEach(path => {
        const card = document.createElement('div');
        card.className = 'card';
        card.style.borderLeft = '4px solid var(--primary-accent)';
        card.style.display = 'flex';
        card.style.flexDirection = 'column';
        card.style.justifyContent = 'space-between';
        card.style.padding = '1.25rem';
        card.style.marginBottom = '0';

        const sortedSteps = path.steps.sort((a, b) => a.step_order - b.step_order);
        const stepsPreview = sortedSteps.map(s => `
          <span style="
            border: 1px solid var(--primary-accent);
            border-radius: 4px;
            padding: 0.2rem 0.5rem;
            font-size: 0.7rem;
            font-weight: 600;
            background: var(--card-bg);
            color: var(--primary-accent);
            white-space: nowrap;
          ">${esc(s.step_label)}</span>
        `).join('<span style="color:var(--primary-accent); font-size:0.75rem;">→</span>');

        const linkedSources = path.sources.map(s => esc(s.title || `Source #${s.id}`)).join(', ') || 'None';

        card.innerHTML = `
          <div>
            <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:0.5rem;">
              <h4 style="margin:0; font-weight:700; color:var(--text-main); font-size:1rem;">${esc(path.title)}</h4>
              <button class="btn-ghost delete-path-btn" style="padding:0.25rem; font-size:0.85rem;" data-id="${path.id}">🗑️</button>
            </div>
            ${path.description ? `<p style="font-size:0.8rem; color:var(--text-muted); margin:0 0 1rem; font-style:italic;">${esc(path.description)}</p>` : ''}
            
            <div style="display:flex; align-items:center; flex-wrap:wrap; gap:0.25rem; margin-bottom:1.25rem; background:rgba(194, 65, 12, 0.03); border: 1px solid var(--border-color); border-radius:6px; padding:0.75rem;">
              ${stepsPreview || '<span style="font-style:italic; font-size:0.75rem; color:var(--text-muted);">No steps defined</span>'}
            </div>
          </div>
          
          <div style="display:flex; justify-content:space-between; align-items:center; border-top:1px solid var(--border-color); padding-top:0.75rem; margin-top:auto;">
            <div style="font-size:0.75rem; color:var(--text-muted); max-width:70%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${linkedSources}">
              🔗 Sources: ${linkedSources}
            </div>
            <button class="btn-ghost edit-path-btn" style="padding:0.25rem 0.5rem; font-size:0.75rem; border:1px solid var(--border-color); border-radius:4px;" data-id="${path.id}">✏️ Edit</button>
          </div>
        `;

        card.querySelector('.edit-path-btn').addEventListener('click', () => {
          editPath(path);
        });

        card.querySelector('.delete-path-btn').addEventListener('click', async (e) => {
          e.stopPropagation();
          if (confirm(`Are you sure you want to delete the system path "${path.title}"?`)) {
            try {
              const delRes = await fetch(`${API}/admin/system-paths/${path.id}`, { method: 'DELETE', headers: auth() });
              if (delRes.status === 401) { handleExpiredToken(); return; }
              if (delRes.ok) {
                toast('System path deleted successfully.', 'success');
                loadPaths();
                resetPathForm();
              } else {
                toast('Failed to delete system path.', 'error');
              }
            } catch {
              toast('Network error.', 'error');
            }
          }
        });

        gridEl.appendChild(card);
      });
    }
  } catch (err) {
    console.error(err);
    if (loadingEl) loadingEl.classList.add('hidden');
    toast('Error loading system paths', 'error');
  }
}

function editPath(path) {
  document.getElementById('path-form-title').textContent = 'Edit System Path';
  document.getElementById('path-id').value = path.id;
  document.getElementById('path-title-input').value = path.title;
  document.getElementById('path-desc-input').value = path.description || '';

  const container = document.getElementById('steps-container');
  if (container) {
    container.innerHTML = '';
    const sorted = path.steps.sort((a, b) => a.step_order - b.step_order);
    sorted.forEach(s => {
      addStepInput(s.step_label);
    });
  }

  const select = document.getElementById('path-sources-select');
  if (select) {
    Array.from(select.options).forEach(opt => opt.selected = false);
    const linkedIds = path.sources.map(s => s.id);
    Array.from(select.options).forEach(opt => {
      if (linkedIds.includes(parseInt(opt.value, 10))) {
        opt.selected = true;
      }
    });
  }

  const cancelBtn = document.getElementById('path-cancel-btn');
  if (cancelBtn) cancelBtn.classList.remove('hidden');
  const submitBtn = document.getElementById('path-submit-btn');
  if (submitBtn) submitBtn.textContent = 'Save Changes';

  document.getElementById('path-form-title').scrollIntoView({ behavior: 'smooth' });
}

function resetPathForm() {
  document.getElementById('path-form-title').textContent = 'Create System Path';
  document.getElementById('path-id').value = '';
  document.getElementById('path-form').reset();

  const container = document.getElementById('steps-container');
  if (container) {
    container.innerHTML = '';
    addStepInput();
  }

  const select = document.getElementById('path-sources-select');
  if (select) {
    Array.from(select.options).forEach(opt => opt.selected = false);
  }

  const cancelBtn = document.getElementById('path-cancel-btn');
  if (cancelBtn) cancelBtn.classList.add('hidden');
  const submitBtn = document.getElementById('path-submit-btn');
  if (submitBtn) submitBtn.textContent = 'Create Path';

  renderLivePreview();
}

// Register Listeners
const addStepBtnEl = document.getElementById('add-step-btn');
if (addStepBtnEl) {
  addStepBtnEl.addEventListener('click', () => addStepInput());
}

const cancelBtnEl = document.getElementById('path-cancel-btn');
if (cancelBtnEl) {
  cancelBtnEl.addEventListener('click', resetPathForm);
}

const pathFormEl = document.getElementById('path-form');
if (pathFormEl) {
  pathFormEl.addEventListener('submit', async (e) => {
    e.preventDefault();

    const pathId = document.getElementById('path-id').value;
    const title = document.getElementById('path-title-input').value.trim();
    const description = document.getElementById('path-desc-input').value.trim();
    
    const stepInputs = document.querySelectorAll('.step-label-input');
    const steps = Array.from(stepInputs).map(input => input.value.trim()).filter(val => val !== '');
    
    if (steps.length === 0) {
      toast('Please add at least one step in the sequence.', 'error');
      return;
    }

    const select = document.getElementById('path-sources-select');
    const sourceIds = Array.from(select.selectedOptions).map(opt => parseInt(opt.value, 10));

    const method = pathId ? 'PUT' : 'POST';
    const endpoint = pathId ? `${API}/admin/system-paths/${pathId}` : `${API}/admin/system-paths`;

    const payload = {
      title,
      description: description || null,
      steps,
      source_ids: sourceIds
    };

    const submitBtn = document.getElementById('path-submit-btn');
    const originalText = submitBtn.textContent;
    submitBtn.disabled = true;
    submitBtn.textContent = 'Saving...';

    try {
      const res = await fetch(endpoint, {
        method,
        headers: { ...auth(), 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (res.status === 401) { handleExpiredToken(); return; }
      if (res.ok) {
        toast(pathId ? 'System path updated successfully.' : 'System path created successfully.', 'success');
        resetPathForm();
        loadPaths();
      } else {
        const data = await res.json().catch(() => ({}));
        toast(data.detail || 'Failed to save system path.', 'error');
      }
    } catch {
      toast('Connection error.', 'error');
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = originalText;
    }
  });
}

// ── FAQs Section ─────────────────────────────────────────────────────────────

async function loadSourcesForFaqSelect() {
  const select = document.getElementById('faq-source-select');
  if (!select) return;
  if (cachedSources.length === 0) {
    try {
      const res = await fetch(`${API}/admin/sources`, { headers: auth() });
      if (res.ok) cachedSources = await res.json();
    } catch (e) {
      console.error("Error loading sources:", e);
    }
  }
  select.innerHTML = '<option value="">None</option>';
  cachedSources.forEach(src => {
    const opt = document.createElement('option');
    opt.value = src.id;
    opt.textContent = `[#${src.id}] ${src.title || 'Untitled'}`;
    select.appendChild(opt);
  });
}

async function loadFaqs() {
  const list = document.getElementById('faqs-list');
  const loading = document.getElementById('faqs-loading');
  const empty = document.getElementById('faqs-empty');
  if (!list) return;

  loading.classList.remove('hidden');
  empty.classList.add('hidden');
  list.innerHTML = '';

  try {
    const res = await fetch(`${API}/admin/faqs`, { headers: auth() });
    if (res.status === 401) { handleExpiredToken(); return; }
    const faqs = await res.json();
    loading.classList.add('hidden');
    if (!faqs || faqs.length === 0) {
      empty.classList.remove('hidden');
      return;
    }

    faqs.forEach((f, idx) => {
      const card = document.createElement('div');
      card.className = 'source-card';
      card.style.display = 'flex';
      card.style.flexDirection = 'column';
      card.style.gap = '0.75rem';
      
      const badgeColor = f.is_published ? 'var(--success)' : 'var(--text-muted)';
      const badgeText = f.is_published ? 'Published' : 'Draft';
      
      card.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem;">
          <div style="flex: 1;">
            <div style="font-weight: 700; color: var(--text-main); margin-bottom: 0.25rem;">${esc(f.question)}</div>
            <div style="font-size: 0.85rem; color: var(--text-muted);">${esc(f.category || 'General')}</div>
          </div>
          <div style="display: flex; gap: 0.5rem; align-items: center;">
            <span class="status-pill" style="background: ${badgeColor}; color: white; padding: 0.2rem 0.5rem; font-size: 0.7rem;">${badgeText}</span>
            <button class="btn-ghost faq-up-btn" data-id="${f.id}" title="Move Up" style="padding: 0.2rem 0.4rem;">▲</button>
            <button class="btn-ghost faq-down-btn" data-id="${f.id}" title="Move Down" style="padding: 0.2rem 0.4rem;">▼</button>
            <button class="btn-ghost faq-edit-btn" data-faq='${esc(JSON.stringify(f))}' title="Edit">✏️</button>
            <button class="btn-row-del faq-del-btn" data-id="${f.id}" title="Delete">🗑</button>
          </div>
        </div>
        <div style="font-size: 0.9rem; color: var(--text-main); background: rgba(0,0,0,0.02); padding: 0.5rem; border-radius: 4px; border-left: 2px solid var(--border-color);">
          ${esc(f.answer).replace(/\n/g, '<br>')}
        </div>
      `;
      list.appendChild(card);
    });

    list.querySelectorAll('.faq-edit-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const f = JSON.parse(btn.dataset.faq);
        document.getElementById('faq-id').value = f.id;
        document.getElementById('faq-question-input').value = f.question;
        document.getElementById('faq-answer-input').value = f.answer;
        document.getElementById('faq-category-input').value = f.category || 'General';
        document.getElementById('faq-source-select').value = f.linked_source_id || '';
        document.getElementById('faq-published-input').checked = f.is_published;
        document.getElementById('faq-form-title').textContent = 'Edit FAQ';
        document.getElementById('faq-cancel-btn').classList.remove('hidden');
        document.getElementById('faq-submit-btn').textContent = 'Save Changes';
        document.getElementById('faq-form-title').scrollIntoView({ behavior: 'smooth' });
      });
    });

    list.querySelectorAll('.faq-del-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        if (!confirm('Delete this FAQ?')) return;
        try {
          await fetch(`${API}/admin/faqs/${btn.dataset.id}`, { method: 'DELETE', headers: auth() });
          loadFaqs();
          toast('FAQ deleted', 'success');
        } catch (e) { toast('Error deleting FAQ', 'error'); }
      });
    });

    // Handle local reordering before saving
    list.querySelectorAll('.faq-up-btn').forEach((btn, idx) => {
      btn.addEventListener('click', () => {
        if (idx === 0) return;
        const currentCard = btn.closest('.source-card');
        const prevCard = currentCard.previousElementSibling;
        list.insertBefore(currentCard, prevCard);
        document.getElementById('faq-save-order-btn').classList.remove('hidden');
      });
    });
    list.querySelectorAll('.faq-down-btn').forEach((btn, idx) => {
      btn.addEventListener('click', () => {
        const currentCard = btn.closest('.source-card');
        const nextCard = currentCard.nextElementSibling;
        if (!nextCard) return;
        list.insertBefore(nextCard, currentCard);
        document.getElementById('faq-save-order-btn').classList.remove('hidden');
      });
    });

  } catch (e) {
    loading.textContent = 'Error loading FAQs.';
  }
}

async function loadSuggestedFaqs() {
  const list = document.getElementById('faq-suggest-list');
  const loading = document.getElementById('faq-suggest-loading');
  const empty = document.getElementById('faq-suggest-empty');
  if (!list) return;

  loading.classList.remove('hidden');
  empty.classList.add('hidden');
  list.innerHTML = '';

  try {
    const res = await fetch(`${API}/admin/faqs/suggested`, { headers: auth() });
    if (res.status === 401) { handleExpiredToken(); return; }
    const items = await res.json();
    loading.classList.add('hidden');
    if (!items || items.length === 0) {
      empty.classList.remove('hidden');
      return;
    }

    items.forEach(item => {
      const card = document.createElement('div');
      card.className = 'source-card';
      card.style.padding = '1rem';
      card.innerHTML = `
        <div style="font-weight: 600; margin-bottom: 0.5rem; color: var(--text-main);">${esc(item.query)}</div>
        <div style="font-size: 0.8rem; color: var(--text-muted); margin-bottom: 1rem;">Asked ${item.count} times recently</div>
        <button class="btn-ghost faq-promote-btn" style="width: 100%; border: 1px dashed var(--primary-color); color: var(--primary-color);" data-q="${esc(item.query)}" data-a="${esc(item.answer || '')}">
          ⭐ Promote to FAQ
        </button>
      `;
      list.appendChild(card);
    });

    list.querySelectorAll('.faq-promote-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.getElementById('faq-id').value = '';
        document.getElementById('faq-question-input').value = btn.dataset.q;
        document.getElementById('faq-answer-input').value = btn.dataset.a;
        document.getElementById('faq-form-title').textContent = 'Create New FAQ';
        document.getElementById('faq-cancel-btn').classList.add('hidden');
        document.getElementById('faq-submit-btn').textContent = 'Save FAQ';
        document.getElementById('faq-form-title').scrollIntoView({ behavior: 'smooth' });
      });
    });
  } catch (e) {
    loading.textContent = 'Error loading suggestions.';
  }
}

const faqSaveOrderBtn = document.getElementById('faq-save-order-btn');
if (faqSaveOrderBtn) {
  faqSaveOrderBtn.addEventListener('click', async () => {
    const list = document.getElementById('faqs-list');
    const items = Array.from(list.querySelectorAll('.faq-up-btn')).map((btn, idx) => ({
      id: parseInt(btn.dataset.id, 10),
      display_order: idx
    }));
    
    faqSaveOrderBtn.textContent = 'Saving...';
    faqSaveOrderBtn.disabled = true;
    
    try {
      await fetch(`${API}/admin/faqs/reorder`, {
        method: 'POST',
        headers: { ...auth(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ items })
      });
      toast('Display order saved', 'success');
      faqSaveOrderBtn.classList.add('hidden');
    } catch (e) {
      toast('Error saving order', 'error');
    } finally {
      faqSaveOrderBtn.textContent = '💾 Save Display Order';
      faqSaveOrderBtn.disabled = false;
    }
  });
}

function resetFaqForm() {
  document.getElementById('faq-form-title').textContent = 'Create New FAQ';
  document.getElementById('faq-id').value = '';
  document.getElementById('faq-form').reset();
  const cancelBtn = document.getElementById('faq-cancel-btn');
  if (cancelBtn) cancelBtn.classList.add('hidden');
  const submitBtn = document.getElementById('faq-submit-btn');
  if (submitBtn) submitBtn.textContent = 'Save FAQ';
}

const faqFormEl = document.getElementById('faq-form');
if (faqFormEl) {
  faqFormEl.addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = document.getElementById('faq-id').value;
    const q = document.getElementById('faq-question-input').value.trim();
    const a = document.getElementById('faq-answer-input').value.trim();
    const cat = document.getElementById('faq-category-input').value;
    const src = document.getElementById('faq-source-select').value;
    const pub = document.getElementById('faq-published-input').checked;

    const payload = {
      question: q,
      answer: a,
      category: cat,
      linked_source_id: src ? parseInt(src, 10) : null,
      is_published: pub
    };

    const method = id ? 'PUT' : 'POST';
    const endpoint = id ? `${API}/admin/faqs/${id}` : `${API}/admin/faqs`;
    
    const submitBtn = document.getElementById('faq-submit-btn');
    const ogText = submitBtn.textContent;
    submitBtn.textContent = 'Saving...';
    submitBtn.disabled = true;

    try {
      const res = await fetch(endpoint, {
        method,
        headers: { ...auth(), 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        toast(id ? 'FAQ updated' : 'FAQ created', 'success');
        resetFaqForm();
        loadFaqs();
        loadSuggestedFaqs();
      } else {
        toast('Error saving FAQ', 'error');
      }
    } catch (e) {
      toast('Connection error', 'error');
    } finally {
      submitBtn.textContent = ogText;
      submitBtn.disabled = false;
    }
  });
}

const faqCancelBtn = document.getElementById('faq-cancel-btn');
if (faqCancelBtn) {
  faqCancelBtn.addEventListener('click', resetFaqForm);
}

// ── FAQ Filters & Bulk Actions ──────────────────────────────────────────

const faqFilters = document.querySelectorAll('.faq-status-filters .filter-btn');
faqFilters.forEach(btn => {
  btn.addEventListener('click', () => {
    faqFilters.forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    
    const filter = btn.dataset.faqFilter;
    const cards = document.querySelectorAll('#faqs-list .source-card');
    cards.forEach(card => {
      const isPublished = card.querySelector('.status-pill').textContent === 'Published';
      if (filter === 'all') card.style.display = 'flex';
      else if (filter === 'published') card.style.display = isPublished ? 'flex' : 'none';
      else if (filter === 'draft') card.style.display = !isPublished ? 'flex' : 'none';
    });
  });
});

const publishAllBtn = document.getElementById('faq-publish-all-btn');
if (publishAllBtn) {
  publishAllBtn.addEventListener('click', async () => {
    if (!confirm('Publish all draft FAQs? They will be visible to users immediately.')) return;
    try {
      const res = await fetch(`${API}/admin/faqs/publish-all`, {
        method: 'POST',
        headers: auth()
      });
      if (res.ok) {
        toast('All drafts published successfully!', 'success');
        loadFaqs();
      }
    } catch(e) { console.error(e); }
  });
}

const autoGenBtn = document.getElementById('faq-auto-gen-btn');
if (autoGenBtn) {
  let faqGenAbortController = null;

  // Cancel button handler
  const cancelBtn = document.getElementById('faq-gen-cancel-btn');
  if (cancelBtn) {
    cancelBtn.addEventListener('click', () => {
      if (faqGenAbortController) {
        faqGenAbortController.abort();
        faqGenAbortController = null;
      }
      const container = document.getElementById('faq-gen-progress-container');
      const statusText = document.getElementById('faq-gen-status-text');
      statusText.textContent = 'Generation cancelled.';
      setTimeout(() => {
        container.classList.add('hidden');
        autoGenBtn.disabled = false;
        loadFaqs(); // Refresh to show any FAQs generated before cancel
        toast('FAQ generation cancelled. Already generated FAQs are saved as drafts.', 'info');
      }, 1500);
    });
  }

  autoGenBtn.addEventListener('click', async () => {
    if (!confirm('This will scan all completed sources and generate draft FAQs using AI. Review them before publishing. Continue?')) return;
    
    const container = document.getElementById('faq-gen-progress-container');
    const statusText = document.getElementById('faq-gen-status-text');
    const countText = document.getElementById('faq-gen-count-text');
    const bar = document.getElementById('faq-gen-progress-bar');
    
    container.classList.remove('hidden');
    bar.style.width = '0%';
    statusText.textContent = 'Starting generation...';
    countText.textContent = '0 / 0 sources done';
    autoGenBtn.disabled = true;

    // Create abort controller for cancel support
    faqGenAbortController = new AbortController();
    
    try {
      const res = await fetch(`${API}/admin/faqs/generate-from-sources`, {
        method: 'POST',
        headers: auth(),
        signal: faqGenAbortController.signal
      });
      
      if (!res.ok) throw new Error('Network error');
      
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      
      while (true) {
        const {value, done} = await reader.read();
        if (done) break;
        
        const chunk = decoder.decode(value);
        const lines = chunk.split('\n\n');
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.substring(6));
              if (data.status === 'starting' || data.status === 'generating') {
                const pct = data.total > 0 ? (data.progress / data.total) * 100 : 0;
                bar.style.width = pct + '%';
                countText.textContent = `${data.progress} / ${data.total} sources done`;
                if (data.source_title) {
                  statusText.textContent = `Generating for: ${data.source_title}`;
                }
              } else if (data.status === 'completed') {
                bar.style.width = '100%';
                countText.textContent = `${data.total} / ${data.total} sources done`;
                statusText.textContent = 'Generation completed!';
                setTimeout(() => {
                  container.classList.add('hidden');
                  autoGenBtn.disabled = false;
                  loadFaqs(); // Refresh the list
                  toast('Draft FAQs generated successfully', 'success');
                  
                  // Switch to draft filter view
                  const draftBtn = document.querySelector('[data-faq-filter="draft"]');
                  if(draftBtn) draftBtn.click();
                }, 2000);
              } else if (data.status === 'error') {
                statusText.textContent = data.message;
                autoGenBtn.disabled = false;
              }
            } catch(e) {}
          }
        }
      }
    } catch(e) {
      if (e.name === 'AbortError') {
        // Cancelled by user — handled in cancel button click
        return;
      }
      console.error(e);
      statusText.textContent = 'An error occurred';
      autoGenBtn.disabled = false;
    } finally {
      faqGenAbortController = null;
    }
  });
}

