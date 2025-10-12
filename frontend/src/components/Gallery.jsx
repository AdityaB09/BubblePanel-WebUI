// For now we list file paths (safe in browser). We can add a /files endpoint later for thumbnails.
export default function Gallery({result}){
  if (!result) return null;
  const { overlays=[], text_files=[], jsonls=[], out_dir } = result;
  return (
    <div className="card vstack">
      <div className="header">
        <div className="title">Outputs</div>
        <div className="hstack">
          <span className="badge">Out</span>
          <span className="small">{out_dir}</span>
        </div>
      </div>

      {overlays.length>0 && (
        <>
          <div className="sub">Overlays</div>
          <ul>{overlays.map((p,i)=><li key={i} className="small">{p}</li>)}</ul>
          <hr/>
        </>
      )}

      {text_files.length>0 && (
        <>
          <div className="sub">Transcripts</div>
          <ul>{text_files.map((p,i)=><li key={i} className="small">{p}</li>)}</ul>
          <hr/>
        </>
      )}

      {jsonls.length>0 && (
        <>
          <div className="sub">JSON/JSONL</div>
          <ul>{jsonls.map((p,i)=><li key={i} className="small">{p}</li>)}</ul>
        </>
      )}
    </div>
  );
}
