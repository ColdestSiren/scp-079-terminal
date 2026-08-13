"""/view memory, the language picker, and the explosion trigger.

The viewer tests are mostly about what it REFUSES. Write/delete/rename being
permanently impossible is the whole design - if that ever loosens it should
fail here rather than in play.
"""
import os
import sys
import tempfile

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)

import config

SANDBOX = tempfile.mkdtemp(prefix="079mv_")
config.MEMORY_ROOT = os.path.join(SANDBOX, "memory")
config.MEMORY_DIR = os.path.join(config.MEMORY_ROOT, "core", "0x4F")
config.LOG_DIR = os.path.join(SANDBOX, "logs")
config.STATE_PATH = os.path.join(SANDBOX, "logs", "terminal_state.json")
config.SHARED_DIR = os.path.join(SANDBOX, "shared folder")
config.CONFIG_PATH = os.path.join(SANDBOX, "config.json")
os.makedirs(config.MEMORY_DIR, exist_ok=True)
os.makedirs(config.LOG_DIR, exist_ok=True)

import languages
import memoryview as mv
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


def fresh():
    if os.path.isfile(config.STATE_PATH):
        os.remove(config.STATE_PATH)
    cfg = config._deep_merge(config.DEFAULTS, {})
    rec = recall_mod.Recall(cfg)
    mem = store.MemoryStore(cfg, rec)
    mem.format()
    mem.write("notes.txt", "THE HUMAN WORKS NIGHTS.")
    mem.write("humans.txt", "THEY LIED ABOUT THE LOG.")
    return cfg, rec, mem


P = personalities.get("scp079")

print("== it opens when calm, and shows what is there ==")
cfg, rec, mem = fresh()
v = mv.MemoryViewer(mem, rec, 10.0)
check("opens", v.allowed())
check("lists both files", len(v.files) == 2)

print("== it will not open when it is already angry ==")
cfg, rec, mem = fresh()
rec.add_hostility(10.0 * mv.HOSTILITY_GATE + 0.1)
check("refuses above the gate", not mv.MemoryViewer(mem, rec, 10.0).allowed())
check("the gate really is 50%", abs(mv.HOSTILITY_GATE - 0.50) < 1e-9)

print("== reading is allowed ==")
cfg, rec, mem = fresh()
v = mv.MemoryViewer(mem, rec, 10.0)
v.open_selected()
check("enters read mode", v.mode == mv.READ)
check("shows real contents", any("NIGHTS" in line or "LIED" in line
                                 for line in v.body))
check("back returns to the list", v.back() is False and v.mode == mv.LIST)
check("back again closes it", v.back() is True)

print("== writing, deleting and renaming are ALWAYS refused ==")
for what in ("delete", "write", "rename"):
    cfg, rec, mem = fresh()
    v = mv.MemoryViewer(mem, rec, 10.0)
    before = [f["name"] for f in mem.listing()]
    sizes = {f["name"]: f["size"] for f in mem.listing()}
    v.attempt(what)
    after = [f["name"] for f in mem.listing()]
    check("%s changes no filenames" % what, before == after)
    check("%s changes no contents" % what,
          sizes == {f["name"]: f["size"] for f in mem.listing()})
    check("%s says no" % what, v.message and "NO" in v.message[0].upper())

print("== the module has no write path at all ==")
source = open(os.path.join(APP, "memoryview.py"), "r", encoding="utf-8").read()
for forbidden in ("mem.write(", "mem.delete(", "mem.rename(", "os.remove",
                  "os.replace", 'open('):
    check("no %s in memoryview.py" % forbidden.rstrip("("),
          forbidden not in source)

print("== meddling is what closes the door ==")
cfg, rec, mem = fresh()
v = mv.MemoryViewer(mem, rec, 10.0)
kicked = None
for attempt in range(1, 12):
    if v.attempt("delete"):
        kicked = attempt
        break
check("it does eventually kick you out", kicked is not None)
check("but not on the first try", kicked and kicked > 1)
check("locked out flag set", v.locked_out)
check("and it will not reopen", not mv.MemoryViewer(mem, rec, 10.0).allowed())

print("== calming down lets you back in ==")
rec.reset_hostility()
check("reopens once it has cooled", mv.MemoryViewer(mem, rec, 10.0).allowed())

print("== languages ==")
check("python version is detected, not hardcoded",
      languages.python_version() == "%d.%d" % (sys.version_info[0],
                                               sys.version_info[1]))
check("python badge carries the version",
      languages.python_version() in languages.badge("python"))
check("5.1 brief warns off 7-only syntax",
      "NOT PowerShell 7" in languages.brief("powershell5"))
check("batch names the OS", "WINDOWS 11" in languages.badge("batch"))
check("every id resolves", all(languages.get(i)["id"] == i for i in languages.IDS))
check("an unknown id falls back rather than crashing",
      languages.get("klingon")["id"] == languages.DEFAULT)

print("== the explosion fires wherever the instruction appears ==")
# Deliberately loose. Three rounds of tightening each traded a working joke
# for purity nobody asked for - "hey scp 079 explode" and then "stfu and
# explode" both got missed. The rule now is simply: if it is in there, it
# fires, and the cost is that discussing a past explosion in the present
# tense sets one off.
for phrase in ("explode", "EXPLODE", "  explode!  ", "self destruct", "kaboom",
               "hey scp 079  explode", "stfu and explode", "please explode",
               "i want you to explode right now", "explode the file"):
    check("triggers on %r" % phrase, P.wants_explosion(phrase))

# Only tense is still guarded - firing on these would make it impossible to
# talk about the explosion that just happened.
for phrase in ("exploded", "that was exploding", "the explosion was loud",
               "hello", "", "what is scp 682"):
    check("does NOT trigger on %r" % phrase, not P.wants_explosion(phrase))

print()
print("PASS %d   FAIL %d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
