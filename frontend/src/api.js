// src/api.js
// Backend base URL (from Netlify env VITE_API or fallback for local dev)
export const API =
  (import.meta.env.VITE_API ? import.meta.env.VITE_API.replace(/\/+$/, '') : '') ||
  'http://127.0.0.1:8080';

async function readBody(res) {
  const text = await res.text();
  try { return { text, json: JSON.parse(text) }; }
  catch { return { text, json: null }; }
}

function httpError(res, bodyText) {
  const err = new Error(`HTTP ${res.status} ${res.statusText}`);
  err.kind = 'http';
  err.status = res.status;
  err.statusText = res.statusText;
  err.url = res.url;
  err.body = bodyText;
  return err;
}

export async function getHealth() {
  const r = await fetch(`${API}/health`);
  const { text } = await readBody(r);
  if (!r.ok) throw httpError(r, text);
  return JSON.parse(text || '{}');
}

export async function getStatus() {
  const r = await fetch(`${API}/status`);
  const { text } = await readBody(r);
  if (!r.ok) throw httpError(r, text);
  return JSON.parse(text || '{}');
}

export async function getPresets() {
  const r = await fetch(`${API}/presets`);
  const { text, json } = await readBody(r);
  if (!r.ok) throw httpError(r, text);
  return json ?? {};
}

export async function runJob(payload) {
  const r = await fetch(`${API}/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const { text, json } = await readBody(r);
  if (!r.ok) throw httpError(r, text);
  if (!json || typeof json !== 'object') {
    const err = new Error('Invalid JSON from server');
    err.kind = 'bad-json';
    err.url = `${API}/run`;
    err.body = text || '(empty)';
    throw err;
  }
  return json;
}

export async function uploadFile(file) {
  const form = new FormData();
  form.append('file', file);
  const r = await fetch(`${API}/upload`, { method: 'POST', body: form });
  const { text, json } = await readBody(r);
  if (!r.ok) throw httpError(r, text);
  return json ?? {};
}

export const fileUrl = (p) => `${API}/file?path=${encodeURIComponent(p)}`;
