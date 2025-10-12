import { useEffect, useMemo, useState } from 'react';
import { getPresets, runJob } from './api';
import RunCard from './components/RunCard';
import Gallery from './components/Gallery';
import History from './components/History';
import Compare from './components/Compare';
import Toast from './components/Toast';
import StatusBar from './components/StatusBar';

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
  const [history, setHistory] = useState([]);
  const [leftIdx, setLeftIdx] = useState(null);
  const [rightIdx, setRightIdx] = useState(null);
  const [isRunning, setIsRunning] = useState(false);

  useEffect(() => { getPresets().then(setPresets).catch(() => {}); }, []);

  const onRun = async () => {
    setToast('Running…');
    setIsRunning(true);
    try {
      const res = await runJob(form);
      setResult(res);
      setHistory(h => [{ ok: res.ok, time: Date.now(), form: { ...form }, res }, ...h]);
      setToast(res.ok ? 'Done' : 'Finished with errors');
    } catch {
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

      <StatusBar />

      <div className="card" style={{padding:12, marginTop:12}}>
        <div className="small" style={{opacity:.8, marginBottom:6}}>Command preview</div>
        <code style={{whiteSpace:'pre-wrap', fontSize:12}}>
          {buildCommandPreview(form)}
        </code>
      </div>

      <RunCard form={form} setForm={setForm} onRun={onRun} onPreset={applyPreset} isRunning={isRunning} />

      <div className="row">
        <div className="vstack" style={{gap:12}}>
          <Gallery result={result} />

          {result && (
            <div className="card vstack">
              <div className="title">Last run logs</div>
              <div className="sub">Command</div>
              <code className="small" style={{whiteSpace:'pre-wrap'}}>{result.command}</code>
              <div className="sub" style={{marginTop:8}}>stdout</div>
              <pre style={{whiteSpace:'pre-wrap', maxHeight:240, overflow:'auto'}}>{result.stdout || '(empty)'}</pre>
              <div className="sub" style={{marginTop:8}}>stderr</div>
              <pre style={{whiteSpace:'pre-wrap', maxHeight:240, overflow:'auto', color:'#f7b' }}>{result.stderr || '(empty)'}</pre>
            </div>
          )}
        </div>

        <div className="vstack" style={{gap:12}}>
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
