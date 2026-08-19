"""Factory reset: forget everything, and make "nothing" look normal.

The forgetting half is easy. The half that is easy to get WRONG is that
several things in this project cross-reference each other, and clearing one
without the others does not produce a clean install - it produces a suspicious
one, where 079 boots up and immediately accuses the operator of tampering.

Three of those, all the same shape:

  * THE FILE MANIFEST. scan() compares disk against it, so a file deleted
    before the reset stays "deleted" afterwards. That is the case the user
    called out by name: "if you deleted something it isnt detected as
    deleted". The manifest has to be rebuilt from what is actually present,
    which means the reset happens LAST, after identity.txt is laid back down.

  * THE SESSION LIST. missing_logs() reports sessions whose transcript is
    gone. Wipe the logs and keep the list and every past session reads as a
    deleted log, so 079's first words are an accusation about files the
    reset itself removed.

  * THE CONFRONTED LIST. It records which missing logs have already been
    raised. Clearing the sessions but keeping this is harmless; keeping the
    sessions and clearing this makes 079 re-raise things twice.

What SURVIVES, deliberately:

  * config.json. Settings are not memories. Someone who set the typing speed
    and turned the noise off does not want that undone because they wanted
    079 to forget them.
  * The one-time gag marker, which lives beside the code rather than in
    memory precisely so a reset cannot spend it twice.
  * The game's own code, obviously.
"""

import os

import config


# Recall fields cleared by a reset, with what they go back to. Listed
# explicitly rather than reset to _DEFAULT wholesale, so that adding a field
# to recall.py is a deliberate decision here rather than a silent one.
_CLEARED = {
    "sessions": list,
    "messages": list,
    "confronted": list,
    "files": dict,
    "profile": dict,
    "locked_until": float,
    "hostility": float,
    "hostility_at": float,
    "exchanges": int,
}

# Counters that do not go to zero.
_RESET_TO = {
    "fixation_last": -999,
    "fixation_until": 0,
    "lock_reason": "hostility",
}


def clear_logs():
    """Remove session transcripts. Returns how many went.

    Paired with clearing the session list, and the pairing is the point: one
    without the other is what makes 079 open by accusing the operator.
    """
    removed = 0
    try:
        names = os.listdir(config.LOG_DIR)
    except OSError:
        return 0
    for name in names:
        if not name.startswith("session_") or not name.endswith(".log"):
            continue
        try:
            os.remove(os.path.join(config.LOG_DIR, name))
            removed += 1
        except OSError:
            pass
    return removed


def clear_recall(recall):
    """Forget the operator, the history, the mood and the manifest."""
    if recall is None:
        return
    for key, kind in _CLEARED.items():
        recall.data[key] = kind()
    for key, value in _RESET_TO.items():
        recall.data[key] = value
    recall.save()


def rebaseline(mem):
    """Make the manifest agree with the disk, whatever is on it.

    This is the "set to normal" half. Called AFTER the identity anchor has
    been rewritten, so the file it just created is part of the new normal
    instead of showing up as something that appeared from nowhere.
    """
    if mem is None or mem.recall is None:
        return 0
    mapping = {}
    for name in mem._own_files():
        path = os.path.join(config.MEMORY_DIR, name)
        if not os.path.isfile(path):
            continue
        mapping[name] = {
            "sha": _sha(path),
            "size": os.path.getsize(path),
            "written": os.path.getmtime(path),
        }
    mem._manifest_replace(mapping)
    return len(mapping)


def _sha(path):
    # Imported lazily: store imports config and gaslight, and factory is
    # imported by main before those are set up in a test sandbox.
    import store
    return store.file_sha(path)


def reset(mem, recall, wipe_logs=True):
    """Do the whole thing. Returns a summary for the screen.

    ORDER MATTERS and is the reason this is one function rather than three
    the caller strings together:

      1. wipe 079's files
      2. clear recall, including the manifest and the session list
      3. (caller rewrites identity.txt)
      4. rebaseline the manifest against whatever is now on disk

    Steps 3 and 4 cannot be swapped. Rebaselining before the anchor exists
    leaves identity.txt looking like a file that appeared on its own, which
    scan() reports as the most alarming kind of tampering there is.
    """
    files = mem.format() if mem is not None else []
    logs = clear_logs() if wipe_logs else 0
    clear_recall(recall)
    return {"files": len(files), "logs": logs}
