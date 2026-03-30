import AsyncStorage from '@react-native-async-storage/async-storage';

const API_URL_KEY = 'coo_api_url';
const TOKEN_KEY = 'coo_token';

export const DEFAULT_API_URL = 'http://localhost:8002';

export async function getApiUrl(): Promise<string> {
  const u = await AsyncStorage.getItem(API_URL_KEY);
  return u && u.length > 0 ? u : DEFAULT_API_URL;
}

export async function setApiUrl(url: string): Promise<void> {
  await AsyncStorage.setItem(API_URL_KEY, url.replace(/\/$/, ''));
}

export async function getToken(): Promise<string | null> {
  return AsyncStorage.getItem(TOKEN_KEY);
}

export async function setToken(token: string | null): Promise<void> {
  if (token) await AsyncStorage.setItem(TOKEN_KEY, token);
  else await AsyncStorage.removeItem(TOKEN_KEY);
}

function authHeaders(token: string | null): HeadersInit {
  const h: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) h['Authorization'] = `Bearer ${token}`;
  return h;
}

export async function login(
  email: string,
  password: string,
  baseUrl?: string
): Promise<{ token: string; email: string; plan?: string; name?: string; api_key?: string }> {
  const api = baseUrl || (await getApiUrl());
  const r = await fetch(`${api}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Login failed');
  if (!data.token) throw new Error('No token returned');
  await setToken(data.token);
  return data;
}

export async function logout(baseUrl?: string): Promise<void> {
  const api = baseUrl || (await getApiUrl());
  const token = await getToken();
  try {
    if (token) {
      await fetch(`${api}/auth/logout`, {
        method: 'POST',
        headers: authHeaders(token) as Record<string, string>,
        body: '{}',
      });
    }
  } catch {
    /* ignore */
  }
  await setToken(null);
}

export async function execute(
  command: string,
  dryRun: boolean,
  token: string | null,
  baseUrl?: string
): Promise<{
  task_id: string;
  status: string;
  goal?: string;
}> {
  const api = baseUrl || (await getApiUrl());
  const r = await fetch(`${api}/execute`, {
    method: 'POST',
    headers: authHeaders(token) as Record<string, string>,
    body: JSON.stringify({ command, dry_run: dryRun, source: 'mobile' }),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data));
  return data;
}

export async function listTasks(
  token: string | null,
  limit = 30,
  baseUrl?: string
): Promise<{ count: number; tasks: any[] }> {
  const api = baseUrl || (await getApiUrl());
  const r = await fetch(`${api}/tasks?limit=${limit}`, {
    headers: authHeaders(token) as Record<string, string>,
  });
  const data = await r.json().catch(() => ({ tasks: [] }));
  if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Failed to load tasks');
  return data;
}

export async function getTask(taskId: string, token: string | null, baseUrl?: string): Promise<any> {
  const api = baseUrl || (await getApiUrl());
  const r = await fetch(`${api}/tasks/${encodeURIComponent(taskId)}`, {
    headers: authHeaders(token) as Record<string, string>,
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Task not found');
  return data;
}

export async function getTaskLogs(taskId: string, token: string | null, baseUrl?: string): Promise<any[]> {
  const api = baseUrl || (await getApiUrl());
  const r = await fetch(`${api}/tasks/${encodeURIComponent(taskId)}/logs`, {
    headers: authHeaders(token) as Record<string, string>,
  });
  const data = await r.json().catch(() => ({ logs: [] }));
  if (!r.ok) return [];
  return data.logs || [];
}

export async function getMe(token: string | null, baseUrl?: string): Promise<any | null> {
  const api = baseUrl || (await getApiUrl());
  if (!token) return null;
  const r = await fetch(`${api}/auth/me`, {
    headers: authHeaders(token) as Record<string, string>,
  });
  if (!r.ok) return null;
  return r.json();
}

export async function transcribeAndExecute(
  uri: string,
  token: string | null,
  baseUrl?: string
): Promise<{ text: string; task_id?: string }> {
  const api = baseUrl || (await getApiUrl());
  const form = new FormData();
  form.append('file', {
    uri,
    name: 'recording.m4a',
    type: 'audio/m4a',
  } as any);
  const headers: Record<string, string> = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const r = await fetch(`${api}/voice/transcribe?auto_execute=true`, {
    method: 'POST',
    headers,
    body: form,
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Transcription failed');
  return data;
}
