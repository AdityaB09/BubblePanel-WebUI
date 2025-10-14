export const API = import.meta.env.VITE_API || 'http://127.0.0.1:8080';

export async function getHealth() {
  const r = await fetch(`${API}/health`);
  return r.json();
}

export async function getStatus() {
  const r = await fetch(`${API}/status`);
  return r.json();
}

export async function getPresets() {
  const r = await fetch(`${API}/presets`);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function runJob(payload) {
  const r = await fetch(`${API}/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function uploadFile(file) {
  const form = new FormData();
  form.append('file', file);
  const r = await fetch(`${API}/upload`, { method: 'POST', body: form });
  if (!r.ok) throw new Error(await r.text());
  return r.json(); // { ok, path, filename }
}

export const fileUrl = (p) => `${API}/file?path=${encodeURIComponent(p)}`;
