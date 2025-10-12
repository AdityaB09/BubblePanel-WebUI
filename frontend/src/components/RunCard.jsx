import Field from './Field';

export default function RunCard({ form, setForm, onRun, onPreset, isRunning }) {
  const update = (k, v) => setForm(prev => ({ ...prev, [k]: v }));

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
        <Field label="Input image path">
          <input value={form.input} onChange={e=>update('input', e.target.value)}
                 placeholder=".\\data\\chapter\\smoke_chapter\\page_0007.png"/>
        </Field>
        <Field label="Output folder">
          <input value={form.out} onChange={e=>update('out', e.target.value)}
                 placeholder=".\\data\\outputs\\page_0007_web"/>
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
        <button onClick={onRun} disabled={isRunning}>{isRunning ? 'Running…' : 'Run'}</button>
      </div>
    </div>
  );
}
