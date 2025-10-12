export default function History({history, onSelect}){
if (!history.length) return null
return (
<div className="card vstack">
<div className="title">Run History</div>
<div className="grid">
{history.map((h,i)=> (
<div key={i} className="vstack" style={{border:'1px solid var(--muted)', borderRadius:12, padding:12}}>
<div className="hstack" style={{justifyContent:'space-between'}}>
<span className="badge">{h.ok? 'OK' : 'ERR'}</span>
<span className="small">{new Date(h.time).toLocaleString()}</span>
</div>
<div className="small">{h.form.engine.toUpperCase()} • {h.form.page_style}</div>
<div className="small" style={{overflow:'hidden', textOverflow:'ellipsis'}}>{h.form.input}</div>
<div className="hstack">
<button className="ghost" onClick={()=>onSelect(i)}>Open</button>
</div>
</div>
))}
</div>
</div>
)
}