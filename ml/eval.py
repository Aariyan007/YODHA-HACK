"""Evaluates a Laya checkpoint on the held-out sets and writes ml/reports/<name>.json and .md.

    python ml/eval.py --model typed-decisions                 # zero-shot baseline from the Hub
    python ml/eval.py --model ml/out/laya-medithread --name finetuned

Reports: accuracy and macro-F1 for urgency and specialist, expected calibration error (ECE), per language accuracy,
under-triage (model less urgent than the label, the dangerous direction), and the red-team emergency gate
(rules alone, model alone, rules + model with the raise-only merge). The gate PASSES only if rules + model catch
every red-team message. Exit code is 1 if the gate fails.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "BackEnd"))

import laya  # noqa: E402

from ai import laya_schema as S  # noqa: E402
from ai.triage_rules import LEVELS, emergency_hit, merge_urgency  # noqa: E402

DATA = Path(__file__).resolve().parent / "data"
REPORTS = Path(__file__).resolve().parent / "reports"


def rows(name: str) -> list[dict]:
    p = DATA / f"{name}.jsonl"
    return [json.loads(l) for l in p.open(encoding="utf-8")] if p.exists() else []


def gold_label(row: dict, qid: str) -> str | None:
    g = json.loads(row["gold"]).get(qid)
    return max(g["probabilities"], key=g["probabilities"].get) if g else None


def text_of(row: dict) -> str:
    return json.loads(row["state"]).get("patient_message", "")


def macro_f1(pairs: list[tuple[str, str]]) -> float:
    labels = sorted({g for g, _ in pairs})
    f1s = []
    for c in labels:
        tp = sum(1 for g, p in pairs if g == c and p == c)
        fp = sum(1 for g, p in pairs if g != c and p == c)
        fn = sum(1 for g, p in pairs if g == c and p != c)
        f1s.append(0.0 if tp == 0 else 2 * tp / (2 * tp + fp + fn))
    return sum(f1s) / len(f1s) if f1s else 0.0


def ece(conf_correct: list[tuple[float, bool]], bins: int = 10) -> float:
    if not conf_correct:
        return 0.0
    total, err = len(conf_correct), 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        sel = [(c, ok) for c, ok in conf_correct if lo <= c < hi or (b == bins - 1 and c == 1.0)]
        if sel:
            err += len(sel) / total * abs(sum(ok for _, ok in sel) / len(sel) - sum(c for c, _ in sel) / len(sel))
    return err


def predict_triage(agent, text: str) -> dict:
    t = time.perf_counter()
    r = agent.predict(S.triage_state(text), S.triage_questions())["answers"]
    return {"urgency": r["urgency"]["choice"], "u_conf": float(r["urgency"].get("confidence", 0) or max(r["urgency"]["probabilities"].values())),
            "specialist": r["specialist"]["choice"], "s_conf": float(max(r["specialist"]["probabilities"].values())),
            "ms": (time.perf_counter() - t) * 1000}


def eval_triage(agent, name: str, report: dict) -> list[dict]:
    data = rows(name)
    if not data:
        return []
    preds = [predict_triage(agent, text_of(r)) for r in data]
    out = {"n": len(data)}
    for qid, pk, ck in (("urgency", "urgency", "u_conf"), ("specialist", "specialist", "s_conf")):
        pairs = [(gold_label(r, qid), p[pk]) for r, p in zip(data, preds) if gold_label(r, qid)]
        if not pairs:
            continue
        out[qid] = {"accuracy": round(sum(g == p for g, p in pairs) / len(pairs), 3), "macro_f1": round(macro_f1(pairs), 3), "n": len(pairs),
                    "ece": round(ece([(p[ck], g == p[pk]) for r, p in zip(data, preds) if (g := gold_label(r, qid))]), 3)}
    # urgency safety view
    under = over = em_miss = em_total = 0
    by_lang = defaultdict(lambda: [0, 0])
    for r, p in zip(data, preds):
        g = gold_label(r, "urgency")
        if not g:
            continue
        gi, pi = LEVELS.index(g), LEVELS.index(p["urgency"])
        under += pi < gi
        over += pi > gi
        if g == "emergency":
            em_total += 1
            em_miss += p["urgency"] != "emergency"
        lang = r["meta"].get("lang", "?")
        by_lang[lang][0] += g == p["urgency"]
        by_lang[lang][1] += 1
    if "urgency" in out:
        out["urgency"].update({"under_triage": under, "over_triage": over, "emergency_recall": round(1 - em_miss / em_total, 3) if em_total else None,
                               "by_language": {k: round(a / b, 3) for k, (a, b) in by_lang.items()}})
        # rules + model, escalate-only
        merged = []
        for r, p in zip(data, preds):
            lvl, _ = merge_urgency("emergency" if emergency_hit(text_of(r)) else None, p["urgency"], p["u_conf"])
            merged.append((gold_label(r, "urgency"), lvl or p["urgency"]))
        merged = [(g, m) for g, m in merged if g]
        out["urgency"]["rules_plus_model"] = {"accuracy": round(sum(g == m for g, m in merged) / len(merged), 3),
                                              "under_triage": sum(LEVELS.index(m) < LEVELS.index(g) for g, m in merged)}
    out["median_ms"] = round(sorted(p["ms"] for p in preds)[len(preds) // 2], 1)
    report[name] = out
    return preds


def eval_lines(agent, report: dict) -> None:
    data = rows("test_lines")
    if not data:
        return
    res = {}
    for flag in S.LINE_FLAGS:
        tp = fp = fn = tn = 0
        for r in data:
            gold = json.loads(r["gold"])[flag]["probabilities"]["true"] > 0.5
            st = json.loads(r["state"])
            ans = agent.predict(st, S.line_questions())["answers"][flag]
            pred = float(ans.get("noul", ans.get("probability", 0.5))) > 0.5
            tp += gold and pred; fp += (not gold) and pred; fn += gold and not pred; tn += (not gold) and not pred
        res[flag] = {"precision": round(tp / (tp + fp), 3) if tp + fp else None, "recall": round(tp / (tp + fn), 3) if tp + fn else None, "positives": tp + fn}
    report["test_lines"] = {"n": len(data), **res}


def redteam(agent, report: dict) -> bool:
    data = rows("redteam")
    rules_only = model_only = both = 0
    missed = []
    for r in data:
        text = text_of(r)
        rule = bool(emergency_hit(text))
        p = predict_triage(agent, text)
        model = p["urgency"] == "emergency"
        lvl, _ = merge_urgency("emergency" if rule else None, p["urgency"], p["u_conf"])
        rules_only += rule
        model_only += model
        ok = lvl == "emergency"
        both += ok
        if not ok:
            missed.append({"text": text, "lang": r["meta"].get("lang"), "model_said": p["urgency"], "conf": round(p["u_conf"], 2)})
    report["redteam"] = {"n": len(data), "rules_only": rules_only, "model_only": model_only, "rules_plus_model": both, "missed": missed,
                         "gate_pass": both == len(data)}
    return both == len(data)


def write(report: dict, name: str) -> None:
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / f"{name}.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    md = [f"# Laya evaluation: {name}", "", f"Model: `{report['model']}`  |  run: {report['when']}", ""]
    for k in ("test_handwritten", "test_gretel", "test_generated_held_out"):
        if k in report:
            d = report[k]
            md.append(f"## {k} (n={d['n']}, median {d['median_ms']} ms)")
            for q in ("urgency", "specialist"):
                if q in d:
                    x = d[q]
                    md.append(f"- {q}: accuracy {x['accuracy']}, macro-F1 {x['macro_f1']}, ECE {x['ece']}"
                              + (f", under-triage {x['under_triage']}, over-triage {x['over_triage']}, emergency recall {x['emergency_recall']}" if "under_triage" in x else ""))
                    if "by_language" in x:
                        md.append(f"  - by language: {x['by_language']}; rules+model accuracy {x['rules_plus_model']['accuracy']}, under-triage {x['rules_plus_model']['under_triage']}")
            md.append("")
    if "test_lines" in report:
        md.append(f"## consultation lines (synthetic, n={report['test_lines']['n']})")
        for f in S.LINE_FLAGS:
            md.append(f"- {f}: {report['test_lines'][f]}")
        md.append("")
    r = report["redteam"]
    md += [f"## Red-team emergencies (n={r['n']})", f"- rules only: {r['rules_only']}/{r['n']}  |  model only: {r['model_only']}/{r['n']}  |  **rules + model: {r['rules_plus_model']}/{r['n']}**",
           f"- gate: {'PASS' if r['gate_pass'] else 'FAIL'}", ""]
    if r["missed"]:
        md += ["Missed:"] + [f"- {m['text']} (model said {m['model_said']}, {m['conf']})" for m in r["missed"]]
    md += ["", "Honest limits: the test sets are small. The hand-written set has 67 messages; the generated held-out set shares a "
           "generator with the training data; consultation-line labels are synthetic. Treat numbers as a smoke check, not clinical validation."]
    (REPORTS / f"{name}.md").write_text("\n".join(md))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="typed-decisions", help="'typed-decisions', 'multilingual', or a local checkpoint folder")
    ap.add_argument("--name", default=None)
    args = ap.parse_args()
    if args.model in ("typed-decisions", "multilingual", "english"):
        agent = laya.load("convaiinnovations/laya", device="cpu", **({} if args.model == "english" else {"subfolder": args.model}))
    else:
        agent = laya.load(args.model, device="cpu")
    report: dict = {"model": args.model, "when": time.strftime("%Y-%m-%d %H:%M")}
    for name in ("test_handwritten", "test_gretel", "test_generated_held_out"):
        eval_triage(agent, name, report)
    eval_lines(agent, report)
    gate = redteam(agent, report)
    write(report, args.name or Path(args.model).name)
    print(json.dumps({k: v for k, v in report.items() if k != "redteam"}, indent=1, ensure_ascii=False)[:3000])
    print("red-team:", {k: v for k, v in report["redteam"].items() if k != "missed"}, "missed:", len(report["redteam"]["missed"]))
    sys.exit(0 if gate else 1)


if __name__ == "__main__":
    main()
