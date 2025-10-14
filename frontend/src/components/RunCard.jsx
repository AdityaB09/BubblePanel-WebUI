import { useRef, useState } from 'react';
import Field from './Field';
import { uploadFile } from '../api';

export default function RunCard({ form, setForm, onRun, onPreset, isRunning }) {
  const update = (k, v) => setForm(prev => ({ ...prev, [k]: v }));

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
      if (res?.ok && res?.path) {
        update('input', res.path);   // <-- use server path as --input
        setUploadedName(res.filename);
      }
    } catch {
      alert('Upload failed');
    } finally {
      setUploading(false);
      e.target.value = ''; // allow re-selecting same file
    }
  };

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
          <span className="small">{form.host}</span>
        </div>
      </div>

      <div className="row">
        <Field label="Input image">
          <div className="hstack" style={{ gap: 8, alignItems: 'center' }}>
            <input
              value={form.input || ''}
              onChange={e => update('input', e.target.value)}
              placeholder="(Choose image or paste absolute path)"
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
            placeholder="C:\\path\\to\\outputs\\run1"
          />
        </Field>
      </div>

      <div className="row">
        <Field label="panels.jsonl path">
          <input value={form.jsonl} onChange={e=>update('jsonl', e.target.value)} placeholder="panels.jsonl"/>
        </Field>
        <Field label="Engine">
          <select value={form.engine} onChange={e=>update('engine', e.target.value)}>
            <option value="llm">Text LLM (Ollama)</option>
            <option value="encoder">Encoder (MPNet)</option>
          </select>
        </Field>
      </div>

      {form.engine === 'llm' ? (
        <div className="row">
          <Field label="Text LLM model">
            <input value={form.ollama_text} onChange={e=>update('ollama_text', e.target.value)}
                   placeholder="qwen2.5:7b-instruct"/>
          </Field>
          <Field label="Ollama host">
            <input value={form.host} onChange={e=>update('host', e.target.value)}
                   placeholder="http://127.0.0.1:11434"/>
          </Field>
        </div>
      ) : (
        <div className="row">
          <Field label="Embed model">
            <input value={form.embed_model} onChange={e=>update('embed_model', e.target.value)}
                   placeholder="sentence-transformers/all-mpnet-base-v2"/>
          </Field>
          <Field label="Refiner">
            <label className="toggle">
              <input type="checkbox" checked={form.mlm_refiner}
                     onChange={e=>update('mlm_refiner', e.target.checked)} />
              <span className="small">Use masked-LM refiner</span>
            </label>
          </Field>
        </div>
      )}

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
        <Field label="Advanced">
          <div className="hstack" style={{flexWrap:'wrap'}}>
            <label className="toggle"><input type="checkbox" checked={form.recon_verbose}
                onChange={e=>update('recon_verbose', e.target.checked)}/> Recon verbose</label>
            <label className="toggle"><input type="checkbox" checked={form.save_crops}
                onChange={e=>update('save_crops', e.target.checked)}/> Save crops</label>
            <label className="toggle"><input type="checkbox" checked={form.all_ocr}
                onChange={e=>update('all_ocr', e.target.checked)}/> All OCR</label>
            <label className="toggle"><input type="checkbox" checked={form.ocr_verbose}
                onChange={e=>update('ocr_verbose', e.target.checked)}/> OCR verbose</label>
            <label className="toggle"><input type="checkbox" checked={form.no_ocr}
                onChange={e=>update('no_ocr', e.target.checked)}/> Skip OCR</label>
          </div>
        </Field>
      </div>

      <div className="hstack" style={{justifyContent:'space-between', flexWrap:'wrap'}}>
        <div className="hstack" style={{gap:8}}>
          <button className="ghost" onClick={()=>onPreset('llm_paragraph_qwen')}>Qwen • Paragraph</button>
          <button className="ghost" onClick={()=>onPreset('llm_novel_qwen')}>Qwen • Novel</button>
          <button className="ghost" onClick={()=>onPreset('encoder_paragraph_mpnet')}>Encoder • Paragraph</button>
          <button className="ghost" onClick={()=>onPreset('llm_paragraph_llama')}>Llama • Paragraph</button>
        </div>
        <button onClick={onRun} disabled={!canRun}>
          {uploading ? 'Uploading…' : isRunning ? 'Running…' : 'Run'}
        </button>
      </div>
    </div>
  );
}
