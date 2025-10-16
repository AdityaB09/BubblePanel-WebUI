import { API, getStatus, getPresets, uploadFile, runJob, pollJob, fileUrl } from "./api.js";
import { PRESETS } from "./presets.js";

const els = {
  backendUrl: document.querySelector("#backendUrl"),
  statusBadge: document.querySelector("#statusBadge"),
  choose: document.querySelector("#choose"),
  inputPath: document.querySelector("#input"),
  out: document.querySelector("#out"),
  jsonl: document.querySelector("#jsonl"),
  engine: document.querySelector("#engine"),
  ollamaModel: document.querySelector("#ollamaModel"),
  host: document.querySelector("#host"),
  embedModel: document.querySelector("#embedModel"),
  mlm: document.querySelector("#mlm"),
  summarize: document.querySelector("#summarize"),
  style: document.querySelector("#style"),
  recon: document.querySelector("#recon"),
  savecrops: document.querySelector("#savecrops"),
  allocr: document.querySelector("#allocr"),
  ocrverb: document.querySelector("#ocrverb"),
  noocr: document.querySelector("#noocr"),
  runBtn: document.querySelector("#runBtn"),
  cmd: document.querySelector("#cmd"),
  outputs: document.querySelector("#outputs"),
  presets: document.querySelector("#presets"),
};

function setStatus(ok) {
  els.statusBadge.textContent = ok ? "OK" : "Unknown";
  els.statusBadge.className = `badge ${ok ? "ok" : "bad"}`;
  els.backendUrl.textContent = API;
}

function setEngineUi(engine) {
  const llm = engine === "llm";
  els.ollamaModel.disabled = !llm;
  els.host.disabled = !llm;

  // summarization only if LLM + host present
  const canSummarize = llm && !!els.host.value.trim();
  els.summarize.disabled = !canSummarize;
  if (!canSummarize) els.summarize.checked = false;

  // encoder-only fields
  els.embedModel.disabled = llm;
  els.mlm.disabled = llm;
}

function buildCommandPreview(req) {
  const bits = ["python smoke_test.py", "--input", req.input, "--out", req.out, "--jsonl", req.jsonl];

  if (req.page_summarize && req.engine === "llm" && req.ollama_text && req.host) {
    bits.push("--page-summarize");
    bits.push(req.page_style === "novel" ? "--novel" : "--paragraph");
  }

  if (req.engine === "llm" && req.ollama_text && req.host) {
    bits.push("--ollama-text", req.ollama_text, "--host", req.host);
  }

  if (req.engine === "encoder") {
    bits.push("--encoder", "--embed-model", req.embed_model);
    if (req.mlm_refiner) bits.push("--mlm-refiner");
  }

  if (req.recon_verbose) bits.push("--recon-verbose");
  if (req.save_crops) bits.push("--save-crops");
  if (req.all_ocr) bits.push("--all-ocr");
  if (req.ocr_verbose) bits.push("--ocr-verbose");
  if (req.no_ocr) bits.push("--no-ocr");

  return bits.join(" ");
}

function collectRequest() {
  const engine = els.engine.value;

  const req = {
    input: els.inputPath.value,
    out: els.out.value || "./data/outputs/web",
    jsonl: els.jsonl.value || "panels.jsonl",
    engine,

    // LLM options
    ollama_text: engine === "llm" ? (els.ollamaModel.value || null) : null,
    host: engine === "llm" ? (els.host.value.trim() || "") : "",

    // encoder options
    embed_model: engine === "encoder" ? els.embedModel.value : "",
    mlm_refiner: engine === "encoder" && els.mlm.checked,

    // summarize only when safe
    page_summarize: engine === "llm" && !!els.host.value.trim() && els.summarize.checked,
    page_style: els.style.value,

    // advanced flags
    recon_verbose: els.recon.checked,
    save_crops: els.savecrops.checked,
    all_ocr: els.allocr.checked,
    ocr_verbose: els.ocrverb.checked,
    no_ocr: els.noocr.checked,
  };

  els.cmd.textContent = buildCommandPreview(req);
  return req;
}

function link(href, label = href) {
  const a = document.createElement("a");
  a.href = href;
  a.textContent = label;
  a.target = "_blank";
  a.rel = "noopener";
  return a;
}

function renderOutputs(result) {
  if (!result) { els.outputs.textContent = "No result."; return; }
  const wrap = document.createElement("div");

  const title = document.createElement("div");
  title.style.fontWeight = "700"; title.style.margin = "8px 0";
  title.textContent = "Outputs";
  wrap.appendChild(title);

  if (Array.isArray(result.text_files)) {
    const sec = document.createElement("div");
    sec.appendChild(document.createTextNode("Transcripts:"));
    const ul = document.createElement("ul");
    result.text_files.forEach((p) => {
      const li = document.createElement("li"); li.appendChild(link(fileUrl(p), p)); ul.appendChild(li);
    });
    sec.appendChild(ul); wrap.appendChild(sec);
  }

  if (Array.isArray(result.jsonls)) {
    const sec = document.createElement("div");
    sec.appendChild(document.createTextNode("JSONL/JSON:"));
    const ul = document.createElement("ul");
    result.jsonls.forEach((p) => {
      const li = document.createElement("li"); li.appendChild(link(fileUrl(p), p)); ul.appendChild(li);
    });
    sec.appendChild(ul); wrap.appendChild(sec);
  }

  els.outputs.innerHTML = ""; els.outputs.appendChild(wrap);
}

async function init() {
  // backend status
  try { const st = await getStatus(); setStatus(!!st.ok); } catch { setStatus(false); }
  // presets
  els.presets.innerHTML = "";
  Object.keys(PRESETS).forEach((label) => {
    const b = document.createElement("button");
    b.type = "button"; b.className = "pill"; b.textContent = label;
    b.addEventListener("click", () => {
      const p = PRESETS[label];
      els.engine.value = p.engine;
      setEngineUi(els.engine.value);
      if (p.engine === "encoder") {
        els.embedModel.value = p.embed_model || "sentence-transformers/all-mpnet-base-v2";
        els.mlm.checked = !!p.mlm_refiner;
        els.summarize.checked = false;
      } else {
        els.ollamaModel.value = p.ollama_text || "";
        els.host.value = p.host || "";
        els.summarize.checked = !!p.page_summarize && !!els.host.value;
      }
      els.style.value = p.page_style || "paragraph";
      collectRequest();
    });
    els.presets.appendChild(b);
  });

  // react to inputs
  [els.engine, els.ollamaModel, els.host, els.embedModel, els.mlm,
   els.summarize, els.style, els.recon, els.savecrops, els.allocr,
   els.ocrverb, els.noocr, els.out, els.jsonl, els.inputPath].forEach((node) => {
    node.addEventListener("input", () => {
      if (node === els.engine || node === els.host) setEngineUi(els.engine.value);
      collectRequest();
    });
  });

  // upload
  els.choose.addEventListener("change", async (e) => {
    const file = e.target.files?.[0]; if (!file) return;
    try {
      const up = await uploadFile(file); // { ok, path, ui_path }
      els.inputPath.value = up.ui_path || up.path;
      collectRequest();
    } catch (err) {
      els.outputs.innerHTML = `<pre class="err">${String(err?.message || err)}</pre>`;
    }
  });

  // run
  els.runBtn.addEventListener("click", async () => {
    els.runBtn.disabled = true;
    els.outputs.textContent = "Running…";
    const req = collectRequest();
    try {
      const res = await runJob(req);
      // If backend becomes async: poll
      if (res && res.id) {
        let done = null;
        while (!done) {
          await new Promise((r) => setTimeout(r, 1500));
          const st = await pollJob(res.id);
          if (st.status === "done") done = st.result;
          if (st.status === "error") throw new Error(st.error || "Job failed");
        }
        renderOutputs(done);
      } else {
        renderOutputs(res); // sync today
      }
    } catch (e) {
      els.outputs.innerHTML = `<pre class="err">${String(e?.message || e)}</pre>`;
    } finally {
      els.runBtn.disabled = false;
    }
  });

  // defaults
  setEngineUi(els.engine.value);
  // initial preview
  document.getElementById("cmd").textContent = "(choose an image or set /app/uploads/ path, then click Run)";
}

init();
