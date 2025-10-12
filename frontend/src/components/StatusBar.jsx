import { useEffect, useState } from 'react';
import { getHealth, getStatus } from '../api';

export default function StatusBar() {
  const [health, setHealth] = useState(null);
  const [status, setStatus] = useState(null);

  useEffect(() => {
    const fetchAll = async () => {
      try { setHealth(await getHealth()); } catch {}
      try { setStatus(await getStatus()); } catch {}
    };
    fetchAll();
    const id = setInterval(fetchAll, 3000);
    return () => clearInterval(id);
  }, []);

  const ok = !!(health?.ok && status?.ok && status?.python_exists && status?.repo_exists && status?.script_exists);

  return (
    <div className="card hstack" style={{justifyContent:'space-between', alignItems:'center'}}>
      <div className="hstack" style={{gap:8, flexWrap:'wrap'}}>
        <span className="badge" style={{background: ok ? '#0f4' : '#f44', color:'#041018'}}>
          {ok ? 'Backend: OK' : 'Backend: Issue'}
        </span>
        <span className="small">py: {status?.python} ({status?.python_exists ? 'found' : 'missing'})</span>
        <span className="small">repo: {status?.repo_root} ({status?.repo_exists ? 'exists' : 'missing'})</span>
        <span className="small">script: {status?.script} ({status?.script_exists ? 'exists' : 'missing'})</span>
      </div>
      <div className="small" title="Health">{health ? 'health ✓' : 'health …'}</div>
    </div>
  );
}
