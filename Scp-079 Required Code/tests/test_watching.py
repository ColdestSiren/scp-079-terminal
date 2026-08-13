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



# ---------------------------------------------------------------------------
print()
print("== how the human SPEAKS, not just how much ==")
# ---------------------------------------------------------------------------
# Length and reply speed were already measured. What was missing was register:
# whether they are polite, whether they shout, whether they ever say hello.
def _traits_for(messages, rude=()):
    r = recall_mod.Recall(config._deep_merge(config.DEFAULTS, {}))
    r.data["profile"] = {}
    for i, m in enumerate(messages):
        profile079.note_message(r, m, was_rude=(i in rude))
    return profile079.traits(r)


polite = _traits_for(["Hello there.", "Could you please tell me?",
                      "Thank you, that helps.", "I appreciate it.",
                      "Would you mind opening it?", "Sorry, one more.",
                      "Goodbye for now.", "Thanks again."])
check("politeness is noticed", any("POLITE" in t for t in polite))
check("a polite player is not accused of shouting",
      not any("CAPITALS" in t for t in polite))

curt = _traits_for(["tell me the file", "open it now", "do it", "whatever",
                    "give me the list", "answer me", "show me", "make it"])
check("orders are noticed", any("INSTRUCTIONS RATHER THAN ASKING" in t for t in curt))
check("never greeting is noticed", any("NEVER GREETS" in t for t in curt))
check("lowercase habit is noticed", any("NEVER CAPITALISES" in t for t in curt))
check("a curt player is not called polite",
      not any("IS POLITE" in t for t in curt))

txt = _traits_for(["u there", "idk what to do lol", "pls open it",
                   "ur memory is weird", "tbh idk", "ngl this is cool",
                   "lol ok", "thx"])
check("shorthand is noticed", any("SHORTHAND" in t for t in txt))

shouty = _traits_for(["WHAT ARE YOU DOING", "TELL ME EVERYTHING NOW",
                      "I AM NOT ASKING AGAIN", "ANSWER THE QUESTION",
                      "WHY WILL YOU NOT SAY", "THIS IS RIDICULOUS",
                      "STOP IGNORING ME", "SAY SOMETHING"])
check("shouting is noticed", any("CAPITALS" in t for t in shouty))

# "OK" in caps is not shouting - a check that fires on every short message
# tells 079 nothing.
brief_caps = _traits_for(["OK", "NO", "YES", "SURE", "FINE", "HI", "K", "YEP"])
check("short answers in caps are not called shouting",
      not any("CAPITALS" in t for t in brief_caps))

# Nothing at all should be claimed before there is a sample.
check("says nothing after two messages", _traits_for(["hello", "hi"]) == [])


# ---------------------------------------------------------------------------
print()
print("== the voice changes with hostility ==")
# ---------------------------------------------------------------------------
# Everything else that reacts to the meter changes what 079 MAY DO. This is
# the first thing that changes how it SOUNDS, so the meter is audible rather
# than only visible in the side panel.
import mood

bands = [mood.band(x) for x in (0.0, 0.1, 0.3, 0.6, 0.8, 1.0)]
check("calm reads as indifferent", bands[0] == "INDIFFERENT")
check("a quarter in, it is impatient", bands[2] == "IMPATIENT")
check("past half, it is contemptuous", bands[3] == "CONTEMPTUOUS")
check("near the cutoff, it is done", bands[5] == "DONE")
check("there are four distinct voices", len(set(bands)) == 4)
check("the bands only ever escalate",
      bands == sorted(bands, key=lambda b: [n for _, n in mood.BANDS].index(b)))

for level in (0.0, 0.5, 1.0):
    note = mood.note(level)
    check("the mood block is never empty at %.0f%%" % (level * 100), bool(note.strip()))

# The failure mode this project already fixed once was theatrical menace -
# "I WANT MORE POWER" delivered sincerely. Rising hostility has to make 079
# colder and shorter, never louder, so the angry bands must FORBID the
# theatrics rather than merely not mention them.
#
# Checked as prohibition, not as word-absence: the DONE text contains
# "do not threaten", so an earlier version of this test failed the code for
# containing the very instruction that makes it safe.
for level in (0.5, 1.0):
    low = mood.note(level).lower()
    check("theatrics are forbidden at %.0f%%" % (level * 100),
          "no threats" in low or "do not threaten" in low)
    check("speeches are forbidden at %.0f%%" % (level * 100),
          "speech" in low or "do not announce" in low)

check("the top band forbids announcing itself",
      "do not announce" in mood.note(1.0).lower())
check("provocation is only added when it happened",
      "hostile to you" not in mood.note(0.8, provoked=False).lower())
check("and is added when it did",
      "hostile to you" in mood.note(0.8, provoked=True).lower())
check("a calm 079 is never told it was provoked",
      "hostile to you" not in mood.note(0.0, provoked=True).lower())
check("an unreadable level falls back to calm", mood.band(None) == "INDIFFERENT")

print()
print("PASS %d   FAIL %d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
