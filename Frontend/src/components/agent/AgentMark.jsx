// The Agent's logo: a thread, a node on it, and a small spark branching off. Not a speech bubble, not a robot.
export function AgentMark({ size = 24 }) {
  return (
    <svg className="ag-mark" viewBox="0 0 24 24" width={size} height={size} fill="none" aria-hidden="true">
      <path className="th" d="M7 2.5v19" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <path className="br" d="M7 13c0-3 3-4.5 6.5-4.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <circle className="nd" cx="7" cy="13" r="3" fill="currentColor" />
      <path className="sp" d="M17.5 3.5l1 2.6 2.6 1-2.6 1-1 2.6-1-2.6-2.6-1 2.6-1z" fill="currentColor" />
    </svg>
  );
}
