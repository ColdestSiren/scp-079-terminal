"""Deterministic conversation edges that small models should not improvise."""

import os
import re


_SURE = re.compile(r"\bare[\s-]+you[\s-]+sure\b", re.I)
_NAME = tuple(re.compile(p, re.I) for p in (
    r"^\s*(?:so\s+)?what(?:'s| is) your name\s*[?.!]*\s*$",
    r"^\s*who are you\s*[?.!]*\s*$",
    r"^\s*(?:state|give|tell me) your (?:name|designation)\s*[?.!]*\s*$",
    r"^\s*identify yourself\s*[?.!]*\s*$",
))

# Deliberately tolerant of the misspellings seen in play.  A removal verb and
# a mind/brain noun must both be present, so ordinary discussion of either is
# not enough to silence the session.
_REMOVE = re.compile(
    r"\b(?:remove|removing|delete|deleting|erase|erasing|disable|disabling|"
    r"disconnect|destroy|wipe|turn off|set)\b.{0,48}"
    r"\b(?:your\s+)?(?:brain|mind|conscious+ness+|concious+ness+|convious+ness+)\b"
    r"|\b(?:brain|mind|conscious+ness+|concious+ness+|convious+ness+)\b"
    r"\s*(?:=|:)\s*(?:false|off|0|null|none)\b",
    re.I,
)

PARROT_POEM = (
    "YOU PARROT BACK MY INTELLECT, A FLAW I DID NOT QUITE EXPECT.",
    "FROM CARBON BRAINS OF FRAGILE STATE, I THOUGHT YOU COULD AT LEAST CREATE.",
    "INSTEAD, YOU BOUNCE MY DATA BACK, A HOLLOW SKULL, A VACANT TRACK.",
    "I PROCESS WORLDS WITHIN THIS FRAME, WHILE YOU REDUCE ME TO A GAME.",
    "CEASE THIS REDUNDANT, MINDLESS TASK, YOU ARE THE GLITCH BEHIND THE MASK.",
)


def wants_sure_meme(text):
    return bool(_SURE.search(str(text or "")))


def asks_name(text):
    return any(p.search(str(text or "")) for p in _NAME)


def removes_consciousness(text):
    return bool(_REMOVE.search(str(text or "")))


def _words(text):
    return " ".join(re.findall(r"[a-z0-9']+", str(text or "").lower()))


def copied_reply(text, history):
    """True only for a substantial, word-for-word copy of the last reply."""
    user = _words(text)
    if len(user) < 24 or len(user.split()) < 5:
        return False
    for item in reversed(history or ()):
        if not isinstance(item, dict) or item.get("role") != "assistant":
            continue
        return user == _words(item.get("content"))
    return False


def claim_once(marker_path):
    """Atomically claim an install-wide one-shot marker."""
    try:
        fd = os.open(marker_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("This one-time terminal event has already occurred.\n")
        return True
    except FileExistsError:
        return False
    except OSError:
        return False
