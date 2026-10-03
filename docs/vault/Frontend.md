---
tags: [frontend]
---
# Frontend

Back to [[Architecture]]. React 19 + Vite (JavaScript).

- `src/api/client.js` lists every endpoint. `src/design/` is the component system (`mt.css` holds tokens, chapters, components).
- Screens: Home, Health Thread, Health Check, Medicines, Reminders, Doctors, Sharing, Upload, Triage, Profile, doctor home and console, Admin.
- **Agent panel** (`components/agent/`) and **guided tour and demo** (`components/tour/`): a welcome card once, a Tour button, an auto-playing demo, a doctor tour.
- Typeface: Inter everywhere. Palette: sage greens. Motion: GSAP and IntersectionObserver, reduced-motion aware.
- Lab report cards list the tests inside; prescription cards show medicines only.
- `npm run build:single` makes an offline one-file build on mock data (a backup for the demo).

Related: [[Agent]], [[Demo script]].
