export default function AgentContext({ ctx, facts, loading }) {
  return (
    <section className="ag-ctx" data-a aria-label="What the agent is working with">
      <div className="ag-label">Agent context</div>
      <div className="ag-ctx-title">{ctx.title}</div>
      {ctx.doctor ? (
        <p className="ag-ctx-note">Doctor workspace. The agent has no patient data loaded here yet.</p>
      ) : loading && facts.length === 0 ? (
        <div className="ag-skel" aria-hidden="true"><i /><i /><i /></div>
      ) : facts.length ? (
        <dl className="ag-facts">
          {facts.map(([k, v]) => <div key={k}><dd>{v}</dd><dt>{k}</dt></div>)}
        </dl>
      ) : (
        <p className="ag-ctx-note">No records to work with yet.</p>
      )}
    </section>
  );
}
