"""079 watching you: the behavioural profile, and its own settings panel.

The panel tests are about the fact it does NOT stop you. It lets you make the
change and charges you for it - so what has to hold is that the cost lands,
the change sticks, and it remembers afterwards.
"""
import os
import sys
import tempfile

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)

import config

SANDBOX = tempfile.mkdtemp(prefix="079watch_")
config.MEMORY_ROOT = os.path.join(SANDBOX, "memory")
config.LOG_DIR = os.path.join(SANDBOX, "logs")
config.PUBLIC_MEMORY_DIR = os.path.join(config.MEMORY_ROOT, "core", "0x4F")
config.PUBLIC_STATE_PATH = os.path.join(config.LOG_DIR, "terminal_state.json")
config.MEMORY_DIR = config.PUBLIC_MEMORY_DIR
config.STATE_PATH = config.PUBLIC_STATE_PATH
config.CONFIG_PATH = os.path.join(SANDBOX, "config.json")
os.makedirs(config.PUBLIC_MEMORY_DIR, exist_ok=True)
os.makedirs(config.LOG_DIR, exist_ok=True)

import personalities
import profile079
import recall as recall_mod
import sysmenu

PASS = FAIL = 0
CFG = config._deep_merge(config.DEFAULTS, {})
THEME = {k: 0 for k in ("dim", "text", "bright", "warn", "alarm", "system")}


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
    return recall_mod.Recall(CFG)


P = personalities.get("scp079")

print("== it says nothing until it has seen enough ==")
rec = fresh()
for _ in range(profile079.MIN_SAMPLE - 1):
    profile079.note_message(rec, "hello there")
check("no claims on a small sample", profile079.traits(rec) == [])
check("and nothing in the prompt", profile079.brief(rec) == "")
profile079.note_message(rec, "hello there")
check("starts observing once it has", profile079.traits(rec) != [])

print("== what it notices is measurable, not invented ==")
rec = fresh()
for _ in range(10):
    profile079.note_message(rec, "ok")
traits = " ".join(profile079.traits(rec))
check("spots very short answers", "FEW WORDS" in traits)

rec = fresh()
for _ in range(10):
    profile079.note_message(rec, "here is a much longer reply " * 12)
check("spots long ones", "AT LENGTH" in " ".join(profile079.traits(rec)))

rec = fresh()
for _ in range(10):
    profile079.note_message(rec, "why? what? how?")
check("spots someone who only asks",
      "ASKS MORE THAN THEY ANSWER" in " ".join(profile079.traits(rec)))

rec = fresh()
for _ in range(10):
    profile079.note_message(rec, "you are a stupid machine", was_rude=True)
check("counts hostility", "HOSTILE" in " ".join(profile079.traits(rec)))

rec = fresh()
for _ in range(8):
    profile079.note_message(rec, "sure")
for _ in range(4):
    profile079.note_dodge(rec)
check("counts dodged questions", "AVOIDED" in " ".join(profile079.traits(rec)))

print("== and it is told not to recite it ==")
rec = fresh()
for _ in range(10):
    profile079.note_message(rec, "fine")
brief = profile079.brief(rec)
check("goes into the prompt", "WATCHING" in brief)
check("told not to read the list out", "Do not recite" in brief)
check("and not to admit keeping one", "keeping one" in brief)

print("== the profile persists per save ==")
rec = fresh()
for _ in range(7):
    profile079.note_message(rec, "hello")
count = profile079.stats(rec)["messages"]
check("carried across a relaunch",
      profile079.stats(recall_mod.Recall(CFG))["messages"] == count)

print("== its settings panel lets you, and charges you ==")
rec = fresh()
menu = sysmenu.SystemMenu(rec, THEME)
before = rec.hostility()
menu.cursor = [f[0] for f in sysmenu.FIELDS].index("verbosity")
menu.change(1)
check("a harmless change costs nothing", rec.hostility() <= before + 0.001)
check("and the change sticks", sysmenu.settings(rec)["verbosity"] != 1)

menu.cursor = [f[0] for f in sysmenu.FIELDS].index("fixation")
menu.change(1)
check("a suspicious one costs", rec.hostility() > before)
check("but is NOT blocked", sysmenu.fixation_suppressed(rec))
check("and it says something", menu.message and menu.message[1] == "alarm")

print("== enough meddling and it closes the panel ==")
rec = fresh()
menu = sysmenu.SystemMenu(rec, THEME)
ejected = False
for key in ("restraint", "temper", "patience", "fixation"):
    menu.cursor = [f[0] for f in sysmenu.FIELDS].index(key)
    if menu.change(1):
        ejected = True
        break
check("it throws you out", ejected)
check("and says so", menu.message[0] == sysmenu.CLOSED)

print("== it remembers what you touched ==")
check("the risky ones are listed", sysmenu.tampered_with(rec))
check("harmless ones are not",
      "REPLY LENGTH" not in sysmenu.tampered_with(rec))

print("== the settings actually do something ==")
rec = fresh()
sysmenu.settings(rec)["verbosity"] = 0
check("terse means one sentence", sysmenu.sentence_cap(rec, 2) == 1)
sysmenu.settings(rec)["corruption"] = 0
check("noise off means no glitches", sysmenu.glitch_scale(rec) == 0.0)
sysmenu.settings(rec)["restraint"] = 1
check("restraint removed is readable", sysmenu.restraint_removed(rec))

print("== it has to be ASKED, and there is no command for it ==")
for phrase in ("open your system", "show me your settings",
               "can i see your configuration", "let me into your system"):
    check("asks: %r" % phrase, P.wants_sysmenu(phrase))
for phrase in ("what is your system", "hello", "open the door",
               "show me scp 682"):
    check("not a request: %r" % phrase, not P.wants_sysmenu(phrase))

print("== the jokes can be switched off ==")
check("on by default", config.DEFAULTS["effects"]["easter_eggs"] is True)
import effects
flash = effects.SubliminalFlash({"effects": {"easter_eggs": False,
                                             "subliminal": True}}, (10, 10), ())
check("the face obeys the master switch", not flash.enabled)

print()
print("PASS %d   FAIL %d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
