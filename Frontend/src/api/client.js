// API client. Source of truth for the backend contract.
// Every function returns the same shape as the matching export in mockData.js.
import * as mock from "../data/mockData.js";

const USE_MOCK = import.meta.env.VITE_USE_MOCK === "true";
const BASE = import.meta.env.VITE_API_URL || ""; // empty = same origin, Vite proxies /api

const TOKEN_KEY = "medithread_token";

// Pipeline stages in order. Shared with the Upload page UI.
export const STAGES = ["read", "understand", "code", "explain", "check"];

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t) => (t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY));

const delay = (data) => new Promise((r) => setTimeout(() => r(structuredClone(data)), 250));

async function request(path, { method = "GET", body, auth = true } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth && getToken()) headers.Authorization = `Bearer ${getToken()}`;
  const res = await fetch(`${BASE}${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined });
  if (res.status === 401 && auth) {
    setToken(null);
    window.location.assign("/login");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {}
    throw new Error(typeof detail === "string" ? detail : "Request failed");
  }
  return res.json();
}

// ---------- auth ----------

// -> { ok, phone, expiresIn, demo }
export const requestOtp = (phone) =>
  USE_MOCK
    ? delay({ ok: true, phone, expiresIn: 300, demo: true })
    : request("/api/auth/otp/request", { method: "POST", body: { phone }, auth: false });

// -> { token, profile }
export const verifyOtp = (phone, otp) =>
  USE_MOCK ? delay(mock.login) : request("/api/auth/otp/verify", { method: "POST", body: { phone, otp }, auth: false });

// ---------- patient ----------

export const getTimeline = () => (USE_MOCK ? delay(mock.timeline) : request("/api/patients/me/timeline"));
export const getAlerts = () => (USE_MOCK ? delay(mock.alerts) : request("/api/patients/me/alerts"));
export const getInsights = () => (USE_MOCK ? delay(mock.insights) : request("/api/patients/me/insights"));
export const getMedicines = () => (USE_MOCK ? delay(mock.medicines) : request("/api/patients/me/medicines"));
export const getReminders = () => (USE_MOCK ? delay(mock.reminders) : request("/api/patients/me/reminders"));
export const getAccessLog = () => (USE_MOCK ? delay(mock.accessLog) : request("/api/patients/me/access-log"));
export const getFamily = () => (USE_MOCK ? delay(mock.family) : request("/api/patients/me/family"));

// -> { key, date, taken: true }
export const markReminderTaken = (key) =>
  USE_MOCK
    ? delay({ key, date: mock.reminders[0]?.date, taken: true })
    : request(`/api/patients/me/reminders/${encodeURIComponent(key)}/taken`, { method: "POST" });

// ---------- shares ----------

// -> { token, url, scope, expiresAt }
export const createShare = (hours = 24, scope = "full") =>
  USE_MOCK ? delay({ ...mock.share, scope }) : request("/api/shares", { method: "POST", body: { hours, scope } });

// -> { patient, scope, expiresAt, timeline, medicines, alerts, insights }
export const getShareSnapshot = (token, viewer) =>
  USE_MOCK
    ? delay(mock.snapshot)
    : request(`/api/shares/${encodeURIComponent(token)}/snapshot${viewer ? `?viewer=${encodeURIComponent(viewer)}` : ""}`, {
        auth: false,
      });

// ---------- document upload (SSE pipeline) ----------

// Upload one file + listen to stage events over Server-Sent Events.
// callbacks: { onStage(stage), onDone(result), onError(message) }
export function uploadDocument(file, callbacks = {}) {
  const { onStage = () => {}, onDone = () => {}, onError = () => {} } = callbacks;

  if (USE_MOCK) {
    let i = 0;
    const timer = setInterval(() => {
      if (i < STAGES.length) {
        onStage(STAGES[i++]);
      } else {
        clearInterval(timer);
        onDone(structuredClone(mock.demoUpload));
      }
    }, 350);
    return { cancel: () => clearInterval(timer) };
  }

  const form = new FormData();
  form.append("file", file);
  const headers = {};
  if (getToken()) headers.Authorization = `Bearer ${getToken()}`;

  let source;
  fetch(`${BASE}/api/documents`, { method: "POST", body: form, headers })
    .then(async (r) => {
      if (!r.ok) {
        let msg = r.statusText;
        try {
          msg = (await r.json()).detail ?? msg;
        } catch {}
        throw new Error(typeof msg === "string" ? msg : "Upload failed");
      }
      return r.json();
    })
    .then(({ jobId }) => {
      // EventSource cannot send Authorization headers; the unguessable jobId is the key.
      source = new EventSource(`${BASE}/api/jobs/${encodeURIComponent(jobId)}/events`);
      source.onmessage = (ev) => {
        let data;
        try {
          data = JSON.parse(ev.data);
        } catch {
          return;
        }
        if (data.stage) onStage(data.stage);
        else if (data.error) {
          source.close();
          onError(data.error);
        } else if (data.done) {
          source.close();
          onDone(data.result);
        }
      };
      source.onerror = () => {
        source.close();
        onError("Lost connection to the server. Please try again.");
      };
    })
    .catch((e) => onError(e.message));

  return {
    cancel: () => {
      if (source) source.close();
    },
  };
}

// -> { urgent, specialist, why }
export const triage = (text) =>
  USE_MOCK
    ? delay(mock.mockTriage(text))
    : request("/api/triage", { method: "POST", body: { text }, auth: false });

// ---------- consultation (doctor console, Phase 4) ----------
//
// Doctor-side flow is NOT authenticated with the patient JWT. The share token
// identifies the authorized visit; every call after /start sends it as the
// X-Share-Token header. (The backend validates expiry on every call.)

const MOCK_CID = "cons-mock";
let MOCK_STATE = null; // reset each /start

async function shareReq(path, { method = "GET", body, shareToken } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (shareToken) headers["X-Share-Token"] = shareToken;
  const res = await fetch(`${BASE}${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch {}
    throw new Error(typeof detail === "string" ? detail : "Request failed");
  }
  return res.json();
}

// -> { consultationId }
export function startConsultation(shareToken, doctorName) {
  if (USE_MOCK) {
    MOCK_STATE = null;
    return delay({ consultationId: MOCK_CID });
  }
  // Real: POST /api/consultations/start (no auth; patient share token is in body)
  return shareReq("/api/consultations/start", {
    method: "POST",
    body: { patientToken: shareToken, doctorName },
  });
}

// -> { transcript, partial_note, flags, suggestions }
export function sendLine(consultationId, text, speaker, shareToken) {
  if (USE_MOCK) {
    MOCK_STATE = mock.mockLineStep(MOCK_STATE, speaker, text);
    return delay(MOCK_STATE);
  }
  // Real: POST /api/consultations/{id}/line
  return shareReq(`/api/consultations/${encodeURIComponent(consultationId)}/line`, {
    method: "POST",
    body: { text, speaker },
    shareToken,
  });
}

// -> consultation shape (incl. finalNote with per-field source_lines)
export function finalizeConsultation(consultationId, shareToken) {
  if (USE_MOCK) {
    return delay({
      id: MOCK_CID,
      status: "draft",
      transcript: MOCK_STATE?.transcript || [],
      soap: MOCK_STATE?.partial_note || {},
      finalNote: mock.mockFinalNote,
      flags: MOCK_STATE?.flags || [],
      questions: MOCK_STATE?.suggestions || [],
      editedFields: [],
    });
  }
  return shareReq(`/api/consultations/${encodeURIComponent(consultationId)}/finalize`, {
    method: "POST",
    shareToken,
  });
}

// -> { record, alerts, reminders }
export function approveConsultation(consultationId, edits, shareToken) {
  if (USE_MOCK) {
    const merged = structuredClone(mock.mockApprovedRecord);
    for (const k of ["subjective", "objective", "assessment", "plan"]) {
      if (edits && edits[k] && typeof edits[k].text === "string") {
        // Mock does not need to re-synth summary; just acknowledge the edit.
        merged.record.title = merged.record.title; // no-op; keep shape stable
      }
    }
    return delay(merged);
  }
  return shareReq(`/api/consultations/${encodeURIComponent(consultationId)}/approve`, {
    method: "POST",
    body: { edits: edits || {} },
    shareToken,
  });
}

// -> consultation state (used after a page refresh to restore the view)
export function getConsultation(consultationId, shareToken) {
  if (USE_MOCK) {
    return delay({
      id: MOCK_CID,
      status: MOCK_STATE?.transcript?.length ? "active" : "active",
      transcript: MOCK_STATE?.transcript || [],
      soap: MOCK_STATE?.partial_note || {},
      finalNote: {},
      flags: MOCK_STATE?.flags || [],
      questions: MOCK_STATE?.suggestions || [],
      editedFields: [],
    });
  }
  return shareReq(`/api/consultations/${encodeURIComponent(consultationId)}`, { shareToken });
}

// Feeds the scripted 14-line conversation one line at a time, calling
// onLine(state, index) after each response so the UI can animate it.
export async function runDemoConversation(consultationId, shareToken, onLine) {
  const script = mock.consultationScript;
  let last;
  for (let i = 0; i < script.length; i++) {
    const [speaker, text] = script[i];
    try {
      last = await sendLine(consultationId, text, speaker, shareToken);
    } catch (e) {
      onLine && onLine({ error: e.message, index: i }, i);
      throw e;
    }
    onLine && onLine(last, i);
    // Small pause so the demo reads as a conversation, not a dump.
    await new Promise((r) => setTimeout(r, 450));
  }
  return last;
}
