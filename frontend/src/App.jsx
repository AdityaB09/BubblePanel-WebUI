import { useEffect, useMemo, useState } from 'react';
import { API, getPresets, runJob, getHealth } from './api';
import RunCard from './components/RunCard';
import Gallery from './components/Gallery';
import History from './components/History';
import Compare from './components/Compare';
import Toast from './components/Toast';

const DEFAULT_FORM = {
  input: '.\\data\\chapter\\smoke_chapter\\page_0007.png',
  out: '.\\data\\outputs\\page_0007_web',
  jsonl: 'panels.jsonl',
  host: 'http://127.0.0.1:11434',

  // summary mode
  page_summarize: true,
  page_style: 'paragraph', // 'paragraph' | 'novel'

  // engines
  engine: 'llm', // 'llm' | 'encoder'
  ollama_text: 'qwen2.5:7b-instruct',

  // encoder options
  embed_model: 'sentence-transformers/all-mpnet-base-v2',
  mlm_refiner: false,

  // advanced toggles
  recon_verbose: false,
  save_crops: false,
  all_ocr: false,
  ocr_verbose: false,
  no_ocr: false,
};

function buildCommandPreview(f) {
  const parts = [
    'python', 'smoke_test.py',
    '--input', f.input,
    '--out', f.out,
    '--jsonl', f.jsonl,
  ];

  if (f.page_summarize) {
    parts.push('--page-summarize');
    parts.push(f.page_style === 'novel' ? '--novel' : '--paragraph');
  }

  if (f.engine === 'llm') {
    if (f.ollama_text) {
      parts.push('--ollama-text', f.ollama_text, '--host', f.host);
    }
  } else {
    parts.push('--encoder', '--embed-model', f.embed_model);
    if (f.mlm_refiner) parts.push('--mlm-refiner');
  }

  if (f.recon_verbose) parts.push('--recon-verbose');
  if (f.save_crops) parts.push('--save-crops');
  if (f.all_ocr) parts.push('--all-ocr');
  if (f.ocr_verbose) parts.push('--ocr-verbose');
  if (f.no_ocr) parts.push('--no-ocr');

  return parts.map(x => (/\s/.test(x) ? `"${x}"` : x)).join(' ');
}

export default function App() {
  const [form, setForm] = useState(DEFAULT_FORM);
  const [presets, setPresets] = useState({});
  const [result, setResult] = useState(null);
  const [toast, setToast] = useState('');
  const [error, setError] = useState(null);
  const [history, setHistory] = useState([]);
  const [leftIdx, setLeftIdx] = useState(null);
  const [rightIdx, setRightIdx] = useState(null);
  const [isRunning, setIsRunning] = useState(false);
  const [health, setHealth] = useState(null);

  useEffect(() => {
    getPresets().then(setPresets).catch((e) => setError(e));
    // ping backend so we can show status + which URL we’re using
    getHealth().then(setHealth).catch(() => setHealth({ ok: false }));
  }, []);

  const onRun = async () => {
    setToast('Running…');
    setIsRunning(true);
    setError(null);
    try {
      // sanitize host (avoid trailing spaces/slashes/quotes)
      const clean = {
        ...form,
        host: (form.host || '').trim().replace(/^['"]|['"]$/g, '').replace(/\/+$/,''),
      };
      const res = await runJob(clean);
      setResult(res);
      setHistory(h => [{ ok: res.ok, time: Date.now(), form: { ...clean }, res }, ...h]);
      setToast(res.ok ? 'Done' : 'Finished with errors');
      // If backend finished but reported errors, show stderr inline
      if (!res.ok) {
        setError({ kind: 'pipeline', message: 'Pipeline returned ok=false', body: res.stderr || '(no stderr)' });
      }
    } catch (e) {
      // e has {kind, status, url, body} from api.js
      setError(e);
      setToast('Request failed');
    } finally {
      setIsRunning(false);
      setTimeout(() => setToast(''), 1800);
    }
  };

  const applyPreset = (key) => {
    const p = presets[key];
    if (!p) return;
    setForm(prev => ({ ...prev, ...p }));
  };

  const left = useMemo(() => (leftIdx != null ? history[leftIdx]?.res : null), [leftIdx, history]);
  const right = useMemo(() => (rightIdx != null ? history[rightIdx]?.res : null), [rightIdx, history]);

  return (
    <div className="container vstack">
      <div className="vstack">
        <div className="title">BubblePanel Web</div>
        <div className="sub">Website UI • Cards • Gallery • Presets (no terminal)</div>
      </div>

      {/* Backend status + which URL we’re using */}
      <div className="card row" style={{ padding: 12, gap: 12, alignItems: 'center', marginTop: 12 }}>
        <div className="small" style={{ opacity: .8 }}>Backend:</div>
        <code className="small" style={{ whiteSpace: 'pre-wrap' }}>{API}</code>
        <span style={{
          marginLeft: 'auto',
          padding: '3px 8px',
          borderRadius: 999,
          fontSize: 12,
          background: health?.ok ? '#063' : '#5a0',
          color: '#fff'
        }}>
          {health?.ok ? 'OK' : 'Unknown'}
        </span>
      </div>

      {/* Command preview */}
      <div className="card" style={{ padding: 12, marginTop: 12 }}>
        <div className="small" style={{ opacity: .8, marginBottom: 6 }}>Command preview</div>
        <code style={{ whiteSpace: 'pre-wrap', fontSize: 12 }}>
          {buildCommandPreview(form)}
        </code>
      </div>

      {/* Error banner (rich details) */}
      {error && (
        <div className="card vstack" style={{ borderLeft: '4px solid #f87171', gap: 8 }}>
          <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
            <div className="title" style={{ color: '#fda4af' }}>
              {error.kind === 'http' ? `HTTP ${error.status} ${error.statusText}` :
               error.kind === 'bad-json' ? 'Invalid JSON from server' :
               error.kind === 'pipeline' ? 'Pipeline error' : 'Request failed'}
            </div>
            <button className="btn" onClick={() => setError(null)}>Dismiss</button>
          </div>
          {error.url && <div className="small">URL: <code>{error.url}</code></div>}
          {error.message && <div className="small">Message: {error.message}</div>}
          {error.body && (
            <>
              <div className="small" style={{ opacity: .7, marginTop: 6 }}>Body:</div>
              <div style={{ background: '#0b1015', color: '#cbd5e1', padding: 10, borderRadius: 8, overflow: 'auto', maxHeight: 220, fontFamily: 'ui-monospace, Menlo, monospace', fontSize: 12, whiteSpace: 'pre-wrap' }}>
                {error.body}
              </div>
            </>
          )}
        </div>
      )}

      <RunCard form={form} setForm={setForm} onRun={onRun} onPreset={applyPreset} isRunning={isRunning} />

      <div className="row">
        <div className="vstack" style={{ gap: 12 }}>
          <Gallery result={result} />

          {result && (
            <div className="card vstack">
              <div className="title">Last run logs</div>
              <div className="sub">Command</div>
              <code className="small" style={{ whiteSpace: 'pre-wrap' }}>{result.command}</code>
              <div className="sub" style={{ marginTop: 8 }}>stdout</div>
              <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 240, overflow: 'auto' }}>{result.stdout || '(empty)'}</pre>
              <div className="sub" style={{ marginTop: 8 }}>stderr</div>
              <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 240, overflow: 'auto', color: '#f7b' }}>{result.stderr || '(empty)'}</pre>
            </div>
          )}
        </div>

        <div className="vstack" style={{ gap: 12 }}>
          <History history={history} onSelect={(i) => setResult(history[i].res)} />
          <div className="card vstack">
            <div className="title">Compare (stdout)</div>
            <div className="row">
              <select
                onChange={(e) => setLeftIdx(e.target.value ? Number(e.target.value) : null)}
                value={leftIdx ?? ''}
              >
                <option value="">Left run…</option>
                {history.map((h, i) => (
                  <option key={i} value={i}>
                    {new Date(h.time).toLocaleTimeString()} • {h.form.engine}/{h.form.page_style}
                  </option>
                ))}
              </select>
              <select
                onChange={(e) => setRightIdx(e.target.value ? Number(e.target.value) : null)}
                value={rightIdx ?? ''}
              >
                <option value="">Right run…</option>
                {history.map((h, i) => (
                  <option key={i} value={i}>
                    {new Date(h.time).toLocaleTimeString()} • {h.form.engine}/{h.form.page_style}
                  </option>
                ))}
              </select>
            </div>
            <Compare left={left} right={right} />
          </div>
        </div>
      </div>

      <div className="footer">© BubblePanel Web UI</div>
      <Toast msg={toast} />
    </div>
  );
}
