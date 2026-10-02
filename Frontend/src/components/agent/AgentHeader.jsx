import { AgentMark } from "./AgentMark.jsx";
import { agentAvailable } from "../../api/client.js";

export default function AgentHeader({ ctx, onClose }) {
  return (
    <header className="ag-head" data-a>
      <span className="ag-head-mark"><AgentMark size={22} /></span>
      <div className="ag-head-txt">
        <div className="ag-label">MediThread Agent {!agentAvailable() && <span className="ag-preview">Preview</span>}</div>
        <div className="ag-head-ctx">Context · {ctx.label}</div>
      </div>
      <button type="button" className="ag-x" onClick={onClose} aria-label="Close MediThread Agent">×</button>
    </header>
  );
}
