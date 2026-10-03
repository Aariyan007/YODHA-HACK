// One flag banner. Icon plus text so colour is never the only signal.
// Red for clash / duplicate / allergy / urgent, yellow for missing info, grey otherwise.

const ICONS = {
  clash: "⚠",
  duplicate: "⇆",
  allergy: "⚠",
  urgent: "⛑",
  missing: "ⓘ",
};

const COLOR = {
  clash: "alert",
  duplicate: "alert",
  allergy: "alert",
  urgent: "alert",
  missing: "watch",
};

export function FlagBanner({ flag, onDismiss }) {
  const color = COLOR[flag.kind] || "watch";
  const icon = ICONS[flag.kind] || "ⓘ";
  return (
    <div
      className={`console-flag ${color}`}
      role="alert"
      aria-live="polite"
    >
      <span className="console-flag-icon" aria-hidden="true">{icon}</span>
      <div className="console-flag-body">
        <strong>{flag.title}</strong>
        <p className="small muted">{flag.reason}</p>
      </div>
      {onDismiss && (
        <button className="link small" onClick={() => onDismiss(flag.id)} aria-label={`Dismiss ${flag.title}`}>
          Dismiss
        </button>
      )}
    </div>
  );
}

export function FlagList({ flags, onDismiss }) {
  if (!flags?.length) return null;
  // Severity order: high, medium, low
  const rank = { high: 0, medium: 1, low: 2 };
  const sorted = [...flags].sort((a, b) => (rank[a.severity] ?? 9) - (rank[b.severity] ?? 9));
  return (
    <div className="console-flags" aria-live="polite">
      {sorted.map((f) => <FlagBanner key={f.id || `${f.title}-${f.lineIndex}`} flag={f} onDismiss={onDismiss} />)}
    </div>
  );
}
