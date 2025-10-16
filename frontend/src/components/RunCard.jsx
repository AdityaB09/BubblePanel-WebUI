// src/components/RunCard.jsx
import { useRef, useState, useMemo } from 'react';
import Field from './Field';
import { uploadFile } from '../api';

export default function RunCard({ form, setForm, onRun, onPreset, isRunning }) {
  const update = (k, v) => setForm(prev => ({ ...prev, [k]: v }));

  // ---------- upload handling ----------
  const fileRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [uploadedName, setUploadedName] = useState('');
  const pickFile = () => fileRef.current?.click();

  const onFileChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const res = await uploadFile(file);
      // Prefer ui_path if returned, else path
      const serverPath = res?.ui_path || res?.path;
      if (res?.ok && serverPath) {
        update('input', serverPath);       // <-- use server-visible path
        setUploadedName(res.filename || '');
      }
    } catch {
      alert('Upload failed');
    } finally {
      setUploading(false);
      e.target.value = ''; // allow re-selecting same file
    }
  };

  // ---------- summarization safety ----------
  const llmSelected = form.engine === 'llm';
  const hasHost = !!(form.host && String(form.host).trim());
  const canSummarize = llmSelected && hasHost;

  // If summarize is on but conditions are no longer valid, auto-disable
  useMemo(() => {
    if (!canSummarize && form.page_summarize) {
      update('page_summarize', false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canSummarize, form.engine, form.host]);

  const canRun = !!form.input && !uploading && !isRunning;

  return (
    <div className="card vstack">
      <div className="header">
        <div>
          <div className="title">Process Page</div>
          <div className="sub">Configure and run BubblePanel</div>
        </div>
        <div className="hstack">
          <span className="badge">Ollama host</span>
          <span className="small">{form.host || '(none)'}</span>
        </div>
      </div>

      {/* input + out */}
      <div className="row">
        <Field label="Input image">
          <div className="hstack" style={{ gap: 8, alignItems: 'center' }}>
            <input
              value={form.input || ''}
              onChange={e => update('input', e.target.value)}
              placeholder="(Choose image or paste absolute server path like /app/uploads/...)"
              style={{ flex: 1 }}
            />
            <input
              type="file"
              accept="image/*"
              ref={fileRef}
              onChange={onFileChange}
              style={{ display: 'none' }}
            />
            <button className="ghost" onClick={pickFile} disabled={uploading}>
              {uploading ? 'Uploading…' : 'Choose image'}
            </button>
          </div>
          {uploadedName && <div className="small">Uploaded: {uploadedName}</div>}
          {!form.input && <div className="small" style={{ color: '#f7b' }}>No input selected yet.</div>}
        </Field>

        <Field label="Output folder">
          <input
            value={form.out}
            onChange={e => update('out', e.target.value)}
            placeholder="./data/outputs/run_web"
          />
        </Field>
      </div>

      {/* jsonl + engine */}
      <div className="row">
        <Field label="panels.jsonl path">
          <input value={form.jsonl} onChange={e=>update('jsonl', e.target.value)} placeholder="panels.jsonl"/>
        </Field>
        <Field label="Engine">
          <select value={form.engine} onChange={e=>update('engine', e.target.value)}>
            <option value="encoder">Encoder (MPNet)</option>
            <option value="llm">Text LLM (Ollama)</option>
          </select>
        </Field>
      </div>

      {/* engine-specific rows */}
      {llmSelected ? (
        <div className="row">
          <Field label="Text LLM model">
            <input
              value={form.ollama_text || ''}
              onChange={e=>update('ollama_text', e.target.value)}
              placeholder="qwen2.5:7b-instruct"
            />
          </Field>
          <Field label="Ollama host">
            <input
              value={form.host || ''}
              onChange={e=>update('host', e.target.value)}
              placeholder="https://your-ollama.onrender.com"
            />
          </Field>
        </div>
      ) : (
        <div className="row">
          <Field label="Embed model">
            <input
              value={form.embed_model}
              onChange={e=>update('embed_model', e.target.value)}
              placeholder="sentence-transformers/all-mpnet-base-v2"
            />
          </Field>
          <Field label="Refiner">
            <label className="toggle">
              <input
                type="checkbox"
                checked={!!form.mlm_refiner}
                onChange={e=>update('mlm_refiner', e.target.checked)}
              />
              <span className="small">Use masked-LM refiner</span>
            </label>
          </Field>
        </div>
      )}

      {/* summarize + style */}
      <div className="row">
        <Field label="Summary style">
          <div className="radio">
            <label><input type="radio" name="style"
                   checked={form.page_style==='paragraph'}
                   onChange={()=>update('page_style','paragraph')}/> Paragraph</label>
            <label><input type="radio" name="style"
                   checked={form.page_style==='novel'}
                   onChange={()=>update('page_style','novel')}/> Novel</label>
          </div>
        </Field>
        <Field label="Summarization">
          <label className="toggle" title={canSummarize ? '' : 'Enable only when Engine=LLM and a reachable Ollama host is set'}>
            <input
              type="checkbox"
              checked={!!form.page_summarize && canSummarize}
              disabled={!canSummarize}
              onChange={e=>update('page_summarize', e.target.checked)}
            />
            <span className="small">Summarize page (requires LLM + host)</span>
          </label>
          {!hasHost && llmSelected && (
            <div className="small" style={{ color:'#f7b' }}>
              Provide a real Ollama host to enable summarization (not 127.0.0.1).
            </div>
          )}
        </Field>
      </div>

      {/* advanced */}
      <div className="row">
        <Field label="Advanced">
          <div className="hstack" style={{flexWrap:'wrap'}}>
            <label className="toggle"><input type="checkbox" checked={!!form.recon_verbose}
                onChange={e=>update('recon_verbose', e.target.checked)}/> Recon verbose</label>
            <label className="toggle"><input type="checkbox" checked={!!form.save_crops}
                onChange={e=>update('save_crops', e.target.checked)}/> Save crops</label>
            <label className="toggle"><input type="checkbox" checked={!!form.all_ocr}
                onChange={e=>update('all_ocr', e.target.checked)}/> All OCR</label>
            <label className="toggle"><input type="checkbox" checked={!!form.ocr_verbose}
                onChange={e=>update('ocr_verbose', e.target.checked)}/> OCR verbose</label>
            <label className="toggle"><input type="checkbox" checked={!!form.no_ocr}
                onChange={e=>update('no_ocr', e.target.checked)}/> Skip OCR</label>
          </div>
        </Field>
        <div></div>
      </div>

      {/* presets + run */}
      <div className="hstack" style={{justifyContent:'space-between', flexWrap:'wrap'}}>
        <div className="hstack" style={{gap:8}}>
          <button className="ghost" onClick={()=>onPreset('encoder_paragraph_mpnet')}>Encoder • Paragraph</button>
          <button className="ghost" onClick={()=>onPreset('llm_paragraph_qwen')}>Qwen • Paragraph</button>
          <button className="ghost" onClick={()=>onPreset('llm_paragraph_llama')}>Llama • Paragraph</button>
        </div>
        <button onClick={onRun} disabled={!canRun}>
          {uploading ? 'Uploading…' : isRunning ? 'Running…' : 'Run'}
        </button>
      </div>
    </div>
  );
}
