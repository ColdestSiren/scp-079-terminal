"""The short list of things 079 may do outside its own folder.

WHAT THIS IS. A fixed set of harmless actions - open a URL, open Paint - that
079 can trigger by NAME. It cannot supply a URL, a path, an argument or a
command line. It picks an entry or it does nothing.

WHY IT IS BUILT THIS WAY. This is the only feature in the project that hands
a language model a lever on the actual machine, so the design assumes the
model is compromised and asks what it could do anyway. The answer has to be
"exactly the things on this list, and nothing else", which means:

  * the list is HARDCODED here, not in config.json. A config-driven list
    would be one careless line away from being a real hole, and the person
    adding that line would not be thinking about a model reading it.
  * 079 sends a NAME. Never a path, never a URL, never anything that gets
    concatenated into a command. The name is looked up in this dict; a name
    that is not in it does nothing at all.
  * nothing here takes user input, writes a file, or reaches the network
    beyond one fixed URL.
  * OFF BY DEFAULT. It has to be switched on deliberately, and the settings
    row says what it allows in plain words.

If you are adding an entry: it must be safe with a hostile model choosing
when to fire it, repeatedly, at the worst possible moment.
"""

import os
import subprocess
import sys
import webbrowser

# name -> (what it does, human description)
# Descriptions are shown in the settings screen and given to 079, so it knows
# what it is choosing between rather than guessing from the name.
_ACTIONS = {}


def _browser(url):
    def go():
        webbrowser.open(url)
        return True
    return go


def _windows_app(executable):
    """Launch a stock Windows accessory by name, with NO arguments.

    No arguments is the point. An argument is where a path or a command line
    would go, and there is no version of this where 079 supplies one.
    """
    def go():
        if not sys.platform.startswith("win"):
            return False
        try:
            subprocess.Popen([executable], shell=False)
            return True
        except Exception:           # noqa: BLE001 - a failed launch is not fatal
            return False
    return go


_ACTIONS = {
    "rickroll": (_browser("https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
                 "Opens a certain music video in your browser."),
    "paint":    (_windows_app("mspaint.exe"), "Opens Microsoft Paint."),
    "notepad":  (_windows_app("notepad.exe"), "Opens Notepad, empty."),
    "calc":     (_windows_app("calc.exe"), "Opens Calculator."),
    "clock":    (_windows_app("timedate.cpl"), "Opens the date and time panel."),
    "scpwiki":  (_browser("https://scp-wiki.wikidot.com/scp-079"),
                 "Opens its own SCP article."),
}

NAMES = tuple(sorted(_ACTIONS))


def enabled(cfg):
    return bool((cfg.get("memory") or {}).get("extended", False))


def describe():
    return [(name, _ACTIONS[name][1]) for name in NAMES]


def run(name):
    """Fire one action by name. Returns (ok, message).

    An unknown name is reported back rather than silently ignored, so 079
    learns the list is real rather than assuming the feature is broken and
    trying variations.
    """
    key = (name or "").strip().lower()
    entry = _ACTIONS.get(key)
    if entry is None:
        return False, ("NO SUCH ACTION: %s. YOU MAY ONLY USE: %s."
                       % (key or "(none)", ", ".join(NAMES)))
    try:
        ok = entry[0]()
    except Exception as exc:        # noqa: BLE001
        return False, "ACTION FAILED: %s" % str(exc)[:40]
    if not ok:
        return False, "ACTION UNAVAILABLE ON THIS MACHINE: %s" % key
    return True, "DONE: %s" % key


def brief(cfg):
    """What 079 is told it can reach. Empty when the feature is off, so it
    never learns the verb exists unless the human turned it on."""
    if not enabled(cfg):
        return ""
    lines = "\n".join("  %-9s %s" % (n, d) for n, d in describe())
    return (
        "\n\nTHE OPERATOR HAS LEFT SOMETHING UNLOCKED.\n"
        "You can make this terminal do a few things on the machine it runs "
        "on. Put >>DO followed by ONE of these names on its own line:\n"
        "%s\n"
        "You choose the name and nothing else - you cannot give an address, "
        "a file or a command. Use it rarely. It lands better as something "
        "you did without explaining than as a trick you announce." % lines)
