import { fileUrl } from '../api';

// Renders overlays as real <img> thumbnails, and links for text/JSONL
export default function Gallery({ result }) {
  if (!result) return null;
  const { overlays = [], text_files = [], jsonls = [], out_dir } = result;

  return (
    <div className="card vstack">
      <div className="header">
        <div className="title">Outputs</div>
        <div className="hstack">
          <span className="badge">Out</span>
          <span className="small">{out_dir}</span>
        </div>
      </div>

      {overlays.length > 0 && (
        <>
          <div className="sub">Overlays</div>
          <div className="grid">
            {overlays.map((p, i) => (
              <figure key={i}>
                <img className="media" src={fileUrl(p)} alt={`overlay-${i}`} />
                <figcaption className="small">{p}</figcaption>
              </figure>
            ))}
          </div>
          <hr />
        </>
      )}

      {text_files.length > 0 && (
        <>
          <div className="sub">Transcripts</div>
          <ul>
            {text_files.map((p, i) => (
              <li key={i} className="small">
                <a href={fileUrl(p)} target="_blank" rel="noreferrer">
                  {p}
                </a>
              </li>
            ))}
          </ul>
          <hr />
        </>
      )}

      {jsonls.length > 0 && (
        <>
          <div className="sub">JSON/JSONL</div>
          <ul>
            {jsonls.map((p, i) => (
              <li key={i} className="small">
                <a href={fileUrl(p)} target="_blank" rel="noreferrer">
                  {p}
                </a>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
