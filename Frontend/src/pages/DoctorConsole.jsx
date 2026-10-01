import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { gsap } from "gsap";
import {
  approveConsultation,
  finalizeConsultation,
  getShareSnapshot,
  startConsultation,
} from "../api/client.js";
import { consultationScript } from "../data/mockData.js";
import { Loading } from "../components/ui.jsx";
import { HistoryPanel } from "../components/console/HistoryPanel.jsx";
import { RecordingPanel } from "../components/console/RecordingPanel.jsx";
import { ReviewPanel } from "../components/console/ReviewPanel.jsx";
import { ApprovedPanel } from "../components/console/ApprovedPanel.jsx";
import { useT } from "../i18n.js";

const PHASE_LABELS = {
  recording: "Recording",
  review:    "Review & edit",
  approved:  "Approved",
};

// ── Phase progress bar ────────────────────────────────────────
function PhaseBar({ phase }) {
  const phases = ["history", "recording", "review", "approved"];
  const idx    = phases.indexOf(phase);
  return (
    <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
      {phases.filter((p) => p !== "history").map((p, i) => (
        <div
          key={p}
          title={p}
          style={{
            width:  32,
            height: 4,
            borderRadius: 9999,
            background: i < idx
              ? "var(--good)"
              : i === idx - 1
                ? "var(--accent)"
                : "var(--border-strong)",
            transition: "background 0.3s ease",
          }}
        />
      ))}
      {phase !== "history" && (
        <span style={{ fontSize: "var(--font-size-xs)", color: "var(--text-3)", marginLeft: 6 }}>
          {PHASE_LABELS[phase]}
        </span>
      )}
    </div>
  );
}

// ── Console header ────────────────────────────────────────────
function ConsoleHeader({ patientName, phase }) {
  return (
    <header className="console-top" role="banner">
      <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-3)" }}>
        <span className="brand" aria-label="MediThread Doctor Console">MediThread</span>
        <span style={{
          fontSize: "var(--font-size-xs)",
          background: "var(--accent-subtle)",
          color: "var(--accent-text)",
          border: "1px solid var(--accent-border)",
          borderRadius: "var(--r-full)",
          padding: "2px 8px",
          fontWeight: 600,
          letterSpacing: "0.04em",
        }}>
          Doctor Console
        </span>
        {patientName && (
          <span style={{ color: "var(--text-3)", fontSize: "var(--font-size-sm)" }}>
            · {patientName}
          </span>
        )}
      </div>
      <PhaseBar phase={phase || "history"} />
    </header>
  );
}

export default function DoctorConsole() {
  const { token }    = useParams();
  const navigate     = useNavigate();
  const mainRef      = useRef(null);

  const [snapshot,     setSnapshot]     = useState(null);
  const [snapshotError,setSnapshotError]= useState(null);
  const [doctorName,   setDoctorName]   = useState("Dr. Suresh Menon");
  const [phase,        setPhase]        = useState("history");
  const [busy,         setBusy]         = useState(false);
  const [startError,   setStartError]   = useState(null);
  const [consultationId,setConsultationId] = useState(null);
  const [consultState, setConsultState] = useState({
    transcript: [], flags: [], suggestions: [],
    partial_note: { subjective: null, objective: null, assessment: null, plan: null },
  });
  const [autoFeedScript, setAutoFeedScript] = useState(null);
  const [approvedResult, setApprovedResult] = useState(null);

  useEffect(() => {
    let alive = true;
    getShareSnapshot(token, "Doctor Console")
      .then((d) => alive && setSnapshot(d))
      .catch((e) => alive && setSnapshotError(e.message));
    return () => { alive = false; };
  }, [token]);

  // Animate phase transitions
  useEffect(() => {
    if (!mainRef.current) return;
    gsap.fromTo(mainRef.current,
      { opacity: 0, y: 12 },
      { opacity: 1, y: 0, duration: 0.35, ease: "power2.out" }
    );
  }, [phase]);

  const begin = async () => {
    setStartError(null);
    setBusy(true);
    try {
      const { consultationId: id } = await startConsultation(token, doctorName);
      setConsultationId(id);
      setAutoFeedScript(null);
      setPhase("recording");
    } catch (e) {
      setStartError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const playDemo = async () => {
    setStartError(null);
    setBusy(true);
    try {
      const { consultationId: id } = await startConsultation(token, doctorName);
      setConsultationId(id);
      setAutoFeedScript(consultationScript);
      setPhase("recording");
    } catch (e) {
      setStartError(e.message);
    } finally {
      setBusy(false);
    }
  };

  if (snapshotError) {
    return (
      <div className="console-shell">
        <ConsoleHeader />
        <div className="page-shell">
          <div className="card-alert" style={{ borderRadius: "var(--r-lg)", padding: "var(--sp-5)" }}>
            <p className="text-alert font-medium">Could not load patient history: {snapshotError}</p>
            <button style={{ marginTop: "var(--sp-3)" }} onClick={() => navigate("/")}>
              Back
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!snapshot) {
    return (
      <div className="console-shell">
        <ConsoleHeader />
        <div className="page-shell"><Loading /></div>
      </div>
    );
  }

  return (
    <div className="console-shell">
      <ConsoleHeader patientName={snapshot.patient?.name} phase={phase} />
      <main className="page-shell" ref={mainRef}>
        {startError && (
          <div className="card-alert" style={{ borderRadius: "var(--r-lg)", padding: "var(--sp-4)", marginBottom: "var(--sp-4)" }}>
            {startError}
          </div>
        )}

        {phase === "history" && (
          <HistoryPanel
            snapshot={snapshot}
            doctorName={doctorName}
            setDoctorName={setDoctorName}
            onStart={begin}
            onDemo={playDemo}
            busy={busy}
          />
        )}

        {phase === "recording" && (
          <RecordingPanel
            consultationId={consultationId}
            shareToken={token}
            initialState={consultState}
            autoFeed={autoFeedScript}
            onStop={(finalState) => {
              setConsultState(finalState);
              setPhase("review");
            }}
          />
        )}

        {phase === "review" && (
          <ReviewPanel
            consultationId={consultationId}
            shareToken={token}
            transcript={consultState.transcript}
            flags={consultState.flags}
            onBack={() => setPhase("recording")}
            onApproved={(result) => {
              setApprovedResult(result);
              setPhase("approved");
            }}
          />
        )}

        {phase === "approved" && approvedResult && (
          <ApprovedPanel
            result={approvedResult}
            patient={snapshot.patient}
            onNewConsultation={() => {
              setConsultationId(null);
              setConsultState({
                transcript: [], flags: [], suggestions: [],
                partial_note: { subjective: null, objective: null, assessment: null, plan: null },
              });
              setAutoFeedScript(null);
              setApprovedResult(null);
              setPhase("history");
            }}
            onBack={() => setPhase("history")}
          />
        )}
      </main>
    </div>
  );
}
