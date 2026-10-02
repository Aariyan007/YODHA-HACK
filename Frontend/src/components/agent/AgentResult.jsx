import { Arrow } from "../../design/primitives.jsx";

export default function AgentResult({ result, onBack, onGo, ctxActions, onRun, onType }) {
  return (
    <section className="ag-res" data-a aria-live="polite" aria-label="Result">
      <div className="ag-label">{result.preview ? "Not connected yet" : "Result"}</div>
      <h3 className="ag-res-title">{result.title}</h3>
      {result.lead && <p className="ag-res-lead">{result.lead}</p>}
      {result.items?.length > 0 && (
        <ul className="ag-res-list">
          {result.items.map((it, i) => (
            <li key={i} className={it.tone || "steady"}>
              {it.glyph && <span className="gl" aria-hidden="true">{it.glyph}</span>}
              <span className="lb">{it.label}</span>
              <span className="vl">{it.value}</span>
              {it.sub && <span className="sb">{it.sub}</span>}
            </li>
          ))}
        </ul>
      )}
      {result.note && <p className="ag-res-note">{result.note}</p>}
      {result.typeChoices?.length > 0 && (
        <div className="ag-res-sug" role="group" aria-label="What kind of document is this?">
          {result.typeChoices.map((c) => <button key={c.id} type="button" className="ag-chip" onClick={() => onType(c.id)}>{c.title}</button>)}
        </div>
      )}
      {result.suggestions?.length > 0 && (
        <div className="ag-res-sug">
          {result.suggestions.map((a) => <button key={a.id} type="button" className="ag-chip" onClick={() => onRun(a.id, a.title)}>{a.title}</button>)}
        </div>
      )}
      <div className="ag-res-actions">
        {result.cta && <button type="button" className="mt-btn sm" onClick={() => onGo(result.cta.to)}>{result.cta.label} <Arrow /></button>}
        <button type="button" className="mt-btn secondary sm" onClick={onBack}>All actions</button>
      </div>
    </section>
  );
}
