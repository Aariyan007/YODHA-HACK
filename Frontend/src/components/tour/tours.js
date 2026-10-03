// What each tour shows. A step is { route, target, title, text }. `target` is a list of CSS selectors, the first one found wins. If none is
// found (or none given) the card is centred, so a missing element never breaks the tour. Nav links are matched by the end of their href,
// which works in both the normal build (/upload) and the offline hash build (#/upload).
const nav = (path) => `.tabs a[href$="${path}"]`;

const S = {
  welcome: { title: "Welcome to MediThread", text: "Your prescriptions, reports and visits in one health thread, with an assistant that explains them and helps you act. This takes about a minute." },
  home: { route: "/", target: ["#main-content h1"], title: "Home: your health at a glance", text: "Your latest readings, warnings and today's medicines. Anything that needs attention shows up here first." },
  upload: { route: "/upload", target: [".dropzone", nav("/upload")], title: "Add a report or prescription", text: "Drop a photo or PDF here, or tap to choose one. It is read in seconds, checked for medicine clashes and allergies, and added to your thread." },
  timeline: { route: "/timeline", target: ["#main-content h1", nav("/timeline")], title: "Your health thread", text: "Every record in date order. Tap any point to see the record behind it, and the cards below show each document." },
  medicines: { route: "/medicines", target: ["#main-content h1", nav("/medicines")], title: "Medicines and doses", text: "What you take, how much, when, and how many days are left. The assistant can also check for bad combinations and side effects." },
  reminders: { route: "/reminders", target: [".toggle", nav("/reminders")], title: "Reminders on Telegram", text: "Turn on reminders to get a message at each dose time, and an hourly nudge until you mark it taken. You need to message the MediThread bot first." },
  reading: { route: "/insights", target: [".checkself", nav("/insights")], title: "Log a reading", text: "Type your blood pressure, sugar or pulse. You see how it compares with your last one, and it is saved to your thread." },
  doctors: { route: "/doctors", target: [".mt-ask", "#main-content h1", nav("/doctors")], title: "Find the right doctor", text: "Doctors matched to your record, not just the nearest. Use Which doctor? to describe a symptom and get a suggestion. These are sample doctors in this demo." },
  share: { route: "/sharing", target: [".mt-invite", "#main-content h1", nav("/sharing")], title: "Share with your doctor", text: "Make a QR or link a doctor can open, or an invite code to link their account. You choose what they see and can stop access any time." },
  agent: { target: [".ag-launch"], title: "Ask the assistant", text: "Type or tap the microphone, in English, Malayalam or a mix. Tap the paperclip to give it a photo or PDF. It always asks Yes or No before it saves or shares anything.", last: true },
  doctorWelcome: { title: "Welcome, doctor", text: "Link your patients with a one-time code, review their record before the visit, and speak the consultation to get a draft note. Nothing reaches a patient until you approve it. This takes under a minute." },
  doctorAgent: { target: [".ag-launch"], title: "Ask the assistant", text: "Ask for a brief of a patient, what changed since the last visit, or missing information. It reads the linked record only, and never saves or sends anything without your Yes.", last: true },
  doctorHome: { route: "/doctor", target: ["#main-content section.card", "#main-content .page-header"], title: "Your patients", text: "Patients who linked you appear here. Ask a patient for their invite code (Sharing page) and paste it to link them." },
  doctorConsole: { target: [], title: "The consultation console", text: "Open a patient, then start a consultation. Speak the visit and a draft note appears with medicines, diagnoses and advice sorted out. Nothing reaches the patient until you approve it." },
};

export const TOURS = {
  full: [S.welcome, S.home, S.upload, S.timeline, S.medicines, S.reminders, S.reading, S.doctors, S.share, S.agent],
  upload: [S.upload, S.agent], reading: [S.reading], medicines: [S.medicines], reminders: [S.reminders], share: [S.share],
  doctors: [S.doctors], timeline: [S.timeline], agent: [S.agent],
  doctor: [S.doctorWelcome, S.doctorHome, S.doctorConsole, S.doctorAgent],
};
