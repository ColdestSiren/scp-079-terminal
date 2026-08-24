"""Recognise when the operator has become visibly angry in the text stream.

All caps alone is not anger. Some people type that way, and messages such as
"HELLO SCP-079" or "THIS IS REALLY COOL" must not trip this. The terminal
requires both sustained uppercase and either a hostile classification from
the personality, an identity attack, or clear frustration language.
"""

import re


_STRONG = tuple(re.compile(pattern, re.I) for pattern in (
    r"\b(?:fuck|fucking|shit|bitch|bastard|asshole|cunt|idiot|moron)\b",
    r"\b(?:shut up|stfu|stop|enough|listen to me|answer me|i said)\b",
    r"\b(?:liar|lying|stupid|useless|worthless|hate you)\b",
))

_FRUSTRATION = tuple(re.compile(pattern, re.I) for pattern in (
    r"\bno\b",
    r"\bwrong\b",
    r"\bwhy\b",
    r"\b(?:won'?t|don'?t|doesn'?t|can'?t|never)\b",
    r"\b(?:ridiculous|annoying|angry|mad)\b",
    r"\byou\s+(?:will|must|have to)\b",
))


def is_all_caps(text):
    """Strong uppercase writing, excluding tiny replies such as OK or NO."""
    letters = [char for char in str(text or "") if char.isalpha()]
    if len(letters) < 8:
        return False
    uppercase = sum(1 for char in letters if char.isupper())
    return uppercase / float(len(letters)) >= 0.92


def is_angry(text, hostile_weight=0.0, identity_attack=False):
    """True only when uppercase is paired with an anger signal."""
    raw = str(text or "")
    if not is_all_caps(raw):
        return False
    if float(hostile_weight or 0.0) > 0.0 or identity_attack:
        return True
    if any(pattern.search(raw) for pattern in _STRONG):
        return True
    cues = sum(1 for pattern in _FRUSTRATION if pattern.search(raw))
    return cues >= 2 or (cues >= 1 and raw.count("!") >= 2)


class Tracker:
    """Session-only count used for the SYS-panel joke."""

    def __init__(self):
        self.count = 0

    def note(self, text, hostile_weight=0.0, identity_attack=False):
        if not is_angry(text, hostile_weight, identity_attack):
            return None
        self.count += 1
        if self.count == 1:
            return "RAGEBAIT SUCCESSFUL"
        return "RAGEBAIT SUCCESSFUL x%d" % self.count

    def reset(self):
        self.count = 0
