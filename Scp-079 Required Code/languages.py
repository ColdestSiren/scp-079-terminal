"""Which language 079 writes code in, and what to call it on screen.

The version matters more than it looks. "Write me a script" without a target
gets you PowerShell 7 syntax on a machine running 5.1, or f-strings on an old
Python - code that looks right and does not run. Naming the target in the
prompt is the cheap fix, and showing it on the block is how you know what you
are pasting.

Python's version is DETECTED rather than assumed: the interpreter running the
game is the one the player has, so that is the one to write for.
"""

import subprocess
import sys

# id, menu label, and the sentence handed to the model.
_DEFS = [
    {
        "id": "python",
        "label": "PYTHON",
        "badge": "PYTHON",
        "prompt": ("Write Python %(version)s. Standard library only unless "
                   "they ask otherwise. It runs on Windows 11."),
    },
    {
        "id": "powershell5",
        "label": "POWERSHELL 5.1",
        "badge": "POWERSHELL 5.1",
        "prompt": ("Write Windows PowerShell 5.1 for Windows 11. NOT "
                   "PowerShell 7 - no ternary operator, no ?? operator, no "
                   "&& or || chaining, no -AsHashtable. Those are parse "
                   "errors in 5.1."),
    },
    {
        "id": "powershell7",
        "label": "POWERSHELL 7",
        "badge": "POWERSHELL 7",
        "prompt": "Write PowerShell 7 for Windows 11.",
    },
    {
        "id": "batch",
        "label": "BATCH / CMD",
        "badge": "BATCH - WINDOWS 11",
        "prompt": ("Write a Windows 11 batch file for cmd.exe. Remember "
                   "delayed expansion when setting variables inside a block."),
    },
    {
        "id": "web",
        "label": "WEB (HTML/CSS/JS)",
        "badge": "WEB",
        "prompt": ("Write HTML, CSS and JavaScript that runs in a modern "
                   "browser with no build step and no frameworks."),
    },
]

IDS = [d["id"] for d in _DEFS]
DEFAULT = "python"

_python_version = None


def python_version():
    """The version actually running this, e.g. '3.13'. Cached."""
    global _python_version
    if _python_version is None:
        _python_version = "%d.%d" % (sys.version_info[0], sys.version_info[1])
    return _python_version


def _fill(entry):
    out = dict(entry)
    if entry["id"] == "python":
        version = python_version()
        out["badge"] = "PYTHON %s" % version
        out["label"] = "PYTHON %s" % version
        out["prompt"] = entry["prompt"] % {"version": version}
    return out


def get(language_id):
    for entry in _DEFS:
        if entry["id"] == language_id:
            return _fill(entry)
    return _fill(_DEFS[0])


def all_languages():
    return [_fill(entry) for entry in _DEFS]


def badge(language_id):
    """Short label shown beside a code block's copy button."""
    return get(language_id)["badge"]


def label(language_id):
    return get(language_id)["label"]


def brief(language_id):
    """The block appended to the system prompt on a coding model."""
    entry = get(language_id)
    return ("\n\nWHEN YOU WRITE CODE:\n%s\n"
            "Put it in a fenced block. Do not explain it unless asked."
            % entry["prompt"])
