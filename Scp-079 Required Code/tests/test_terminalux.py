"""What the terminal itself says back, as opposed to what 079 says.

Two complaints from the same live capture, both about the machine's own
voice rather than the model's.

FIRST: `/view court.txt` is the obvious thing to type once 079 has just told
you it wrote court.txt. It is not a real command, which is fine - but the
answer was `UNKNOWN COMMAND: /view_court.txt`, naming something the player
never typed, because the argument had already been glued onto the command by
the time anything looked at it. An error that misquotes you is worse than no
error.

SECOND: the SYS panel held four identical `MEMORY VIEW CLOSED` lines. Every
one of them was real - the viewer really was opened and closed four times -
but the panel only has four rows, so one repeated action pushed everything
else off it and said nothing new in exchange.
"""
import os
import shutil
import sys
import tempfile

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)

import config

SANDBOX = tempfile.mkdtemp(prefix="079tux_")
config.MEMORY_ROOT = os.path.join(SANDBOX, "memory")
config.MEMORY_DIR = os.path.join(config.MEMORY_ROOT, "core", "0x4F")
config.LOG_DIR = os.path.join(SANDBOX, "logs")
config.STATE_PATH = os.path.join(SANDBOX, "logs", "terminal_state.json")
config.SHARED_DIR = os.path.join(SANDBOX, "shared folder")
config.ASSET_DIR = os.path.join(SANDBOX, "assets")
config.CONFIG_PATH = os.path.join(SANDBOX, "config.json")
os.makedirs(config.MEMORY_DIR, exist_ok=True)
os.makedirs(config.LOG_DIR, exist_ok=True)

import pygame
pygame.display.init()
pygame.font.init()

import debugcmds
import devtrap
import diskpanel
import main as main_mod

PASS = FAIL = 0


def check(label, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print("  FAIL:", label)


def section(title):
    print()
    print("--", title)


class FakeSession:
    busy = False
    internet = False
    shared = False
    show_thinking = False
    pending_commands = ()
    pending_unknown = ()
    pending_code = ()

    def __init__(self):
        self.sent = []

    def send(self, text, log_as=None, remember=True):
        self.sent.append(text)
        return True

    def poll(self):
        return []

    def note(self, text):
        pass

    def log(self, who, text):
        pass

    def record(self, u, r):
        pass

    def cancel(self):
        pass


def make_app():
    cfg = config._deep_merge(config.DEFAULTS, {})
    cfg["sound"]["enabled"] = False
    cfg["effects"]["random_events"] = False
    cfg["effects"]["idle_interruptions"] = False
    app = main_mod.App(cfg)
    app.audio.enabled = False
    app.stage = "chat"
    app.recall.data["messages"] = []
    app.session = FakeSession()
    app.session.gaslight_tracker = app.gaslight
    return app


def screen_text(app):
    out = []
    for entry in app.console.entries():
        if isinstance(entry, tuple):
            out.append(entry[1])
        else:
            out.append("".join(seg[1] for seg in entry))
    return "\n".join(out)


# ---------------------------------------------------------------------------
section("a wrong argument to /view is answered with what /view takes")

app = make_app()
check("the command is still handled here, not sent to 079",
      app.handle_operator_command("/view court.txt") is True)
check("and it never reached the model", app.session.sent == [])

_out = screen_text(app).upper()
check("it says what the command actually is", "/VIEW MEMORY" in _out)
check("it does not quote a command nobody typed",
      "VIEW_COURT" not in _out)
check("and it does not call it unknown", "UNKNOWN COMMAND" not in _out)
check("the viewer did not open on a bad argument", app.stage == "chat")

# The working forms still work, including bare /view - that one was already
# right and is easy to break while fixing the one next to it.
for _cmd in ("/view", "/view memory", "/view mem", "/memory", "/mem memory"):
    a = make_app()
    check("%r opens the viewer" % _cmd,
          a.handle_operator_command(_cmd) is True and a.stage == "memview")

# An argument that is not the word "memory" gets the hint whichever alias
# was used to get there.
for _cmd in ("/view notes.txt", "/memory court.txt", "/mem 1"):
    a = make_app()
    check("%r gets the hint instead" % _cmd,
          a.handle_operator_command(_cmd) is True and a.stage == "chat"
          and "/VIEW MEMORY" in screen_text(a).upper())


# ---------------------------------------------------------------------------
section("the panel counts a repeat instead of printing it again")

def panel_of(app):
    """A bare panel, built the way the app builds its own."""
    return diskpanel.DiskPanel(app.theme, app.size)


_app = make_app()
panel = panel_of(_app)

panel.note_sys("MEMORY VIEW CLOSED")
check("the first one is just itself", panel.notices[:1] == ["MEMORY VIEW CLOSED"])
panel.note_sys("MEMORY VIEW CLOSED")
check("the second becomes a count", panel.notices[:1] == ["MEMORY VIEW CLOSED x2"])
panel.note_sys("MEMORY VIEW CLOSED")
panel.note_sys("MEMORY VIEW CLOSED")
check("and it keeps counting", panel.notices[:1] == ["MEMORY VIEW CLOSED x4"])
check("without using up the panel", len(panel.notices) == 1)

# The count is not a filter. A different notice is a different line, and the
# repeat behind it stays exactly as it was.
panel.note_sys("FULL SCREEN ON")
check("a different notice goes on top",
      panel.notices[0] == "FULL SCREEN ON")
check("and the counted one is untouched beneath it",
      panel.notices[1] == "MEMORY VIEW CLOSED x4")
panel.note_sys("MEMORY VIEW CLOSED")
check("a repeat that is no longer consecutive starts over",
      panel.notices[0] == "MEMORY VIEW CLOSED"
      and panel.notices[1] == "FULL SCREEN ON")

# Only the panel's own suffix counts. A notice that genuinely ends in
# something like "x2" must not be read as a tally of itself.
panel2 = panel_of(_app)
panel2.note_sys("SPEED x2")
panel2.note_sys("SPEED x2")
check("an x-suffix in the text is not mistaken for a count",
      panel2.notices[0] == "SPEED x2 x2")

# It still fills up and still drops the oldest.
panel3 = panel_of(_app)
for _i in range(diskpanel.NOTICES + 3):
    panel3.note_sys("NOTICE %d" % _i)
check("the panel is still bounded", len(panel3.notices) == diskpanel.NOTICES)
check("and keeps the newest", panel3.notices[0] == "NOTICE %d"
      % (diskpanel.NOTICES + 2))

# The flash is what makes a repeat visible at all now, so it has to fire on
# the counted ones too.
panel4 = panel_of(_app)
panel4.note_sys("MEMORY VIEW CLOSED")
panel4.update(1.0)
check("the flash has faded", panel4._sys_flash == 0.0)
panel4.note_sys("MEMORY VIEW CLOSED")
check("a counted repeat still flashes", panel4._sys_flash > 0.0)


# ---------------------------------------------------------------------------
section("and closing the viewer really does notice once per close")

app = make_app()
app.handle_operator_command("/view memory")
check("open", app.stage == "memview")
app.close_memory_viewer()
app.close_memory_viewer()          # the second call is the one that used to
app.close_memory_viewer()          # be suspected of double-noticing
check("back in chat", app.stage == "chat")
check("one notice for one close",
      app.disk.notices[0] == "MEMORY VIEW CLOSED")

app.handle_operator_command("/view memory")
app.close_memory_viewer()
check("two closes read as two, on one row",
      app.disk.notices[0] == "MEMORY VIEW CLOSED x2")
check("and nothing else was pushed off",
      len(app.disk.notices) == 1)


# ---------------------------------------------------------------------------
section("the first lockout says how to skip it, once")
# Sitting out a thirty-minute timeout is not the game. Someone who has just
# been shut out for the first time should be told the way past it exists;
# after that they know, and repeating it every time turns a consequence into
# a formality.

app = make_app()
check("nothing has been shown yet",
      not app.recall.data.get("bypass_hint_seen", False))
app.enter_rejected()
check("the first lockout offers the way out", app._show_bypass_hint)
check("and remembers that it did",
      app.recall.data.get("bypass_hint_seen") is True)

app.recall.clear_lock()
app.enter_rejected()
check("the second lockout does not repeat it", not app._show_bypass_hint)

# It survives a relaunch, which is the only version of "once" that means
# anything - otherwise every launch is a first lockout.
app2 = make_app()
check("and it is still remembered next launch",
      app2.recall.data.get("bypass_hint_seen") is True)
app2.enter_rejected()
check("so a new launch does not offer it again", not app2._show_bypass_hint)

# A factory reset is meant to look like a clean install, and a clean install
# shows the hint.
import factory
factory.clear_recall(app2.recall)
check("a factory reset clears the flag",
      app2.recall.data.get("bypass_hint_seen") is False)

section("and it names the key that actually works")
# The failure this guards against is a hint that tells you to press keys the
# handler does not test. The label is DERIVED from the binding rather than
# written beside it, so this cannot drift.
check("the label spells the binding",
      devtrap.bypass_label()
      == "CTRL+" + pygame.key.name(devtrap.BYPASS_KEY).upper())
check("and the modifier is the one it names",
      devtrap.BYPASS_MOD == pygame.KMOD_CTRL and "CTRL" in devtrap.bypass_label())


class FakeKey:
    def __init__(self, key, mod=0):
        self.key, self.mod = key, mod


check("the handler agrees with the label",
      devtrap.pressed_bypass(FakeKey(devtrap.BYPASS_KEY, pygame.KMOD_CTRL)))
check("the key alone is not enough",
      not devtrap.pressed_bypass(FakeKey(devtrap.BYPASS_KEY, 0)))
check("nor the modifier with the wrong key",
      not devtrap.pressed_bypass(FakeKey(pygame.K_F11, pygame.KMOD_CTRL)))

# The bypass really does end a lockout, or the hint is a lie.
app3 = make_app()
app3.recall.reset_hostility()
app3.enter_rejected()
check("locked", app3.stage == "rejected" and app3.recall.locked_seconds() > 0)
app3.handle_key(FakeKey(devtrap.BYPASS_KEY, pygame.KMOD_CTRL))
check("the advertised key clears it", app3.recall.locked_seconds() == 0.0)
check("and puts you back at the menu", app3.stage == "menu")

section("but it does not become a key to anything else")
# Telling every local player the shortcut changed what it may do. Skipping a
# wait costs nobody anything; opening someone else's code-locked save slot is
# a different thing wearing the same keys.
import devtrap as _dt
_real_user = _dt.current_user
try:
    _dt.current_user = lambda: "somebody-else"
    app4 = make_app()
    app4.stage = "boot"
    app4._pending_slot = "slot2"
    app4.code_buffer = ""
    app4.boot = None
    app4.type_boot_code(FakeKey(devtrap.BYPASS_KEY, pygame.KMOD_CTRL))
    check("a stranger does not get into the slot",
          app4._pending_slot == "slot2")
    check("and is told so rather than silently ignored",
          "NOT YOUR SLOT" in screen_text(app4).upper())
    # allowed() takes the APP, not the cfg - passing the wrong one makes
    # this pass for the wrong reason, which it did on the first attempt.
    check("nor does it hand over the debug menu",
          debugcmds.allowed(app4) is False)
    check("and the owner still has it",
          (setattr(_dt, "current_user", lambda: devtrap.DEFAULT_OWNER),
           debugcmds.allowed(app4))[1] is True)
    _dt.current_user = lambda: "somebody-else"
finally:
    _dt.current_user = _real_user


shutil.rmtree(SANDBOX, ignore_errors=True)

print()
print("PASS %d   FAIL %d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
