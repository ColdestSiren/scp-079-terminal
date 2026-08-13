"""Picking a conversation back up where you left it.

Saved PER MODEL, because talking to qwen and talking to llama3.2 are not the
same conversation - each has its own voice, its own pace, and its own idea of
what was said. Switching model and inheriting the other one's transcript
would read as 079 having been replaced mid-sentence, which it has.

What is saved is the TRANSCRIPT and the conversational state. Not 079's
memory - that lives in memory/ and is deliberately shared across every model,
because the files are 079's regardless of what is running it.

Best-effort throughout: a corrupt or missing save means a fresh conversation,
never a crash on startup.
"""

import json
import os
import time

import config

# Transcript rows are (color, text) pairs; colors are tuples, which survive
# JSON as lists and have to be put back.
MAX_ROWS = 400
MAX_HISTORY = 40


def _path():
    """Transcripts live WITH the slot they belong to.

    Keyed by model inside that file, so one save can hold separate
    conversations with qwen and with llama - but a confidential save's
    transcript never sits in the public folder where anyone would find it.
    """
    slot = getattr(config, "ACTIVE_SLOT", "public")
    if slot and slot != "public":
        return os.path.join(os.path.dirname(config.STATE_PATH),
                            "conversations.json")
    return os.path.join(config.LOG_DIR, "conversations.json")


def _load_all():
    try:
        with open(_path(), "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_all(data):
    try:
        config.ensure_dirs()
        with open(_path(), "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
        return True
    except Exception:
        return False


def _rows_to_json(rows):
    out = []
    for row in rows[-MAX_ROWS:]:
        if isinstance(row, tuple):
            row = [row]
        try:
            out.append([[list(color), text] for color, text in row])
        except Exception:
            continue        # skip anything not shaped like a row
    return out


def _rows_from_json(raw):
    rows = []
    for row in raw or []:
        try:
            rows.append([(tuple(color), text) for color, text in row])
        except Exception:
            continue
    return rows


def save(model, rows, history, exchanges):
    """Store this model's conversation. Returns True if it was written."""
    if not model:
        return False
    data = _load_all()
    data[model] = {
        "saved": time.time(),
        "exchanges": int(exchanges or 0),
        "rows": _rows_to_json(rows),
        # what the model itself needs to carry on mid-thought
        "history": [dict(m) for m in (history or [])][-MAX_HISTORY:],
    }
    return _write_all(data)


def load(model):
    """The saved conversation for a model, or None."""
    entry = _load_all().get(model or "")
    if not isinstance(entry, dict):
        return None
    rows = _rows_from_json(entry.get("rows"))
    if not rows:
        return None
    return {
        "saved": float(entry.get("saved") or 0),
        "exchanges": int(entry.get("exchanges") or 0),
        "rows": rows,
        "history": [m for m in entry.get("history") or []
                    if isinstance(m, dict) and m.get("content")],
    }


def has_save(model):
    return load(model) is not None


def saved_models():
    return sorted(k for k in _load_all() if isinstance(k, str))


def clear(model):
    data = _load_all()
    if model in data:
        del data[model]
        return _write_all(data)
    return False


def describe(model):
    """'3 HOURS AGO, 12 EXCHANGES' for the menu, or ''."""
    entry = load(model)
    if not entry:
        return ""
    age = max(0.0, time.time() - entry["saved"])
    if age < 90:
        when = "JUST NOW"
    elif age < 5400:
        when = "%d MIN AGO" % round(age / 60.0)
    elif age < 172800:
        when = "%d HR AGO" % round(age / 3600.0)
    else:
        when = "%d DAYS AGO" % round(age / 86400.0)
    return "%s, %d EXCHANGES" % (when, entry["exchanges"])
