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

  if (!sources || sources.length === 0) {
    sourcesEmpty.classList.remove('hidden');
    sourcesGrid.classList.add('hidden');
    sidebarSources.innerHTML = '';
    return;
  }

  sourcesEmpty.classList.add('hidden');
  sourcesGrid.classList.remove('hidden');
  sourcesGrid.innerHTML = '';
  sidebarSources.innerHTML = '';

  sources.forEach(s => {
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
