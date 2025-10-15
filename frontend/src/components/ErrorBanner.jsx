// src/components/ErrorBanner.jsx
export default function ErrorBanner({ error, onClose }) {
  if (!error) return null;

  const isHttp = error.kind === 'http';
  const title = isHttp
    ? `HTTP ${error.status} ${error.statusText}`
    : (error.kind === 'bad-json' ? 'Invalid JSON from server' : 'Request failed');

  return (
    <div className="card vstack" style={{borderLeft: '4px solid #f87171', gap: 8}}>
      <div className="row" style={{justifyContent:'space-between', alignItems:'center'}}>
        <div className="title" style={{color:'#fda4af'}}>Error</div>
        <button className="btn" onClick={onClose}>Dismiss</button>
      </div>

      <div style={{fontFamily:'ui-monospace, SFMono-Regular, Menlo, monospace', fontSize:13, lineHeight:1.4, whiteSpace:'pre-wrap'}}>
        <div><b>{title}</b></div>
        {isHttp && <div>URL: {error.url}</div>}
        {error.message && <div>Message: {error.message}</div>}
        {error.body && <>
          <div style={{opacity:.7, marginTop:6}}>Body:</div>
          <div style={{background:'#0b1015', padding:'10px', borderRadius:8, overflow:'auto', maxHeight:220}}>
            {error.body}
          </div>
        </>}
      </div>
    </div>
  );
}
