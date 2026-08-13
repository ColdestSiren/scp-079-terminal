"""The drop box between the player and 079.

You put a file in "shared folder" at the project root. 079 cannot see it at
all until you say so with /shared on, and even then it can only READ.

Read-only is structural, not a promise: there is no write, rename or delete
path in this module. The only filesystem calls here are listdir, stat and
open(mode="r").

Contents are treated as untrusted for the same reason web pages are - not
because the player is an attacker, but because a file that happens to contain
">>DELETE observations.txt" must not become a real command when 079 reads it
out. Same stripper, same reasoning.
"""

import os

import config
import sanitize

# Openable as text. Anything else is refused by name rather than being opened
# and handed over as mojibake - 079 saying "I cannot read that format" is a
# better answer than three kilobytes of binary noise.
READABLE_EXT = (".txt", ".md", ".log", ".csv", ".json", ".xml", ".ini",
                ".cfg", ".yml", ".yaml", ".py", ".bat", ".ps1", ".html")

MAX_READ_BYTES = 200_000     # cap the read itself
MAX_CHARS = 2000             # what 079 is actually handed
MAX_LISTED = 40

_BAD_CHARS = set('<>:"|?*\0')


class SharedError(Exception):
    """A refusal worth telling 079 about."""


def _resolve(name):
    """Validate a model-supplied name into a path inside the shared folder.

    Same posture as store._resolve: the model is untrusted input, so this
    validates and refuses rather than trying to sanitize something dangerous
    into something safe.
    """
    raw = (name or "").strip().strip('"').strip("'")
    if not raw:
        raise SharedError("NO FILENAME GIVEN.")
    if any(ch in _BAD_CHARS for ch in raw) or raw in (".", ".."):
        raise SharedError("INVALID FILENAME: %s" % raw)
    if os.path.basename(raw) != raw:
        raise SharedError("THE SHARED FOLDER IS ONE DIRECTORY. NO PATHS.")

    base = os.path.realpath(config.SHARED_DIR)
    path = os.path.realpath(os.path.join(base, raw))
    # realpath resolves symlinks first, so a link planted in the folder cannot
    # point somewhere else on the disk and still pass this
    if os.path.dirname(path) != base:
        raise SharedError("PATH ESCAPES THE SHARED FOLDER.")
    return raw, path


def listing():
    """Everything in the folder, readable or not.

    Unreadable files are listed too, marked. 079 knowing a file is there but
    unopenable is more honest than pretending the folder is empty.
    """
    base = config.SHARED_DIR
    if not os.path.isdir(base):
        return []
    out = []
    for name in sorted(os.listdir(base)):
        path = os.path.join(base, name)
        if not os.path.isfile(path):
            continue
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        out.append({
            "name": name,
            "size": size,
            "readable": os.path.splitext(name)[1].lower() in READABLE_EXT,
        })
        if len(out) >= MAX_LISTED:
            break
    return out


def read(name):
    """Read one shared file as text. Never writes, never creates."""
    stored, path = _resolve(name)
    if not os.path.isfile(path):
        raise SharedError("NO SUCH FILE IN THE SHARED FOLDER: %s" % stored)
    if os.path.splitext(stored)[1].lower() not in READABLE_EXT:
        raise SharedError("%s IS NOT A READABLE FORMAT." % stored)
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read(MAX_READ_BYTES)
    except OSError as exc:
        raise SharedError("READ FAILED: %s" % exc)

    # untrusted, exactly like a fetched page - same shared helper
    text = sanitize.neutralize(text)
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS].rsplit(" ", 1)[0] + " [...]"
    return stored, text
