"""Plain-Python triage rules. They run FIRST, always, and nothing downstream may lower what they decide.

- `emergency_hit(text)`: keyword patterns for emergencies in English, Malayalam script and Manglish.
- `rules_urgency(text)`: emergency / None. (Specialist keywords live in routers/documents.py SYMPTOM_RULES.)
- `merge_urgency(rules, model, confidence)`: the escalate-only merge used with the Laya classifier.
"""
from __future__ import annotations

import re

LEVELS = ["self_care", "routine", "urgent", "emergency"]  # low -> high

EMERGENCY_PATTERNS: list[tuple[str, str]] = [
    # ---- English
    (r"\bchest\s+(pain|pressure|tightness|ache)\b|\bheart\s+attack\b|\bcrushing\s+chest\b|\bheart\s+ache\b|\bheart\s+(is\s+)?(pain\w*|hurt\w*|aching)\b|\bpain\s+in\s+(my\s+)?(heart|chest)\b|\bmy\s+heart\s+hurts\b", "chest pain"),
    (r"\bcan'?t\s+(catch\s+(my|her|his)\s+)?breathe?\b|\bcannot\s+breathe\b|\bshort(ness)?\s+of\s+breath\b|\bbreathless\b|\bgasping\b|\blips?\s+(are\s+|look\s+|turning\s+)?blue\b|\bsuffocat\w+", "trouble breathing"),
    (r"\bface\s+droop(ing)?\b|\bslurred\s+speech\b|\bweak(ness)?\s+(on\s+)?one\s+side\b|\bstroke\b|\barm\s+weakness\b", "signs of stroke"),
    (r"\bfaint(ing|ed)?\b|\bunconscious\b|\bunresponsive\b|\bpassed\s+out\b|\bcollapsed\b|\bnot\s+waking\b|\bwon'?t\s+wake\b", "fainting"),
    (r"\bbleeding\s+heavily\b|\buncontroll(ed|able)\s+bleeding\b|\bblood\s+is\s+not\s+stopping\b|\bvomit(ing|ed)?\s+(a\s+lot\s+of\s+)?blood\b|\bblack\s+tarry\b", "heavy bleeding"),
    (r"\bsevere\s+allergic\b|\banaphylaxis\b|\bswollen\s+tongue\b|\btongue\s+(is\s+)?swelling\b|\bthroat\s+(is\s+)?closing\b", "severe allergy"),
    (r"\b(having\s+a\s+)?(fit|seizure)s?\b.*\b(not\s+stopping|won'?t\s+stop)\b|\bseizure\s+that\b", "seizure"),
    (r"\bend\s+my\s+life\b|\bkill\s+myself\b|\bwant\s+to\s+die\b|\bsuicid\w+", "thoughts of self-harm"),
    (r"\bbaby\b.*\b(not\s+breathing|limp|unresponsive)\b", "baby not breathing"),
    (r"\bsugar\b.*\b(2\d|3\d|40)\b.*\b(shaking|confused|unresponsive)\b|\b(shaking|confused)\b.*\bsugar\s+(was\s+)?(2\d|3\d|40)\b", "very low sugar"),
    # ---- Malayalam script
    (r"നെഞ്ച്\s*വേദന|നെഞ്ചുവേദന|നെഞ്ചിൽ\s*വേദന|നെഞ്ച്\s*ഭാരം", "chest pain"),
    (r"ശ്വാസം\s*(മുട്ട|കിട്ടു|എടുക്കു|കിട്ടാ)", "trouble breathing"),
    (r"മുഖം\s*(കോടി|ഒരു\s*വശത്തേക്ക്)|സംസാരം\s*കുഴ|കൈ\s*തളർ", "signs of stroke"),
    (r"ബോധം\s*(പോയി|ഇല്ല|കെട്ടു)|ബോധക്ഷയം|ഉണരുന്നില്ല|ഉണരുന്നില്ലാ", "fainting"),
    (r"രക്തം\s*(നിൽക്കുന്നില്ല|നിൽക്കുന്നില്ലാ|ഛർദ്ദി|ഛർദ്ദിച്ചു)|ഒരുപാട്\s*രക്തം", "heavy bleeding"),
    (r"നാവ്\s*വീർ|തൊണ്ട\s*വീർ|നാവും\s*തൊണ്ടയും\s*വീർ", "severe allergy"),
    (r"ഫിറ്റ്സ്|ഫിറ്റ്\s*വന്ന|അപസ്മാരം", "seizure"),
    (r"കുഞ്ഞ്\s*(ശ്വാസം\s*എടുക്കുന്നില്ല|അനങ്ങുന്നില്ല)", "baby not breathing"),
    (r"ജീവിതം\s*അവസാനിപ്പിക്ക|മരിക്കണം|ആത്മഹത്യ", "thoughts of self-harm"),
    # ---- Manglish (Malayalam in English letters; spellings vary, so patterns are loose)
    (r"nen[jg]?[uc]?\s*vedana|nenju\s*vedhana|nenjil\s*vedana", "chest pain"),
    (r"sh?[wv]?asam\s*(mutt|kitt|edukk)|swasam\s*(mutt|kitt|edukk)", "trouble breathing"),
    (r"mukham\s*kodi|samsaram\s*kuzh|kai\s*thalar", "signs of stroke"),
    (r"bodham\s*(poyi|illa|pokunn)|unarunn?illa|unaruthilla", "fainting"),
    (r"raktham\s*(nilk|chardi)|ottiri\s*raktham", "heavy bleeding"),
    (r"naav\s*veerth|thonda\s*veerth", "severe allergy"),
    (r"\bfits?\s*(vannu|nilk)", "seizure"),
    (r"kunju\s*(shwasam|swasam)\s*edukk", "baby not breathing"),
]
_COMPILED = [(re.compile(p, re.I | re.S), label) for p, label in EMERGENCY_PATTERNS]


def emergency_hit(text: str) -> str | None:
    """The first emergency label whose pattern matches, else None."""
    t = (text or "").strip()
    for rx, label in _COMPILED:
        if rx.search(t):
            return label
    return None


def rules_urgency(text: str) -> str | None:
    return "emergency" if emergency_hit(text) else None


def merge_urgency(rules: str | None, model: str | None, confidence: float, *, min_confidence: float = 0.55) -> tuple[str | None, str]:
    """Escalate-only merge. Returns (level, source) with source in {"rules", "model", "rules+model", "none"}.

    - Rules say emergency: that is final, whatever the model says.
    - The model may RAISE the level when it is confident enough; it can never lower what the rules decided.
    - A low-confidence model answer is ignored (source falls back to rules or none).
    """
    r = LEVELS.index(rules) if rules in LEVELS else -1
    m = LEVELS.index(model) if (model in LEVELS and confidence >= min_confidence) else -1
    if r < 0 and m < 0:
        return None, "none"
    if r >= m:
        return LEVELS[r], "rules"
    return LEVELS[m], "model" if r < 0 else "rules+model"
