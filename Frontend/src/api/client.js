// API client. Source of truth for the backend contract.
// Every function returns the same shape as the matching export in mockData.js.
import * as mock from "../data/mockData.js";
import { goLogin } from "../routing.js";

const USE_MOCK = import.meta.env.VITE_USE_MOCK === "true";
// Empty = same origin (nginx or the Vite proxy). A loopback URL in .env only makes sense on the machine that runs the backend:
// opened from another device (a friend on the LAN) it would point at THEIR localhost and every call fails with "Failed to fetch".
const LOOPBACK = /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])(:|\/|$)/i;
const RAW = import.meta.env.VITE_API_URL || "";
const BASE = RAW && LOOPBACK.test(RAW) && typeof location !== "undefined" && !/^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname) ? "" : RAW;

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
    goLogin();
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

// ---------- accounts (Phase 8): email + password, patient or doctor ----------

// -> { demoLogin }  (true only when the server runs with DEMO_MODE=true)
export const getAuthConfig = () => (USE_MOCK ? delay({ demoLogin: true }) : request("/api/auth/config", { auth: false }));

// Offline build: an email containing "doctor" signs in as the mock doctor, anything else as the mock patient.
const mockSession = (email, name) =>
  /doctor/i.test(email)
    ? { token: "mock-doctor", profile: { id: "doc1", userId: "doc1", role: "doctor", name: name || "Dr. Suresh Menon", email, specialty: "General Medicine", hospital: "Caritas Hospital" } }
    : { ...structuredClone(mock.login), profile: { ...structuredClone(mock.login.profile), role: "patient", email } };

// -> { token, profile:{ role, name, email, ... } }.  body: { role, name, email, password, specialty?, hospital? }
export const registerAccount = (body) =>
  USE_MOCK ? delay(mockSession(body.email, body.name)) : request("/api/auth/register", { method: "POST", body, auth: false });

export const loginAccount = (email, password) =>
  USE_MOCK ? delay(mockSession(email)) : request("/api/auth/login", { method: "POST", body: { email, password }, auth: false });

// Patient side: invite a doctor.  -> { code: "K7M2-9QXA", expiresAt }
export const createInvite = () =>
  USE_MOCK
    ? delay({ code: "K7M2-9QXA", expiresAt: new Date(Date.now() + 24 * 3600e3).toISOString() })
    : request("/api/care/invite", { method: "POST" });

let MOCK_DOCTORS = [];
// -> [{ linkId, name, specialty, hospital, since }]
export const listMyDoctors = () => (USE_MOCK ? delay(MOCK_DOCTORS) : request("/api/care/doctors"));
export const removeDoctor = (linkId) => {
  if (USE_MOCK) {
    MOCK_DOCTORS = MOCK_DOCTORS.filter((d) => d.linkId !== linkId);
    return delay({ ok: true });
  }
  return request(`/api/care/doctors/${encodeURIComponent(linkId)}`, { method: "DELETE" });
};

// Doctor side.
// -> { patientId, name }
export const linkPatient = (code) => {
  if (USE_MOCK) {
    if (!/^[A-Z0-9-]{8,9}$/i.test(code.trim())) return Promise.reject(new Error("That code is not valid. Ask the patient for a new one (codes work once and expire after 24 hours)."));
    return delay({ patientId: "ammini01", name: "Ammini Varghese" });
  }
  return request("/api/doctor/link", { method: "POST", body: { code } });
};
// -> [{ patientId, name, age, gender, openAlerts, lastRecord, since }]
export const listDoctorPatients = () =>
  USE_MOCK
    ? delay([{ patientId: "ammini01", name: "Ammini Varghese", age: 62, gender: "Female", openAlerts: 3, lastRecord: "2026-09-24", since: new Date().toISOString() }])
    : request("/api/doctor/patients");
// -> { token, doctorName, expiresAt }  (token opens /console/:token, the existing consultation console)
export const startDoctorConsole = (patientId) =>
  USE_MOCK
    ? delay({ token: "demo-share", doctorName: "Dr. Suresh Menon", expiresAt: new Date(Date.now() + 8 * 3600e3).toISOString() })
    : request(`/api/doctor/patients/${encodeURIComponent(patientId)}/console-token`, { method: "POST" });

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

// ---------- hospital record import (Phase 6) ----------

// -> { imported:{timelineCards,observations,conditions,medicines}, total, duplicates, alreadyImported,
//      ignored:[{type,count}], skippedInvalid, records:[timeline item], alerts:[alert], message }
// Real: POST /api/import/fhir (Bundle JSON as the body, or multipart `file`, max 2 MB)
let MOCK_FHIR_DONE = false;
const mockFhir = () => {
  const out = structuredClone(MOCK_FHIR_DONE ? mock.fhirAlreadyImported : mock.fhirImportResult);
  MOCK_FHIR_DONE = true;
  return delay(out);
};

export const importFhirFile = (file) => {
  if (USE_MOCK) return mockFhir();
  const form = new FormData();
  form.append("file", file);
  return fetch(`${BASE}/api/import/fhir`, { method: "POST", body: form, headers: { Authorization: `Bearer ${getToken()}` } }).then(
    async (res) => {
      if (res.status === 401) {
        setToken(null);
        goLogin();
      }
      if (!res.ok) {
        let detail = res.statusText;
        try {
          detail = (await res.json()).detail ?? detail;
        } catch {}
        throw new Error(typeof detail === "string" ? detail : "Import failed");
      }
      return res.json();
    },
  );
};

// Fetches the fictional Aster Medcity bundle and posts it through the same import path.
export const importFhirSample = async () => {
  if (USE_MOCK) return mockFhir();
  const bundle = await request("/api/import/fhir/sample");
  return request("/api/import/fhir", { method: "POST", body: bundle });
};

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

// One spoken clip -> { transcript, partial_note, flags, suggestions, heard, added }
// Rejects with err.unavailable = true when server-side voice transcription cannot be used
// (not set up, quota used up, mock mode): the caller then falls back to browser speech recognition.
// Rejects with err.skip = true for a clip the server could not read (do not retry that clip).
export async function sendAudio(consultationId, blob, speaker, language, shareToken) {
  if (USE_MOCK) {
    const e = new Error("Voice transcription is not available in the offline demo.");
    e.unavailable = true;
    throw e;
  }
  const form = new FormData();
  const ext = (blob.type || "").includes("mp4") ? "m4a" : (blob.type || "").includes("ogg") ? "ogg" : "webm";
  form.append("file", blob, `clip.${ext}`);
  form.append("speaker", speaker || "unknown");
  if (language) form.append("language", language);
  const headers = {};
  if (shareToken) headers["X-Share-Token"] = shareToken;
  const res = await fetch(`${BASE}/api/consultations/${encodeURIComponent(consultationId)}/audio`, {
    method: "POST", body: form, headers,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch {}
    const e = new Error(typeof detail === "string" ? detail : "Request failed");
    e.status = res.status;
    if (res.status === 503) e.unavailable = true;
    if (res.status === 413 || res.status === 415 || res.status === 422) e.skip = true;
    throw e;
  }
  return res.json();
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
export function approveConsultation(consultationId, edits, shareToken, removedItems) {
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
    body: { edits: edits || {}, removedItems: removedItems || {} },
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

// ---------- reminders (Phase 5) ----------

let MOCK_REMINDER_SETTINGS = {
  remindersEnabled: false,
  channels: { phone: false, telegram: true, family: false },
  telegramChatId: "123456789",
  familyChatId: null,
  familyName: "Joseph",
  missedAfterMinutes: 60,
  telegramReady: true,
  demoMode: true,
};

// -> { remindersEnabled, channels:{phone,telegram,family}, telegramChatId, familyChatId,
//      familyName, missedAfterMinutes, telegramReady, demoMode }
// Real: GET /api/reminders/settings
export const getReminderSettings = () =>
  USE_MOCK ? delay(MOCK_REMINDER_SETTINGS) : request("/api/reminders/settings");

// Real: PUT /api/reminders/settings (same body shape as the GET response)
export const saveReminderSettings = (settings) => {
  if (USE_MOCK) {
    MOCK_REMINDER_SETTINGS = { ...MOCK_REMINDER_SETTINGS, ...settings };
    return delay(MOCK_REMINDER_SETTINGS);
  }
  const { remindersEnabled, channels, telegramChatId, familyChatId, familyName, missedAfterMinutes } = settings;
  return request("/api/reminders/settings", {
    method: "PUT",
    body: { remindersEnabled, channels, telegramChatId, familyChatId, familyName, missedAfterMinutes },
  });
};

// -> { ok: true }. On failure the server answers 400 with a plain-language detail,
// which `request` throws as Error(message).
// Real: POST /api/reminders/telegram/test
export const testTelegram = () =>
  USE_MOCK ? delay({ ok: true }) : request("/api/reminders/telegram/test", { method: "POST" });

// -> { sent, kind, medicine, clock, message } or { sent:false, error }
// Real: POST /api/demo/fire-reminder (404 unless the server has DEMO_MODE=true)
export const fireDemoReminder = () =>
  USE_MOCK
    ? delay({ sent: true, kind: "dose", medicine: "Glycomet 500", clock: "08:00", message: "Time for Glycomet 500. Take it after food. Open MediThread and tap Taken." })
    : request("/api/demo/fire-reminder", { method: "POST" });

// Real: POST /api/demo/fire-missed (404 unless DEMO_MODE=true)
export const fireDemoMissed = () =>
  USE_MOCK
    ? delay({ sent: true, kind: "missed", medicine: "Glycomet 500", clock: "08:00", message: "Joseph, Ammini has not marked Glycomet 500 as taken since 8:00 AM." })
    : request("/api/demo/fire-missed", { method: "POST" });

// ---------- demo reset + deep health (Phase 6, DEMO_MODE=true only) ----------

// -> { ok, deleted:{...counts}, restored:{documents,medicines,alerts}, telegramReminders:{on,chatIdSet,botReady} }
// Real: POST /api/demo/reset (404 unless the server has DEMO_MODE=true)
export const resetDemo = () =>
  USE_MOCK
    ? delay({
        ok: true,
        deleted: { uploadedDocuments: 1, importedRecords: 2, visitNotes: 1, consultations: 1 },
        restored: { documents: 8, medicines: 3, alerts: 3 },
        telegramReminders: { on: true, chatIdSet: true, botReady: true },
      })
    : request("/api/demo/reset", { method: "POST" });

// -> { allOk, database, redis, gemini, groq, telegram, scheduler } each { status: ok|fallback|down, detail }
// Real: GET /api/health/deep
export const getDeepHealth = () =>
  USE_MOCK
    ? delay({
        allOk: true,
        database: { status: "ok", detail: "Mock data" },
        redis: { status: "fallback", detail: "In-memory store" },
        gemini: { status: "ok", detail: "mock" },
        groq: { status: "ok", detail: "mock" },
        telegram: { status: "ok", detail: "mock" },
        scheduler: { status: "ok", detail: "mock" },
      })
    : request("/api/health/deep");

// ---------- profile, home readings, health check (Phase 7) ----------

let MOCK_PROFILE = null;

// -> profile (same shape as login.profile, plus city/lat/lng/profileComplete)
// Real: PUT /api/patients/me  (only the fields sent are changed)
export const updateProfile = (fields) => {
  if (USE_MOCK) {
    MOCK_PROFILE = { ...(MOCK_PROFILE || mock.login.profile), ...fields, profileComplete: true };
    return delay(MOCK_PROFILE);
  }
  return request("/api/patients/me", { method: "PUT", body: fields });
};

// body: { date?, sbp?, dbp?, pulse?, spo2?, weight?, temp?, sugar?, sugarType? }
// -> { record, risks, alerts }
// Real: POST /api/patients/me/vitals
export const addVitals = (vitals) =>
  USE_MOCK
    ? delay({ record: { id: "mockv", date: new Date().toISOString().slice(0, 10), type: "vitals", title: "Home reading", items: [] },
              risks: mockRisksFor(vitals), alerts: mock.alerts })
    : request("/api/patients/me/vitals", { method: "POST", body: vitals });

function mockRisksFor(v) {
  if (v?.sbp >= 180 || v?.dbp >= 120)
    return [{ key: "bp", level: "emergency", title: "Very high blood pressure", specialist: "Emergency", reason: "bp_crisis", emergency: true,
              message: `Your blood pressure was ${v.sbp}/${v.dbp} mmHg today. This is in the danger zone. Call 108 if you have chest pain, a bad headache or weakness.`, evidence: [] }];
  if (v?.sbp >= 140 || v?.dbp >= 90)
    return [{ key: "bp", level: "high", title: "High blood pressure", specialist: "Cardiologist", reason: "high_bp", emergency: false,
              message: `Your blood pressure was ${v.sbp}/${v.dbp} mmHg today. The usual target is below 130/80. Please see a doctor in the next few days.`, evidence: [] }];
  return [];
}

const MOCK_HEALTH_CHECK = {
  risks: [
    { key: "ldl", level: "watch", title: "LDL cholesterol above target", specialist: "General Physician", reason: "cholesterol", emergency: false,
      message: "Your LDL (bad cholesterol) was 142 mg/dL on 2025-03-12, above the target of 100. Mention it at your next visit.",
      messageMl: "നിങ്ങളുടെ LDL 142 mg/dL ആയിരുന്നു, 100 ലക്ഷ്യത്തേക്കാൾ കൂടുതൽ.", evidence: [{ code: "ldl", name: "LDL cholesterol", value: 142, unit: "mg/dL", date: "2025-03-12" }] },
  ],
  review: {
    source: "ai",
    headline: "Your sugar control has improved a lot since 2024, but cholesterol is still above target.",
    headlineMl: "2024 മുതൽ പഞ്ചസാര നിയന്ത്രണം വളരെ മെച്ചപ്പെട്ടു, പക്ഷേ കൊളസ്ട്രോൾ ഇപ്പോഴും ലക്ഷ്യത്തിന് മുകളിലാണ്.",
    points: [
      { kind: "better", text: "HbA1c fell from 9.1% (Nov 2024) to 7.2% (Sep 2026), close to the 7% target.", textMl: "HbA1c 9.1%-ൽ നിന്ന് 7.2% ആയി കുറഞ്ഞു.", tests: ["hba1c"] },
      { kind: "worse", text: "LDL was 142 mg/dL in March 2025, above the target of 100.", textMl: "LDL 142 mg/dL ആയിരുന്നു, 100-ന് മുകളിൽ.", tests: ["ldl"] },
      { kind: "missing", text: "There is no kidney test (creatinine) in the last year. People on Glycomet usually have one yearly.", textMl: "കഴിഞ്ഞ വർഷം വൃക്ക പരിശോധന ഇല്ല.", tests: ["creatinine"] },
    ],
    askDoctor: [
      { text: "Is my cholesterol now on target with Atorva 20?", textMl: "Atorva 20 കൊണ്ട് കൊളസ്ട്രോൾ ലക്ഷ്യത്തിലെത്തിയോ?" },
      { text: "When should I have a kidney test?", textMl: "വൃക്ക പരിശോധന എപ്പോൾ ചെയ്യണം?" },
    ],
  },
  emergency: false, specialist: "General Physician", reason: "cholesterol", checkedAt: new Date().toISOString(),
};

// -> { risks:[{key,level,title,message,messageMl,specialist,evidence,reason,emergency}],
//      review:{headline,headlineMl,points:[{text,textMl,kind,tests}],askDoctor:[{text,textMl}],source},
//      emergency, specialist, reason, checkedAt }
// Real: GET /api/patients/me/health-check
export const getHealthCheck = () => (USE_MOCK ? delay(MOCK_HEALTH_CHECK) : request("/api/patients/me/health-check"));

// ---------- doctor finder (Phase 7, FICTIONAL sample directory) ----------

const qs = (params) => {
  const u = new URLSearchParams();
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "" && v !== false) u.set(k, String(v));
  });
  const s = u.toString();
  return s ? `?${s}` : "";
};

const INDIA_BOUNDS = { south: 6.0, north: 37.6, west: 68.0, east: 97.5 };

// Mock mode: rank the bundled sample file by distance + rating so the offline build still works.
async function mockSearch({ lat, lng, city, specialty, emergency } = {}) {
  const { doctors } = (await import("../data/doctors.sample.json")).default;
  const cities = mockCities(doctors);
  const c = cities.find((x) => x.city === city) || cities.find((x) => x.city === "Kochi");
  const inIndia = lat != null && lng != null && lat >= INDIA_BOUNDS.south && lat <= INDIA_BOUNDS.north && lng >= INDIA_BOUNDS.west && lng <= INDIA_BOUNDS.east;
  const origin = inIndia ? { lat, lng, label: "Your location", source: "device" } : { lat: c.lat, lng: c.lng, label: c.city, source: city ? "city" : "default" };
  const spec = emergency ? "Emergency" : specialty;
  const km = (d) => {
    const R = 6371, toR = Math.PI / 180;
    const dLat = (d.lat - origin.lat) * toR, dLng = (d.lng - origin.lng) * toR;
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(origin.lat * toR) * Math.cos(d.lat * toR) * Math.sin(dLng / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(h));
  };
  let results = doctors
    .filter((d) => !spec || d.specialty === spec || d.specialties.includes(spec) || (spec === "Emergency" && d.emergency24x7))
    .map((d) => {
      const dist = Math.round(km(d) * 10) / 10;
      const score = Math.round((34 * Math.exp(-dist / 12) + ((d.rating * d.reviews + 100) / (d.reviews + 25) - 3.5) / 1.5 * 30) * 10) / 10;
      return { ...d, distanceKm: dist, openNow: true, closesAt: d.emergency24x7 ? null : "19:00", score,
               department: spec && d.specialty !== spec && d.type === "hospital" ? spec : null };
    })
    .sort((a, b) => (spec === "Emergency" ? a.distanceKm - b.distanceKm : b.score - a.score))
    .slice(0, 12);
  const picks = results.slice(0, 3).map((d) => ({
    id: d.id, source: "rules",
    why: `${d.department ? `${d.clinic} (${d.department} department)` : `${d.name} (${d.specialty})`}: ${d.distanceKm} km away, rated ${d.rating} from ${d.reviews} reviews, speaks Malayalam.`,
    reviewSummary: `People say: ${d.reviewSnippets[0].toLowerCase()}`,
  }));
  return { origin, specialty: spec || null, results, picks, relaxed: [], nearbyGp: [], bounds: INDIA_BOUNDS, sample: true };
}

function mockCities(doctors) {
  const acc = {};
  doctors.forEach((d) => {
    const c = (acc[d.city] ||= { city: d.city, district: d.district, state: d.state, lat: 0, lng: 0, doctors: 0 });
    c.lat += d.lat; c.lng += d.lng; c.doctors += 1;
  });
  return Object.values(acc).map((c) => ({ ...c, lat: c.lat / c.doctors, lng: c.lng / c.doctors }))
    .sort((a, b) => (a.state !== "Kerala") - (b.state !== "Kerala") || a.city.localeCompare(b.city));
}

// -> [{ city, district, state, lat, lng, doctors }]
// Real: GET /api/doctors/cities
export const getDoctorCities = async () =>
  USE_MOCK ? mockCities((await import("../data/doctors.sample.json")).default.doctors) : request("/api/doctors/cities");

// params: { lat, lng, city, specialty, language, day, openNow, emergency, teleconsult, maxKm, maxFee, minRating, limit }
// -> { origin:{lat,lng,label,source,outsideIndia}, specialty, results:[doctor + distanceKm, openNow, closesAt, score, department],
//      picks:[{id, why, whyMl, reviewSummary, reviewSummaryMl, source}], relaxed:[str], nearbyGp:[doctor], bounds, sample }
// Real: GET /api/doctors/nearby
export const getNearbyDoctors = (params) =>
  USE_MOCK ? mockSearch(params) : request(`/api/doctors/nearby${qs(params)}`);

// -> same as nearby + { filters, filtersSource: "ai"|"rules"|"ai+rules", query }
// Real: POST /api/doctors/ask
export const askDoctors = async (q, lat, lng) =>
  USE_MOCK
    ? { ...(await mockSearch({ lat, lng, specialty: /heart|bp|cardio/i.test(q) ? "Cardiologist" : null })), filters: {}, filtersSource: "rules", query: q }
    : request("/api/doctors/ask", { method: "POST", body: { q, lat, lng } });

// -> same as nearby + { risk, risks, emergency, bring:[{text,textMl}] }
// Real: GET /api/doctors/recommend
export const getDoctorRecommendation = async (params) =>
  USE_MOCK
    ? { ...(await mockSearch({ ...params, specialty: "General Physician" })), risk: MOCK_HEALTH_CHECK.risks[0], risks: MOCK_HEALTH_CHECK.risks,
        emergency: false, bring: [{ text: "Your medicine list: Glycomet 500, Telma 40, Atorva 20" }, { text: "Allergies: Sulfa drugs" }] }
    : request(`/api/doctors/recommend${qs(params)}`);

// ---------- agent ----------

// Typed requests go to the backend Agent Engine. Offline/mock build has no engine, so callers fall back to local actions.
export const agentAvailable = () => !USE_MOCK;
export const agentChat = (text, conversationId, fileId) => request("/api/agent/chat", { method: "POST", body: { text, conversationId, fileId: fileId || undefined } });
export const agentConfirm = (id, approve) => request("/api/agent/confirm", { method: "POST", body: { id, approve } });
export const agentUploadFile = async (file) => {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${BASE}/api/agent/files`, { method: "POST", headers: { Authorization: `Bearer ${getToken()}` }, body: fd });
  if (res.status === 401) { setToken(null); goLogin(); }
  if (!res.ok) {
    let d = res.statusText;
    try { d = (await res.json()).detail ?? d; } catch {}
    throw new Error(typeof d === "string" ? d : "Upload failed");
  }
  return res.json();
};
export const agentSetFileType = (fileId, type) => request(`/api/agent/files/${fileId}/type`, { method: "POST", body: { type } });
export const agentTask = (id) => request(`/api/agent/tasks/${id}`);
export const agentCancel = (id) => request(`/api/agent/tasks/${id}/cancel`, { method: "POST" });
// Authenticated download of one of the person's own files (the browser cannot send the bearer token on a plain link).
export const agentDownload = async (fileId, name) => {
  const res = await fetch(`${BASE}/api/agent/files/${fileId}/content`, { headers: { Authorization: `Bearer ${getToken()}` } });
  if (!res.ok) throw new Error(res.status === 404 ? "That file has expired. Ask me to make it again." : "Download failed");
  const url = URL.createObjectURL(await res.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: name || "document.pdf" });
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
};
export const agentShareQr = (ref) => request(`/api/agent/shares/${ref}`);

// ---------- doctor agent (one linked patient per call; the server re-checks the care link every time) ----------
export const doctorAgentChat = (text, patientId, conversationId, fileId) =>
  request("/api/doctor-agent/chat", { method: "POST", body: { text, patientId, conversationId, fileId: fileId || undefined } });
export const doctorAgentTask = (id) => request(`/api/doctor-agent/tasks/${id}`);
export const doctorAgentConfirm = (id, patientId, approve) => request("/api/doctor-agent/confirm", { method: "POST", body: { id, patientId, approve } });
export const doctorAgentUpload = async (patientId, file) => {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${BASE}/api/doctor-agent/files?patientId=${encodeURIComponent(patientId)}`, { method: "POST", headers: { Authorization: `Bearer ${getToken()}` }, body: fd });
  if (res.status === 401) { setToken(null); goLogin(); }
  if (!res.ok) {
    let d = res.statusText;
    try { d = (await res.json()).detail ?? d; } catch {}
    throw new Error(typeof d === "string" ? d : "Upload failed");
  }
  return res.json();
};
export const doctorAgentDownload = async (patientId, fileId, name) => {
  const res = await fetch(`${BASE}/api/doctor-agent/files/${fileId}/content?patientId=${encodeURIComponent(patientId)}`, { headers: { Authorization: `Bearer ${getToken()}` } });
  if (!res.ok) throw new Error(res.status === 404 ? "That file has expired. Ask me to make it again." : "Download failed");
  const url = URL.createObjectURL(await res.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: name || "document.pdf" });
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
};
