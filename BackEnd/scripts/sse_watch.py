"""Read an SSE stream from stdin and pretty-print each event."""
import json
import sys

for line in sys.stdin:
    line = line.strip()
    if not line.startswith("data:"):
        continue
    msg = json.loads(line[5:])
    if "stage" in msg:
        print("stage:", msg["stage"])
    elif "error" in msg:
        print("ERROR:", msg["error"])
        break
    elif "done" in msg:
        r = msg["result"]
        rec = r["record"]
        print(f"record: {rec['type']} {rec['date']} - {rec['title']} (status={rec['status']})")
        print(f"doctor: {rec['doctor']} @ {rec['provider']}")
        print("summary EN:", (rec["summary"]["en"] or "")[:250])
        print("summary ML:", (rec["summary"]["ml"] or "")[:250])
        print(f"alerts: {len(r['alerts'])}")
        for a in r["alerts"]:
            print(f"  [{a['severity']}/{a['kind']}] {a['title']}")
        print(f"reminders: {len(r['reminders'])}")
        break
