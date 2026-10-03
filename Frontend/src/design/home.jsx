// Distinct component types for the patient's home (and reused by other pages).
// None of these is "a card": each has its own structure and visual weight.
//   InsightHero      the dominant statement on the page
//   HealthSnapshot   one tinted column of four differently shaped measurements, divided by lines
//   ChangeBlock      an editorial data block: one large change, then compact rows with sparklines
//   AttentionItem    a compact row with a severity rule
//   CareLoop         today's care as nodes on a thread
//   DocumentPreview  a paper-like preview linked to its node in the Health Thread
//   ActionPanel      a quiet dashed call to action
import { useState } from "react";
import { EvidenceDialog } from "./ThreadExplorer.jsx";
import { Link } from "react-router-dom";
import { Sparkline } from "../components/charts.jsx";
import { useT } from "../i18n.js";
import { Arrow, RV, threadLink } from "./primitives.jsx";
import { ARROW, KIND_LABEL, docFigures, fmt, lab, lastChange, longDate, shortDate, unitText } from "./data.js";

const SparkMark = () => (
  <svg viewBox="0 0 16 16" width="14" height="14" fill="currentColor" aria-hidden="true">
    <path d="M8 0l1.6 4.8L14.4 6.4 9.6 8 8 12.8 6.4 8 1.6 6.4 6.4 4.8z" />
  </svg>
);

// ── InsightHero ─────────────────────────────────────────────────────────────
export function InsightHero({ review, deltas = [], openCount = 0, loading = false }) {
  const { lang, pick } = useT();
  const ml = lang === "ml";
  const headline = review ? pick(review, "headline") : null;
  return (
    <RV className="mt-hero">
      <div className="mt-hero-rail" aria-hidden="true"><span /></div>
      <div className="mt-hero-main">
        <div className="mt-label mt-hero-tag">
          <SparkMark /> {review?.source === "ai" ? (ml ? "AI ആരോഗ്യ വായന" : "AI health review") : (ml ? "ആരോഗ്യ വായന" : "Health review")}
        </div>
        {loading ? (
          <div className="mt-hero-skel" aria-hidden="true"><i /><i /><i /></div>
        ) : headline ? (
          <blockquote className="mt-hero-quote">{headline}</blockquote>
        ) : (
          <p className="mt-hero-quote quiet">{ml ? "നിങ്ങളുടെ രേഖകൾ ബന്ധിപ്പിച്ചിരിക്കുന്നു." : "Your records are connected. Add a result to see what changes."}</p>
        )}
        {deltas.length > 0 && (
          <ul className="mt-hero-deltas">
            {deltas.slice(0, 3).map((d) => (
              <li key={d.code} className={d.tone}>
                <span className="a" aria-hidden="true">{ARROW[d.dir]}</span>
                <span className="sr-only">{d.dir === "down" ? "Down" : d.dir === "up" ? "Up" : "Steady"}</span>
                <b>{d.name}</b>
                <span className="v">{fmt(d.from)} → {fmt(d.to)}{unitText(d.unit)}</span>
              </li>
            ))}
          </ul>
        )}
        <div className="mt-hero-foot">
          <span className={`mt-open${openCount ? " has" : ""}`}>
            <b>{openCount}</b> {ml ? "തുറന്ന കാര്യങ്ങൾ" : openCount === 1 ? "open item" : "open items"}
          </span>
          <Link className="mt-btn" to="/timeline">{ml ? "നിങ്ങളുടെ ത്രെഡ് കാണുക" : "View your thread"} <Arrow /></Link>
        </div>
      </div>
    </RV>
  );
}

// ── HealthSnapshot ──────────────────────────────────────────────────────────
export function HealthSnapshot({ insights, timeline = [], openCount = 0, doses }) {
  const { t, lang } = useT();
  const ml = lang === "ml";
  const series = insights?.series || [];
  // The headline measurement: HbA1c if there is one, else any other test with a history. Never BP, which has its own row.
  const primarySeries = series.find((s) => s.code === "hba1c")
    || series.find((s) => !["sbp", "dbp"].includes(s.code) && s.points?.length > 1);
  const primary = lastChange(primarySeries);
  const sbp = lab(insights, "sbp"), dbp = lab(insights, "dbp");
  const bpStatus = [sbp?.status, dbp?.status].includes("alert") ? "alert" : [sbp?.status, dbp?.status].includes("watch") ? "watch" : sbp ? "good" : null;
  const recent = timeline.slice(0, 3);

  return (
    <RV className="mt-snap" stagger={0.09} selector=":scope > .mt-snap-row">
      <div className="mt-snap-head mt-label">{ml ? "ആരോഗ്യ അവലോകനം" : "Current health snapshot"}</div>
      {primary && (
        <div className="mt-snap-row primary">
          <div className="mt-label">{primary.name}</div>
          <div className="mt-snap-big">{fmt(primary.to)}<small>{unitText(primary.unit)}</small></div>
          {primary.dir !== "steady" ? (
            <div className={`mt-snap-delta ${primary.tone}`}>
              <span aria-hidden="true">{ARROW[primary.dir]}</span>
              <span className="sr-only">{primary.dir === "down" ? "Down" : "Up"}</span> {fmt(primary.diff)}{unitText(primary.unit)}
            </div>
          ) : <div className="mt-snap-delta steady">No change</div>}
          <div className="mt-snap-cap">{ml ? "മുൻ രേഖയുമായി താരതമ്യം" : "Compared with previous record"}</div>
        </div>
      )}
      {sbp && dbp && (
        <div className="mt-snap-row">
          <div className="mt-label">{ml ? "രക്തസമ്മർദ്ദം" : "Blood pressure"}</div>
          <div className="mt-snap-mid">{sbp.value}<span className="sl">/</span>{dbp.value}<small> mmHg</small></div>
          <div className={`mt-snap-status ${bpStatus}`}><i aria-hidden="true" />{t(bpStatus)} · {ml ? "ലക്ഷ്യം" : "target"} &lt; 130 / 80</div>
        </div>
      )}
      <div className="mt-snap-row">
        <div className="mt-label">{ml ? "സമീപകാല പ്രവർത്തനം" : "Recent activity"}</div>
        <div className="mt-snap-mid">{timeline.length}<small> {ml ? "രേഖകൾ" : timeline.length === 1 ? "record" : "records"}</small></div>
        {recent.length > 0 && (
          <ol className="mt-snap-ticks">
            {recent.map((d) => <li key={d.id}><i aria-hidden="true" />{shortDate(d.date)} <span>{t(d.type)}</span></li>)}
          </ol>
        )}
      </div>
      <div className="mt-snap-row">
        <div className="mt-label">{ml ? "പരിചരണം" : "Care"}</div>
        <div className="mt-snap-mid">
          {openCount > 0 ? <>{openCount}<small> {ml ? "തുറന്നത്" : openCount === 1 ? "item open" : "items open"}</small></> : <span className="clear">{ml ? "എല്ലാം ശരി" : "All clear"}</span>}
        </div>
        {doses?.total > 0 && (
          <div className="mt-snap-cap">{doses.taken} {ml ? "/" : "of"} {doses.total} {ml ? "ഇന്നത്തെ ഡോസുകൾ" : "doses taken today"}</div>
        )}
      </div>
    </RV>
  );
}

// ── ChangeBlock ─────────────────────────────────────────────────────────────
export function ChangeBlock({ deltas = [], review }) {
  const { lang } = useT();
  const ml = lang === "ml";
  if (!deltas.length) return <p className="mt-quiet">{ml ? "താരതമ്യം ചെയ്യാൻ രണ്ട് ഫലങ്ങൾ വേണം." : "Two results of the same test are needed to show a change."}</p>;
  const [hero, ...rest] = deltas;
  const pts = review?.points || [];
  const missing = pts.filter((p) => p.kind === "missing").length;
  const better = deltas.filter((d) => d.tone === "good").length;
  const watch = deltas.filter((d) => d.tone === "watch").length;
  return (
    <div className="mt-change">
      <RV className="mt-change-hero">
        <div className="mt-label">{hero.name}</div>
        <div className="mt-change-flow">
          <span className="from">{fmt(hero.from)}</span>
          <span className="arrow" aria-hidden="true">→</span>
          <span className="to">{fmt(hero.to)}<small>{unitText(hero.unit)}</small></span>
        </div>
        <div className={`mt-chip ${hero.tone}`}>
          <span aria-hidden="true">{ARROW[hero.dir]}</span>
          {hero.dir === "steady" ? "No change" : `${hero.dir === "down" ? "Down" : "Up"} ${fmt(hero.diff)}${unitText(hero.unit)}`}
          {hero.tone === "good" ? " · improving" : hero.tone === "watch" ? " · to watch" : ""}
        </div>
        <div className="mt-change-since">{ml ? "മുതൽ" : "Since"} {longDate(hero.since)}</div>
        <div className="mt-change-spark"><Sparkline points={hero.points} code={hero.code} /></div>
      </RV>
      <div className="mt-change-side">
        <RV as="ul" className="mt-crows" stagger={0.07} selector=":scope > li">
          {rest.slice(0, 5).map((d) => (
            <li key={d.code} className="mt-crow">
              <span className="n">{d.name}</span>
              <span className="s"><Sparkline points={d.points} code={d.code} /></span>
              <span className="f">{fmt(d.from)} <i aria-hidden="true">→</i> <b>{fmt(d.to)}</b>{unitText(d.unit)}</span>
              <span className={`d ${d.tone}`} aria-hidden="true">{ARROW[d.dir]}</span>
              <span className="sr-only">{d.dir === "down" ? "down" : d.dir === "up" ? "up" : "steady"}</span>
            </li>
          ))}
        </RV>
        <dl className="mt-tally">
          {better > 0 && <div className="good"><dt>{better}</dt><dd>{better === 1 ? "improvement" : "improvements"}</dd></div>}
          {watch > 0 && <div className="watch"><dt>{watch}</dt><dd>{watch === 1 ? "value to watch" : "values to watch"}</dd></div>}
          {missing > 0 && <div className="miss"><dt>{missing}</dt><dd>{missing === 1 ? "record missing" : "records missing"}</dd></div>}
        </dl>
      </div>
    </div>
  );
}

// ── AttentionItem / OpenItems ───────────────────────────────────────────────
export function AttentionItem({ a }) {
  const { pick } = useT();
  return (
    <li className={`mt-att sev-${a.severity}`}>
      <span className="rule" aria-hidden="true" />
      <div className="body">
        <div className="mt-label">{KIND_LABEL[a.kind] || a.kind} · <span className="sev">{a.severity}</span></div>
        <div className="title">{a.title}</div>
        <p>{pick(a, "message")}</p>
        {a.cta && <Link className="mt-link" to={a.cta.to}>{a.cta.label} <Arrow /></Link>}
      </div>
    </li>
  );
}

export function OpenItems({ alerts = [], limit = 4 }) {
  const { lang } = useT();
  const ml = lang === "ml";
  const [all, setAll] = useState(false);
  if (!alerts.length) {
    return (
      <p className="mt-clear"><i aria-hidden="true" />{ml ? "ഇപ്പോൾ ശ്രദ്ധിക്കേണ്ടതൊന്നുമില്ല." : "Nothing needs your attention right now."}</p>
    );
  }
  const shown = all ? alerts : alerts.slice(0, limit);
  return (
    <div>
      <RV as="ul" className="mt-att-list" stagger={0.07} selector=":scope > li">
        {shown.map((a) => <AttentionItem key={a.id} a={a} />)}
      </RV>
      {alerts.length > limit && (
        <button type="button" className="mt-link" onClick={() => setAll((v) => !v)} aria-expanded={all}>
          {all ? (ml ? "കുറച്ച് കാണിക്കുക" : "Show fewer") : `${ml ? "കൂടുതൽ" : "Show all"} ${alerts.length}`} <Arrow />
        </button>
      )}
    </div>
  );
}

// ── CareLoop ────────────────────────────────────────────────────────────────
export function CareLoop({ doses, openCount = 0, followUp }) {
  const { lang } = useT();
  const ml = lang === "ml";
  const rows = [
    {
      key: "doses", label: ml ? "ഇന്നത്തെ മരുന്നുകൾ" : "Medicines today", to: "/medicines",
      value: doses?.total ? `${doses.taken} ${ml ? "/" : "of"} ${doses.total} ${ml ? "കഴിച്ചു" : "taken"}` : (ml ? "ഷെഡ്യൂൾ ഇല്ല" : "None scheduled"),
      done: doses?.total > 0 && doses.taken === doses.total,
    },
    {
      key: "open", label: ml ? "തുറന്ന മുന്നറിയിപ്പുകൾ" : "Open warnings",
      value: openCount ? `${openCount} ${ml ? "തുറന്നത്" : "open"}` : (ml ? "എല്ലാം ശരി" : "All clear"), done: openCount === 0,
    },
    followUp && { key: "follow", label: ml ? "ഫോളോ-അപ്പ്" : "Follow-up note", value: followUp.text, sub: shortDate(followUp.date), done: false },
  ].filter(Boolean);
  return (
    <RV as="ol" className="mt-loop" stagger={0.1} selector=":scope > li">
      {rows.map((r) => (
        <li key={r.key} className={r.done ? "done" : ""}>
          <span className="node" aria-hidden="true">{r.done ? "✓" : ""}</span>
          <div className="txt">
            <span className="mt-label">{r.label}{r.sub ? ` · ${r.sub}` : ""}</span>
            <span className="val">{r.value}</span>
          </div>
          {r.to && <Link className="go" to={r.to} aria-label={`Open ${r.label}`}><Arrow /></Link>}
        </li>
      ))}
    </RV>
  );
}

// ── DocumentPreview ─────────────────────────────────────────────────────────
export function DocumentPreview({ doc, onOpen }) {
  const { t } = useT();
  const figs = docFigures(doc);
  const first = figs[0];
  const Wrap = onOpen ? "button" : Link;
  return (
    <Wrap
      {...(onOpen ? { type: "button", onClick: () => onOpen(doc) } : { to: { pathname: "/timeline", hash: `#${doc.id}` } })}
      className={`mt-doc cat-${doc.type}`}
      onMouseEnter={() => threadLink.set(doc.id)}
      onMouseLeave={() => threadLink.set(null)}
      onFocus={() => threadLink.set(doc.id)}
      onBlur={() => threadLink.set(null)}
    >
      <span className="paper">
        <span className="top"><b>{t(doc.type)}</b><i>{shortDate(doc.date)}</i></span>
        {first ? (
          <span className="fig">
            <span className="fn">{first.name}</span>
            <span className={`fv st-${first.status || "none"}`}>{first.value}</span>
            {figs[1] && <span className="f2">{figs[1].name} · {figs[1].value}</span>}
          </span>
        ) : (
          <span className="fig"><span className="fn">{doc.title}</span></span>
        )}
        <span className="lines" aria-hidden="true"><i /><i /><i /></span>
      </span>
      <span className="cap">
        <span className="ttl">{doc.title}</span>
        <span className="sub">
          {longDate(doc.date)}
          {doc.sourceDoc && <em> · Analysed ✓</em>}
        </span>
        <span className="view">View evidence <Arrow /></span>
      </span>
    </Wrap>
  );
}

export function DocumentStrip({ docs = [], limit = 3, addTo = "/upload" }) {
  const { lang } = useT();
  const ml = lang === "ml";
  const list = docs.slice(0, limit);
  const [open, setOpen] = useState(null);
  return (
    <>
      <RV className="mt-docs" stagger={0.09} selector=":scope > *">
        {list.map((d) => <DocumentPreview key={d.id} doc={d} onOpen={setOpen} />)}
        <ActionPanel to={addTo} title={ml ? "ഒരു രേഖ ചേർക്കുക" : "Add a record"} text={ml ? "ഫോട്ടോ എടുക്കുക അല്ലെങ്കിൽ PDF അപ്‌ലോഡ് ചെയ്യുക" : "Upload a photo or PDF. It joins your thread."} />
      </RV>
      {open && <EvidenceDialog doc={open} onClose={() => setOpen(null)} />}
    </>
  );
}

// ── ActionPanel ─────────────────────────────────────────────────────────────
export function ActionPanel({ to, title, text }) {
  return (
    <Link to={to} className="mt-action">
      <span className="mark" aria-hidden="true"><i /><b>+</b></span>
      <span className="ttl">{title}</span>
      <span className="txt">{text}</span>
      <span className="go">Open <Arrow /></span>
    </Link>
  );
}
