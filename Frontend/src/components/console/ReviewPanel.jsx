import { useEffect, useMemo, useState } from "react";
import { approveConsultation, finalizeConsultation } from "../../api/client.js";
import { Loading } from "../ui.jsx";
import { FlagList } from "./FlagBanner.jsx";

/**
 * State 3 — Review & edit.
 *
 * On mount: calls /finalize to get the full SOAP note (each field carries its
 * source_line indexes). The doctor edits any of S / O / A / P in-place and
 * approves. We track which fields the doctor edited so the backend can record
 * them in editedFields.
 */
export function ReviewPanel({
  consultationId,
  shareToken,
  transcript,
  flags,
  onApproved,
  onBack,
}) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [original, setOriginal] = useState(null);  // { subjective, objective, assessment, plan }
  const [draft, setDraft] = useState(null);
  const [edited, setEdited] = useState(new Set());
  const [selectedField, setSelectedField] = useState(null);  // which field's source lines to highlight
  const [approving, setApproving] = useState(false);
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    let alive = true;
    finalizeConsultation(consultationId, shareToken)
      .then((d) => {
        if (!alive) return;
        setOriginal(d.finalNote);
        setDraft(d.finalNote);
        setLoading(false);
      })
      .catch((e) => {
        if (!alive) return;
        setError(e.message);
        setLoading(false);
      });
    return () => { alive = false; };
  }, [consultationId, shareToken]);

  const setField = (key, text) => {
    setDraft((d) => ({
      ...d,
      [key]: { ...(d?.[key] || {}), text },
    }));
    setEdited((prev) => {
      const originalText = (original?.[key] || {}).text || "";
      const next = new Set(prev);
      if (text !== originalText) next.add(key);
      else next.delete(key);
      return next;
    });
  };

  const highlighted = useMemo(() => {
    if (!selectedField) return new Set();
    const src = (draft?.[selectedField]?.source_lines) || [];
    return new Set(src);
  }, [selectedField, draft]);

  const askApprove = () => {
    setConfirming(true);
  };

  const confirmApprove = async () => {
    setConfirming(false);
    setApproving(true);
    try {
      // Build an edits payload that only contains fields the doctor changed.
      const edits = {};
      for (const key of edited) edits[key] = draft[key];
      const result = await approveConsultation(consultationId, edits, shareToken);
      onApproved(result);
    } catch (e) {
      setError(e.message);
      setApproving(false);
    }
  };

  if (loading) return <div className="card" style={{ padding: 24 }}><Loading /></div>;
  if (error) return (
    <div className="card error">
      {error}
      <div style={{ marginTop: 8 }}>
        <button onClick={onBack}>Keep editing</button>
      </div>
    </div>
  );

  const fields = [
    { key: "subjective", label: "Subjective",
      hint: "What the patient tells you." },
    { key: "objective", label: "Objective",
      hint: "What you observe or measure." },
    { key: "assessment", label: "Assessment",
      hint: "AI only restates what the doctor said. You decide the assessment." },
    { key: "plan", label: "Plan",
      hint: "Medicines, tests, follow-up." },
  ];

  return (
    <div className="console-review">
      <FlagList flags={flags} />

      <div className="console-review-grid">
        <div className="console-review-fields">
          {fields.map((f) => {
            const value = (draft?.[f.key]?.text) || "";
            const srcLines = (draft?.[f.key]?.source_lines) || [];
            const isEdited = edited.has(f.key);
            return (
              <div className={`card review-field ${selectedField === f.key ? "active" : ""}`} key={f.key}>
                <div className="row between" style={{ alignItems: "center" }}>
                  <h3 style={{ margin: 0 }}>{f.label}</h3>
                  <div className="row small" style={{ gap: 6 }}>
                    {isEdited && <span className="pill watch">edited</span>}
                    {srcLines.length > 0 && (
                      <button
                        className="small"
                        onClick={() => setSelectedField(selectedField === f.key ? null : f.key)}
                        aria-pressed={selectedField === f.key}
                        aria-label={`Highlight source lines for ${f.label}`}
                      >
                        Source {`[${srcLines.join(", ")}]`}
                      </button>
                    )}
                  </div>
                </div>
                <textarea
                  rows={3}
                  value={value}
                  onChange={(e) => setField(f.key, e.target.value)}
                  placeholder={`${f.label} not mentioned yet`}
                  aria-label={f.label}
                />
                <p className="muted small" style={{ margin: 0 }}>{f.hint}</p>
              </div>
            );
          })}

          <div className="row" style={{ gap: 8, justifyContent: "flex-end", flexWrap: "wrap" }}>
            <button onClick={onBack}>Keep editing</button>
            <button className="primary" onClick={askApprove} disabled={approving}>
              {approving ? "Sending…" : "Approve and send to patient"}
            </button>
          </div>
        </div>

        <aside className="console-review-side">
          <details open>
            <summary><strong>Transcript</strong> <span className="muted small">({transcript.length} lines)</span></summary>
            <ul className="console-review-transcript">
              {transcript.map((ln, i) => (
                <li key={i} className={`${ln.speaker} ${highlighted.has(i) ? "hl" : ""}`}>
                  <span className="muted small">[{i}] {ln.speaker}:</span> {ln.text}
                </li>
              ))}
            </ul>
          </details>
        </aside>
      </div>

      {confirming && (
        <div className="console-confirm" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
          <div className="console-confirm-box card">
            <h3 id="confirm-title" style={{ marginTop: 0 }}>Approve and send?</h3>
            <p>This note will appear on the patient's timeline.</p>
            <div className="row" style={{ gap: 8, justifyContent: "flex-end" }}>
              <button onClick={() => setConfirming(false)}>Cancel</button>
              <button className="primary" onClick={confirmApprove}>Yes, approve</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
