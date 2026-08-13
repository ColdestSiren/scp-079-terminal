"""/debug - the listing must describe exactly what the dispatcher accepts.

The real risk with a debug menu is not that a command breaks; it is that the
menu and the dispatcher drift, so it advertises something that no longer
works. Both come from one dict, and these check that stays true.
"""
import os
import sys
import tempfile

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)

import config

SANDBOX = tempfile.mkdtemp(prefix="079dbg_")
config.MEMORY_DIR = os.path.join(SANDBOX, "memory")
config.LOG_DIR = os.path.join(SANDBOX, "logs")
config.STATE_PATH = os.path.join(SANDBOX, "logs", "terminal_state.json")
config.SHARED_DIR = os.path.join(SANDBOX, "shared folder")
config.CONFIG_PATH = os.path.join(SANDBOX, "config.json")
for d in (config.MEMORY_DIR, config.LOG_DIR, config.SHARED_DIR):
    os.makedirs(d, exist_ok=True)

import debugcmds
import personalities
import recall as recall_mod
import store

PASS = FAIL = 0


def check(label, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print("  FAIL:", label)


class FakeDisk:
    def __init__(self):
        self.events = []


class FakeSession:
    internet = False
    shared = False
    show_thinking = False


class FakeApp:
    """Only what debugcmds actually touches."""
    def __init__(self):
        self.cfg = config._deep_merge(config.DEFAULTS, {})
        self.personality = personalities.get("scp079")
        self.recall = recall_mod.Recall(self.cfg)
        self.mem = store.MemoryStore(self.cfg, self.recall)
        self.disk = FakeDisk()
        self.session = FakeSession()
        self.background = None
        self.model = "test-model"
        self.reject_threshold = float(self.cfg["rejection"]["threshold"])
        self._cutoff_minutes = None
        self.flash = type("F", (), {"enabled": False, "trigger": lambda s: None})()
        self.rejected = False

    def hostility_level(self):
        return min(1.0, self.recall.hostility() / self.reject_threshold)

    def enter_rejected(self, relock=True):
        # mirrors the real signature: relock=False means the caller already
        # set the lock it wants and this must not overwrite it
        self.rejected = True
        self.relocked = relock


print("== the listing and the dispatcher come from one table ==")
listed = debugcmds.run(None, [])
text = " ".join(line for line, _ in listed)
for name in debugcmds.COMMANDS:
    check("%s is documented" % name, ("/debug " + name) in text)
check("every documented command has a handler",
      all(callable(e["run"]) for e in debugcmds.COMMANDS.values()))
check("every one has a description",
      all(e["description"] for e in debugcmds.COMMANDS.values()))

print("== unknown commands are refused, not crashed on ==")
out = debugcmds.run(FakeApp(), ["nonsense"])
check("says it is unknown", any("UNKNOWN" in line for line, _ in out))

print("== hostility can be set to a fraction of the real threshold ==")
app = FakeApp()
debugcmds.run(app, ["hostility", "100"])
check("100 reaches the cutoff", app.recall.hostility() >= app.reject_threshold)
debugcmds.run(app, ["hostility", "50"])
check("50 is about half", 0.4 <= app.hostility_level() <= 0.6)
debugcmds.run(app, ["hostility", "0"])
check("0 clears it", app.hostility_level() < 0.01)
debugcmds.run(app, ["hostility", "banana"])
check("junk does not crash", True)

print("== cutoff locks, unlock clears ==")
app = FakeApp()
debugcmds.run(app, ["cutoff", "5"])
check("locked", app.recall.locked_seconds() > 250)
check("and shows the refusal screen", app.rejected)
check("without overwriting the duration asked for", app.relocked is False)
debugcmds.run(app, ["unlock"])
check("unlocked", app.recall.locked_seconds() == 0)

print("== fixation can be freed and blocked ==")
app = FakeApp()
debugcmds.run(app, ["fixation", "block"])
check("blocked", not app.recall.fixation_allowed())
debugcmds.run(app, ["fixation"])
check("freed", app.recall.fixation_allowed())

print("== fill respects the real quota, wipe empties ==")
app = FakeApp()
debugcmds.run(app, ["fill", "80"])
used = app.mem.usage()
check("filled to roughly the asked-for level",
      0.7 <= used / float(app.mem.quota) <= 1.0)
check("never exceeds quota", used <= app.mem.quota)
debugcmds.run(app, ["wipe"])
check("wiped", app.mem.usage() == 0)

print("== tamper is detectable, and does not re-bless the file ==")
app = FakeApp()
app.mem.write("notes.txt", "ORIGINAL")
app.mem.accept()
debugcmds.run(app, ["tamper"])
found = app.mem.scan()
check("the edit is noticed", any(found.get(k) for k in found))

print("== state reports without needing a live model ==")
app = FakeApp()
out = debugcmds.run(app, ["state"])
joined = " ".join(line for line, _ in out)
for field in ("EXCHANGES", "HOSTILITY", "MEMORY", "682", "NETWORK"):
    check("state shows %s" % field, field in joined)

print()
print("PASS %d   FAIL %d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
