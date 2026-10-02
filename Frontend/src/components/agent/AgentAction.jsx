import { Arrow } from "../../design/primitives.jsx";

const GLYPH = {
  changes: "↗", open: "→", explain: "◌", prepare: "✎", doctor: "⌖", meds: "℞", rxchanges: "↗", whymatch: "◌", whocansee: "◉",
  summary: "≡", connect: "⇄", addthread: "+", consistency: "✓", dpatients: "◉", dsummary: "≡", dask: "?",
};

export function AgentAction({ action, onRun, first }) {
  return (
    <button type="button" className="ag-act" onClick={() => onRun(action.id, action.title)} data-first={first ? "" : undefined}>
      <span className="g" aria-hidden="true">{GLYPH[action.id] || "→"}</span>
      <span className="t"><b>{action.title}</b><small>{action.sub}</small></span>
      <Arrow />
    </button>
  );
}

export function AgentActionList({ actions, onRun }) {
  return (
    <section className="ag-acts" data-a aria-label="What the agent can do here">
      <div className="ag-label">What can I do?</div>
      <div className="ag-acts-list">
        {actions.map((a, i) => <AgentAction key={a.id} action={a} onRun={onRun} first={i === 0} />)}
      </div>
    </section>
  );
}
