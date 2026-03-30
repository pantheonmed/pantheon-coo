const DEFAULT_API = 'http://localhost:8002';

async function getApiUrl() {
  const { coo_api_url } = await chrome.storage.local.get('coo_api_url');
  return coo_api_url || DEFAULT_API;
}

async function getToken() {
  const { coo_token } = await chrome.storage.local.get('coo_token');
  return coo_token || '';
}

/**
 * execute — POST /execute with stored token
 */
async function execute() {
  const api = (document.getElementById('apiUrl').value || '').trim() || (await getApiUrl());
  const token = (document.getElementById('token').value || '').trim() || (await getToken());
  const command = (document.getElementById('cmd').value || '').trim();
  if (command.length < 3) {
    alert('Command too short');
    return;
  }
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = 'Bearer ' + token;
  const r = await fetch(api.replace(/\/$/, '') + '/execute', {
    method: 'POST',
    headers,
    body: JSON.stringify({ command, dry_run: false, source: 'chrome' }),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    alert(data.detail || r.statusText);
    return;
  }
  await chrome.storage.local.set({ coo_api_url: api, coo_token: token });
  chrome.notifications.create({ type: 'basic', iconUrl: 'icon.png', title: 'COO', message: 'Task queued: ' + (data.task_id || '').slice(0, 8) });
  loadTasks();
}

async function loadTasks() {
  const api = (document.getElementById('apiUrl').value || '').trim() || (await getApiUrl());
  const token = (document.getElementById('token').value || '').trim() || (await getToken());
  const headers = {};
  if (token) headers['Authorization'] = 'Bearer ' + token;
  const r = await fetch(api.replace(/\/$/, '') + '/tasks?limit=3', { headers });
  if (!r.ok) return;
  const d = await r.json();
  const el = document.getElementById('tasks');
  el.innerHTML = (d.tasks || [])
    .map((t) => '<div class="t">' + (t.goal || t.task_id).slice(0, 60) + ' — <b>' + t.status + '</b></div>')
    .join('');
}

document.getElementById('btnExec').addEventListener('click', () => execute());
document.getElementById('btnPage').addEventListener('click', async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) return;
  chrome.tabs.sendMessage(tab.id, { type: 'GET_PAGE_TEXT' }, (resp) => {
    if (resp?.text) {
      document.getElementById('cmd').value = 'Summarize this page:\n\n' + resp.text.slice(0, 8000);
    }
  });
});

document.addEventListener('DOMContentLoaded', async () => {
  document.getElementById('apiUrl').value = await getApiUrl();
  document.getElementById('token').value = await getToken();
  loadTasks();
});
