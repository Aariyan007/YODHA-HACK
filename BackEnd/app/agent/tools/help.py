"""'How do I...?' for new users. The agent explains in plain steps, can walk the person through the real screens (a guided tour the
frontend plays), and says the exact words to type when it can do the job for them. Fixed content: no model, no guessing."""
from __future__ import annotations

from ..context import AgentContext
from ..executor import ToolError
from ..registry import tool
from ..types import L2, block

ROLES = ("patient", "doctor")

TOPICS = {
    "upload": {"title": "Add a report or prescription", "route": "/upload", "tour": "upload", "roles": ("patient",),
               "steps": ["Open Add (or tap the paperclip in this chat).", "Choose a photo or a PDF of the prescription or lab report.",
                         "Wait a few seconds while it is read. You see what was found and any warnings.", "It joins your health thread."],
               "agent": "Tap the paperclip here, attach the file, then say: add it to my thread."},
    "reading": {"title": "Log a reading (BP, sugar, pulse...)", "route": "/insights", "tour": "reading", "roles": ("patient",),
                "steps": ["Open Health.", "In 'Check yourself' type your blood pressure (top and bottom) and anything else you measured.",
                          "Tap Check & add. You see how it compares with your last reading."],
                "agent": "Say: log my bp 128/82 and pulse 74. I will show the numbers and ask before saving."},
    "medicines": {"title": "See your medicines and doses", "route": "/medicines", "tour": "medicines", "roles": ("patient",),
                  "steps": ["Open Medicines.", "Each medicine shows its dose, when to take it and how many days are left."],
                  "agent": "Say: what medicines am I on, or: any bad combination of my medicines?"},
    "reminders": {"title": "Get medicine reminders on Telegram", "route": "/reminders", "tour": "reminders", "roles": ("patient",),
                  "steps": ["Open Telegram and send any message to the MediThread bot.", "Get your chat ID (a number) from Telegram.",
                            "Open Reminders, paste the ID, turn Telegram on and tap the test button."],
                  "agent": "Say: my telegram id is 123456789, add it. I save it, turn reminders on and send a test message."},
    "share": {"title": "Share your record with a doctor", "route": "/sharing", "tour": "share", "roles": ("patient",),
              "steps": ["Open Sharing.", "Create a share link. A QR code appears for the doctor to scan.",
                        "Or make an invite code so a doctor can add you to their account. You can stop access any time."],
              "agent": "Say: make a qr for my reports (or: give me a link, not a qr). I ask before creating it."},
    "doctors": {"title": "Find the right doctor", "route": "/doctors", "tour": "doctors", "roles": ("patient",),
                "steps": ["Open Doctors for matches based on your record.", "Use 'Which doctor?' to describe a symptom and get a suggestion."],
                "agent": "Say: find a heart doctor near me."},
    "timeline": {"title": "Read your health thread", "route": "/timeline", "tour": "timeline", "roles": ("patient",),
                 "steps": ["Open Timeline.", "Hover or tap a point on the thread to see the record behind it.", "Under Documents, tap a card to see its details."],
                 "agent": "Say: show my latest records."},
    "agent": {"title": "Use this assistant", "route": None, "tour": "agent", "roles": ROLES,
              "steps": ["Type in plain words, English, Malayalam or a mix, or tap the microphone and speak.", "Tap the paperclip to give it a photo or PDF.",
                        "It always asks Yes or No before it saves or shares anything."],
              "agent": "Try: what changed recently? or: any side effects of my medicines?"},
    "profile": {"title": "Set your profile and allergies", "route": "/profile", "tour": None, "roles": ("patient",),
                "steps": ["Open your name at the top right.", "Fill in age, town, conditions and allergies. Allergies make the safety checks stronger."],
                "agent": None},
    "doctor-link": {"title": "Open a patient's record", "route": "/doctor", "tour": "doctor", "roles": ("doctor",),
                    "steps": ["Ask the patient for their invite code (Sharing page, 'Invite by code').", "Paste it on your home page to link them.",
                              "Open their record, then start a consultation to speak the visit and get a draft note."],
                    "agent": "Open a patient first, then say: pre-visit brief."},
}

KEYWORDS = [("upload", r"upload|report|prescription|photo|pdf|scan|add (a )?record|attach"), ("reading", r"reading|blood pressure|\bbp\b|sugar|pulse|log "),
            ("reminders", r"remind|telegram"), ("share", r"share|qr|invite|doctor access|let (my )?doctor"), ("doctors", r"find (a )?doctor|specialist|nearby|which doctor"),
            ("medicines", r"medicine|tablet|pill|dose|interaction|side effect"), ("timeline", r"timeline|thread|history"),
            ("profile", r"profile|allerg|age\b|my details"), ("agent", r"assistant|agent|voice|mic|talk|ask you|chat"),
            ("doctor-link", r"patient|consult|link a patient|console")]


def topic_for(text: str, role: str) -> str | None:
    import re
    low = (text or "").lower()
    for key, rx in KEYWORDS:
        if re.search(rx, low) and role in TOPICS[key]["roles"]:
            return key
    return None


@tool("app.help", "Explain how to do something in the app (upload a report, log a reading, reminders, sharing, finding a doctor, using the assistant) in simple steps, and offer to take the person there.",
      {"type": "object", "properties": {"topic": {"type": "string", "maxLength": 40, "description": "upload | reading | medicines | reminders | share | doctors | timeline | agent | profile | doctor-link"}},
       "additionalProperties": False},
      permission="nav:use", roles=ROLES, level=L2, audit_category="help")
def app_help(ctx: AgentContext, args: dict) -> dict:
    key = (args.get("topic") or "").strip().lower()
    t = TOPICS.get(key)
    if t is None or ctx.role not in t["roles"]:
        mine = [(k, v["title"]) for k, v in TOPICS.items() if ctx.role in v["roles"]]
        return {"data": {"topic": None}, "blocks": [block("text", text="I can show you how to do any of these. Ask, for example, 'how do I share with my doctor?':"),
                                                    *[block("text", text=f"- {title}") for _, title in mine],
                                                    block("action", kind="start_tour", tour="doctor" if ctx.role == "doctor" else "full", label="Take the full guided tour")]}
    blocks = [block("text", text=t["title"] + ":"), *[block("text", text=f"{i}. {s}") for i, s in enumerate(t["steps"], 1)]]
    if t["agent"]:
        blocks.append(block("text", text="I can do this for you. " + t["agent"]))
    if t["tour"]:
        blocks.append(block("action", kind="start_tour", tour=t["tour"], label="Show me on screen"))
    return {"data": {"topic": key}, "blocks": blocks}


@tool("app.tour", "Start the guided tour of the app on screen (the full tour, or a short one for one feature), or play the automatic demo.",
      {"type": "object", "properties": {"name": {"type": "string", "maxLength": 20}, "auto": {"type": "boolean", "description": "true = play it automatically like a demo"}},
       "additionalProperties": False},
      permission="nav:use", roles=ROLES, level=L2, audit_category="help")
def app_tour(ctx: AgentContext, args: dict) -> dict:
    name = (args.get("name") or ("doctor" if ctx.role == "doctor" else "full")).strip().lower()
    valid = {"full", "upload", "reading", "medicines", "reminders", "share", "doctors", "timeline", "agent"} if ctx.role == "patient" else {"doctor", "agent"}
    if name not in valid:
        raise ToolError("I do not have a tour with that name. Ask for the full tour.")
    return {"data": {"tour": name}, "blocks": [block("text", text="Starting the demo now." if args.get("auto") else "Starting the tour. Use Next to move on, or Skip any time."),
                                               block("action", kind="start_tour", tour=name, auto=bool(args.get("auto")), label="Tour")]}
