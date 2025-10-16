// Base URL from env (no trailing slash). Defaults to localhost only for dev.
export const API =
  (import.meta.env.VITE_API ? import.meta.env.VITE_API.replace(/\/+$/, "") : "") ||
  "http://127.0.0.1:8080";

async function readBody(res) {
  const text = await res.text();
  try { return { text, json: JSON.parse(text) }; }
  catch { return { text, json: null }; }
}

function httpError(res, bodyText) {
  const err = new Error(`HTTP ${res.status} ${res.statusText}`);
  err.kind = "http";
  err.status = res.status;
  err.body = bodyText;
  return err;
}

export async function getStatus() {
  const r = await fetch(`${API}/status`);
  const { text, json } = await readBody(r);
  if (!r.ok) throw httpError(r, text);
  return json ?? {};
}

export async function getPresets() {
  const r = await fetch(`${API}/presets`);
  const { text, json } = await readBody(r);
  if (!r.ok) throw httpError(r, text);
  return json ?? {};
}

export async function uploadFile(file) {
  const form = new FormData();
  form.append("file", file);
  const r = await fetch(`${API}/upload`, { method: "POST", body: form });
  const { text, json } = await readBody(r);
  if (!r.ok) throw httpError(r, text);
  return json ?? {};
}

export async function runJob(body) {
  const r = await fetch(`${API}/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const { text, json } = await readBody(r);
  if (!r.ok) throw httpError(r, text);
  if (!json) {
    const err = new Error("Invalid JSON from server");
    err.kind = "bad-json";
    err.url = `${API}/run`;
    err.body = text || "(empty)";
    throw err;
  }
  return json;
}

export async function pollJob(jobId) {
  const r = await fetch(`${API}/run/${jobId}`);
  const { text, json } = await readBody(r);
  if (!r.ok) throw httpError(r, text);
  return json ?? {};
}

export const fileUrl = (p) => `${API}/file?path=${encodeURIComponent(p)}`;
