import { forwardRef } from "react";
import { AgentMark } from "./AgentMark.jsx";

// Closed state: compact, quiet, always in the same place. Hover lifts it a few pixels; nothing pulses or bounces.
const AgentLauncher = forwardRef(function AgentLauncher({ open, onClick, controls }, ref) {
  return (
    <button
      ref={ref}
      type="button"
      className={`ag-launch${open ? " open" : ""}`}
      onClick={onClick}
      aria-expanded={open}
      aria-controls={controls}
      aria-label={open ? "Close MediThread Agent" : "Open MediThread Agent"}
    >
      <span className="ag-launch-mark"><AgentMark size={22} /></span>
      <span className="ag-launch-text">
        <b>Agent</b>
        <small>{open ? "Close" : "MediThread"}</small>
      </span>
    </button>
  );
});
export default AgentLauncher;
