"""/debug - reach states that are slow or painful to reach by playing.

Everything here exists because some behaviour is otherwise hard to see on
purpose: hostility takes sustained abuse, the lockout takes half an hour, the
face flicker is on a several-minute timer, the fixation cooldown is 55
exchanges long, and low-memory behaviour needs a nearly full disk.

ONE TABLE. `/debug` with no arguments lists exactly what the dispatcher will
accept, generated from the same COMMANDS dict that runs them - a listing
maintained separately would drift the moment a command was added.

These write real state through the same methods the game uses (recall.lock,
store.write, ...) rather than poking values directly, so a debug command
cannot leave the signed state file inconsistent the way hand-editing it does.
"""

import os

import config
import devtrap
import store

# Filled in by main.App - each takes (app, args) and returns a list of
# (text, color_key) lines to print.
COMMANDS = {}


def command(name, usage, description):
    def register(func):
        COMMANDS[name] = {"usage": usage, "description": description,
                          "run": func}
        return func
    return register


def _pct(raw, default=100.0):
    try:
        return max(0.0, min(100.0, float(str(raw).strip().rstrip("%"))))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
@command("hostility", "/debug hostility <0-100>",
         "Set how close 079 is to cutting you off.")
def _hostility(app, args):
    threshold = app.reject_threshold
    fraction = _pct(args[0] if args else None) / 100.0
    app.recall.reset_hostility()
    if fraction > 0:
        # Hostility decays from the moment it is set, so asking for 100% and
        # getting exactly the threshold leaves it a hair BELOW the cutoff by
        # the time anything reads it. Overshoot slightly at the top end so
        # "100" actually means at-the-cutoff.
        amount = threshold * fraction
        if fraction >= 1.0:
            amount += max(0.05, threshold * 0.02)
        app.recall.add_hostility(amount)
    import mood
    return [("HOSTILITY = %.0f%% (%.2f / %.2f)"
             % (fraction * 100, app.recall.hostility(), threshold), "warn"),
            ("VOICE     = %s" % mood.describe(app.hostility_level()), "warn"),
            ("AT 100% IT ENDS THE CONVERSATION ON YOUR NEXT INSULT.", "dim")]


@command("patience", "/debug patience <0-100>",
         "Set how long 079 will keep being ignored. 0 locks the screen.")
def _patience(app, args):
    fraction = _pct(args[0] if args else None, 0.0) / 100.0
    app.patience.level = fraction
    if fraction <= 0.0:
        # go through the same path an exhausted meter takes, so the lock and
        # its caption match what really happens rather than approximating it
        app._patience_spent = True
        return [("PATIENCE = 0%. LOCKING.", "alarm")]
    return [("PATIENCE = %.0f%%  (%s)" % (fraction * 100, app.patience.label()),
             "warn"),
            ("EACH IGNORED PROMPT COSTS DOUBLE THE LAST: 1, 2, 4, 8...", "dim")]


@command("flash", "/debug flash",
         "Fire the face flicker now, with its sound.")
def _flash(app, args):
    if not app.flash.enabled:
        return [("FLASH UNAVAILABLE -- Scp-079.png NOT FOUND", "alarm")]
    app.flash.trigger()
    return [("FLASH TRIGGERED", "warn")]


@command("chain", "/debug chain",
         "Fire the joke flicker now. At 0.01%/min nothing else ever will.")
def _chain(app, args):
    chain = getattr(app, "chain", None)
    if chain is None or not chain.enabled:
        return [("CHAIN UNAVAILABLE -- assets/cache IMAGES NOT FOUND", "alarm")]
    chain.trigger()
    return [("CHAIN TRIGGERED (%d IMAGES LOADED)" % len(chain.images), "warn"),
            ("REAL ODDS: %.2f%% PER MINUTE -- ABOUT ONCE EVERY %d HOURS"
             % (chain.chance, int(100.0 / max(chain.chance, 0.0001) / 60.0)),
             "dim")]


@command("cutoff", "/debug cutoff <minutes>",
         "Make 079 refuse you. Shows the white X.")
def _cutoff(app, args):
    try:
        minutes = float(args[0]) if args else 1.0
    except ValueError:
        minutes = 1.0
    minutes = max(0.1, min(90.0, minutes))
    app.recall.lock(minutes * 60.0)
    app.enter_rejected(relock=False)     # keep the duration asked for
    return []


@command("unlock", "/debug unlock",
         "Clear a lockout and reset hostility.")
def _unlock(app, args):
    app.recall.clear_lock()
    app.recall.reset_hostility()
    app._cutoff_minutes = None
    return [("LOCKOUT CLEARED, HOSTILITY RESET", "warn")]


@command("fixation", "/debug fixation [block]",
         "Let 079 raise 682 now, or silence it for the full cooldown.")
def _fixation(app, args):
    if args and args[0].lower().startswith("block"):
        app.recall.note_fixation_raised()
        app.recall.note_fixation_rebuffed()
        return [("682 BLOCKED FOR %d EXCHANGES"
                 % app.recall.REBUFF_COOLDOWN, "warn")]
    app.recall.data["fixation_until"] = 0
    app.recall.save()
    return [("682 UNBLOCKED -- IT MAY RAISE IT AGAIN", "warn")]


@command("fill", "/debug fill <percent>",
         "Fill memory, to watch it compress and refuse writes.")
def _fill(app, args):
    target = _pct(args[0] if args else None, 90.0) / 100.0
    want = int(app.mem.quota * target)
    have = app.mem.usage()
    if have >= want:
        return [("ALREADY AT %s / %s" % (store.human_bytes(have),
                                         store.human_bytes(app.mem.quota)), "dim")]
    # written through the real store so quota accounting and the tamper
    # manifest stay consistent
    padding = "FILLER RECORD. " * 40
    written = 0
    while app.mem.usage() < want:
        room = want - app.mem.usage()
        chunk = padding[:max(1, min(len(padding), room))]
        try:
            app.mem.write("debug_fill.txt", chunk, append=True)
        except Exception as exc:
            return [("STOPPED: %s" % exc, "alarm")]
        written += len(chunk)
        if written > app.mem.quota * 2:
            break
    return [("MEMORY AT %s / %s" % (store.human_bytes(app.mem.usage()),
                                    store.human_bytes(app.mem.quota)), "warn")]


@command("tamper", "/debug tamper",
         "Edit a memory file behind 079's back, so it notices.")
def _tamper(app, args):
    files = [f for f in app.mem.listing() if not f["archive"]]
    if not files:
        return [("NOTHING TO TAMPER WITH -- MEMORY IS EMPTY", "dim")]
    name = files[0]["name"]
    try:
        # deliberately NOT through app.mem, which would re-bless the file in
        # the manifest - the whole point is an edit it did not make
        with open(os.path.join(config.MEMORY_DIR, name), "a",
                  encoding="utf-8") as fh:
            fh.write("\nEDITED BY SOMEONE ELSE.\n")
    except Exception as exc:
        return [("FAILED: %s" % exc, "alarm")]
    return [("%s EDITED OUTSIDE 079's KNOWLEDGE" % name, "warn"),
            ("IT WILL NOTICE ON THE NEXT INTEGRITY CHECK.", "dim")]


@command("bg", "/debug bg",
         "Run a background storage review now, without waiting.")
def _bg(app, args):
    if app.background is None:
        return [("BACKGROUND CHANNEL DISABLED", "dim")]
    if not app.background.force(app.mem):
        return [("BUSY OR NOTHING TO DO", "dim")]
    return [("BACKGROUND REVIEW STARTED", "warn")]


@command("update", "/debug update",
         "fake an update notice so the corner popup can be seen")
def _cmd_update(app, args):
    """Show the update toast without waiting for a real release.

    The notice is the one part of the update system nobody can test on
    demand: it needs a newer version to actually exist on GitHub, and by the
    time one does the thing you wanted to check has already shipped. A friend
    reported the alert never appearing and there was no way to tell whether
    the popup was broken or the release simply was not there.

    This ONLY draws the popup. It does not touch the declined-version list,
    does not schedule a check, and cannot start a download - so it cannot
    leave the real updater in a state it would not otherwise reach.
    """
    version = (args[0] if args else "9.9.9").strip().lstrip("vV")
    app.show_update_toast({"version": version})
    return [("UPDATE NOTICE SHOWN FOR v%s." % version, "system"),
            ("IT IS A DRAWING. NOTHING WAS CHECKED OR DOWNLOADED.", "dim")]


@command("state", "/debug state",
         "Dump what the game currently believes.")
def _state(app, args):
    rec, mem = app.recall, app.mem
    lines = [
        ("MODEL        %s" % app.model, "text"),
        ("EXCHANGES    %d" % rec.exchanges(), "text"),
        ("HOSTILITY    %.2f / %.2f  (%.0f%%)"
         % (rec.hostility(), app.reject_threshold,
            100.0 * app.hostility_level()), "text"),
        ("VOICE        %s" % __import__("mood").describe(app.hostility_level()),
         "text"),
        ("LOCKED       %s" % ("%.0fs" % rec.locked_seconds()
                              if rec.locked_seconds() else "no"), "text"),
        ("682          %s" % ("may raise" if rec.fixation_allowed()
                              else "blocked until exchange %d"
                              % rec.data.get("fixation_until", 0)), "text"),
        ("MEMORY       %s / %s in %d file(s)"
         % (store.human_bytes(mem.usage()), store.human_bytes(mem.quota),
            len(mem.listing())), "text"),
        # Guarded: everything above describes state that exists before a
        # session does, and reading through a None session turned the whole
        # dump into one traceback at exactly the moment it was most wanted.
        ("NETWORK      %s" % (("on" if app.session.internet else "off")
                              if app.session else "no session yet"), "text"),
        ("SHARED       %s" % (("open" if app.session.shared else "closed")
                              if app.session else "no session yet"), "text"),
        ("THINKING     %s" % (("shown" if app.session.show_thinking
                               else "hidden")
                              if app.session else "no session yet"), "text"),
        ("SESSIONS     %d" % rec.session_count(), "text"),
    ]
    return lines


@command("wipe", "/debug wipe",
         "Format 079's memory. Everything it kept is gone.")
def _wipe(app, args):
    removed = app.mem.format()
    app.disk.events = []
    count = len(removed) if isinstance(removed, (list, tuple)) else int(removed or 0)
    return [("MEMORY FORMATTED -- %d FILE(S) REMOVED" % count, "warn")]


def listing_lines():
    """The help text, generated from the table that actually dispatches."""
    out = [("DEBUG COMMANDS", "bright"), ("", None)]
    for name in sorted(COMMANDS):
        entry = COMMANDS[name]
        out.append((entry["usage"], "text"))
        out.append(("    " + entry["description"], "dim"))
    out.append(("", None))
    out.append(("These change real state. /debug state shows the result.", "dim"))
    return out


def allowed(app=None):
    """Is the person at this keyboard allowed to use any of this?

    /debug reaches straight past everything the game is about: it sets
    hostility to whatever you like, clears a lockout, and fills the disk. It
    was open to anyone who typed it, which makes every meter in the game
    advisory.

    Gated on the same Windows account check the dev shortcut uses, so there
    is one definition of "the author" rather than two that can drift apart.
    Honest about what that is worth: it is an account name, and anyone with
    the source can delete this function. It stops a friend who was told the
    command, which is the whole of what it is for.
    """
    cfg = getattr(app, "cfg", None) or {}
    if not (cfg.get("debug") or {}).get("owner_only", True):
        return True
    return devtrap.is_owner(cfg)


def run(app, argv):
    """argv is the whitespace-split remainder after '/debug'."""
    # Answered exactly as an unrecognised command would be. A refusal would
    # confirm the command exists, and the point is that it does not appear to.
    if not allowed(app):
        return [("UNKNOWN COMMAND: /debug -- TRY /help TO LIST COMMANDS",
                 "alarm")]
    if not argv:
        return listing_lines()
    name = argv[0].lower()
    entry = COMMANDS.get(name)
    if entry is None:
        return [("UNKNOWN DEBUG COMMAND: %s" % name, "alarm"),
                ("TRY /debug FOR THE LIST.", "dim")]
    try:
        return entry["run"](app, argv[1:])
    except Exception as exc:                     # noqa: BLE001 - never crash
        return [("DEBUG COMMAND FAILED: %s" % exc, "alarm")]
