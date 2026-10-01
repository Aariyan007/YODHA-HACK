import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
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

/**
 * Doctor console. Routed at /console/:token.
 *
 * Not behind the patient login guard — the share token in the URL is the only
 * credential the backend needs for the consultation endpoints.
 *
 * State machine: history → recording → review → approved. The in-progress
 * consultationId and transcript live in React state only (no localStorage).
 * If the page refreshes mid-visit, we offer a Restore button that calls
 * getConsultation to rehydrate from the server.
 */
export default function DoctorConsole() {
  const { token } = useParams();
  const navigate = useNavigate();

  // Patient history (shared snapshot).
  const [snapshot, setSnapshot] = useState(null);
  const [snapshotError, setSnapshotError] = useState(null);

  // Doctor identity.
  const [doctorName, setDoctorName] = useState("Dr. Suresh Menon");

  // State machine.
  const [phase, setPhase] = useState("history"); // history | recording | review | approved
  const [busy, setBusy] = useState(false);
  const [startError, setStartError] = useState(null);

  // Consultation state (populated once /start succeeds).
  const [consultationId, setConsultationId] = useState(null);
  const [consultState, setConsultState] = useState({
    transcript: [],
    flags: [],
    suggestions: [],
    partial_note: { subjective: null, objective: null, assessment: null, plan: null },
  });
  const [autoFeedScript, setAutoFeedScript] = useState(null);
  const [approvedResult, setApprovedResult] = useState(null);

  // Load the share snapshot once.
  useEffect(() => {
    let alive = true;
    getShareSnapshot(token, "Doctor Console")
      .then((d) => alive && setSnapshot(d))
      .catch((e) => alive && setSnapshotError(e.message));
    return () => {
      alive = false;
    };
  }, [token]);

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
      // RecordingPanel enqueues this script line-by-line through the same
      // queue the mic uses — same retry, same ordering guarantees.
      setAutoFeedScript(consultationScript);
      setPhase("recording");
    } catch (e) {
      setStartError(e.message);
    } finally {
      setBusy(false);
    }
  };

  // ---- rendering ----

  if (snapshotError) {
    return (
      <div className="console-shell">
        <ConsoleHeader />
        <div className="card error" style={{ margin: 16 }}>
          Could not load patient history: {snapshotError}
          <div style={{ marginTop: 8 }}>
            <button onClick={() => navigate("/")}>Back</button>
          </div>
        </div>
      </div>
    );
  }
  if (!snapshot) {
    return (
      <div className="console-shell">
        <ConsoleHeader />
        <div style={{ padding: 16 }}><Loading /></div>
      </div>
    );
  }

  return (
    <div className="console-shell">
      <ConsoleHeader patientName={snapshot.patient?.name} phase={phase} />
      <main className="console-main">
        {startError && <div className="card error" style={{ marginBottom: 12 }}>{startError}</div>}

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

function ConsoleHeader({ patientName, phase }) {
  return (
    <header className="console-top">
      <div>
        <span className="brand">MediThread · Doctor console</span>
        {patientName && <span className="muted" style={{ marginLeft: 8 }}>· {patientName}</span>}
      </div>
      {phase && phase !== "history" && (
        <span className="muted small" aria-live="polite">
          {phase === "recording" && "Recording"}
          {phase === "review" && "Review & edit"}
          {phase === "approved" && "Approved"}
        </span>
      )}
    </header>
  );
}

