// API client. Source of truth for the backend contract.
// Every function returns the same shape as the matching export in mockData.js.
import * as mock from "../data/mockData.js";

const USE_MOCK = import.meta.env.VITE_USE_MOCK === "true";
const BASE = import.meta.env.VITE_API_URL || ""; // empty = same origin, Vite proxies /api

const TOKEN_KEY = "medithread_token";

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
