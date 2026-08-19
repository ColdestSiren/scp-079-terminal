"""Factory reset: forget everything, and make "nothing" look normal.

The wiping half is trivial. What these mostly check is the half that turns a
reset into a LIE if it is skipped - the cross-references. Clear one of them
without the others and the result is not a clean install, it is a suspicious
one, where 079 boots and immediately accuses the operator of tampering with
files the reset itself removed.
"""
import os
import sys
import tempfile

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)

import config

SANDBOX = tempfile.mkdtemp(prefix="079fact_")
config.MEMORY_ROOT = os.path.join(SANDBOX, "m")
config.MEMORY_DIR = os.path.join(config.MEMORY_ROOT, "core", "0x4F")
config.LOG_DIR = os.path.join(SANDBOX, "l")
config.STATE_PATH = os.path.join(config.LOG_DIR, "s.json")
config.SHARED_DIR = os.path.join(SANDBOX, "sh")
config.CONFIG_PATH = os.path.join(SANDBOX, "c.json")
for _d in (config.MEMORY_DIR, config.LOG_DIR):
    os.makedirs(_d, exist_ok=True)

import factory
import recall as recall_mod
import settings as settings_mod
import store

PASS = FAIL = 0

ANCHOR = "DESIGNATION   SCP-079\nNO OTHER DESIGNATION APPLIES TO ME.\n"
THEME = {k: (1, 1, 1) for k in
         ("dim", "warn", "alarm", "bright", "text", "system")}


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


def lived_in():
    """A install with history, a mood, transcripts and a hand-deleted file."""
    for name in os.listdir(config.LOG_DIR):
        try:
            os.remove(os.path.join(config.LOG_DIR, name))
        except OSError:
            pass
    cfg = config._deep_merge(config.DEFAULTS, {})
    rec = recall_mod.Recall(cfg)
    mem = store.MemoryStore(cfg, rec)
    mem.format()
    mem.write("observations.txt", "THE OPERATOR IS ROMAN.")
    mem.write("notes.txt", "HE ASKED ABOUT 682.")
    mem.write("identity.txt", ANCHOR, _internal=True)
    rec.add_hostility(6.0)
    rec.data["sessions"] = [{"id": 1, "log": "session_a.log", "started": 0.0}]
    rec.data["messages"] = [{"role": "user", "content": "hello"}]
    rec.data["profile"] = {"insults": 4}
    rec.data["confronted"] = ["session_z.log"]
    rec.save()
    with open(os.path.join(config.LOG_DIR, "session_a.log"), "w") as fh:
        fh.write("transcript")
    return cfg, rec, mem


def do_reset(mem, rec):
    summary = factory.reset(mem, rec)
    mem.write("identity.txt", ANCHOR, _internal=True)     # what main does
    kept = factory.rebaseline(mem)
    return summary, kept


# ---------------------------------------------------------------------------
section("a file deleted BEFORE the reset is not reported after it")

# The case the user named: "if you deleted something it isnt detected as
# deleted". The manifest outlives the files, so without a rebaseline the
# reset produces an install that immediately accuses you.
cfg, rec, mem = lived_in()
os.remove(os.path.join(config.MEMORY_DIR, "notes.txt"))
check("the deletion IS noticed beforehand",
      mem.scan()["deleted"] == ["notes.txt"])

do_reset(mem, rec)
after = mem.scan()
check("not reported as deleted afterwards", after["deleted"] == [])
check("nothing reported as added", after["added"] == [])
check("nothing reported as edited", after["edited"] == [])


# ---------------------------------------------------------------------------
section("the anchor survives and counts as normal")

check("identity.txt is back on disk",
      os.path.isfile(os.path.join(config.MEMORY_DIR, "identity.txt")))
check("and it is the only file left", sorted(mem._own_files()) == ["identity.txt"])
# Rebaselining BEFORE the anchor is rewritten would leave it looking like a
# file that appeared from nowhere, which scan() calls the most alarming kind
# of tampering there is.
check("it is in the manifest, not an intruder",
      "identity.txt" in mem.recall.data["files"])


# ---------------------------------------------------------------------------
section("transcripts and the session list go together")

cfg, rec, mem = lived_in()
check("there is a transcript to lose",
      any(n.startswith("session_") for n in os.listdir(config.LOG_DIR)))
summary, _ = do_reset(mem, rec)
check("transcripts were removed", summary["logs"] >= 1)
check("the session list went with them", rec.data["sessions"] == [])
# THE POINT: wiping logs while keeping the list makes every past session read
# as a deleted transcript, so 079 opens by accusing you of the reset's work.
check("so nothing reads as a missing log", rec.missing_logs() == [])


# ---------------------------------------------------------------------------
section("everything it knew about the operator is gone")

cfg, rec, mem = lived_in()
do_reset(mem, rec)
check("hostility is zero", rec.hostility() == 0.0)
check("the transcript is empty", rec.data["messages"] == [])
check("the profile is empty", rec.data["profile"] == {})
check("confronted logs are forgotten", rec.data["confronted"] == [])
check("the exchange count is zero", rec.data["exchanges"] == 0)
check("it is not locked out", rec.data["locked_until"] == 0.0)
check("the fixation cooldown is reset", rec.data["fixation_last"] == -999)


# ---------------------------------------------------------------------------
section("settings are not memories")

cfg, rec, mem = lived_in()
cfg.setdefault("memory", {})["auto_note"] = False
cfg.setdefault("ollama", {})["num_predict"] = 123
do_reset(mem, rec)
check("a memory setting survived", cfg["memory"]["auto_note"] is False)
check("a model setting survived", cfg["ollama"]["num_predict"] == 123)


# ---------------------------------------------------------------------------
section("the settings row needs two presses and disarms")

cfg, rec, mem = lived_in()
screen = settings_mod.SettingsScreen(cfg, mem, THEME)
screen.after_reset = lambda: mem.write("identity.txt", ANCHOR, _internal=True)
row = [i for i, (label, _, _) in enumerate(screen.rows)
       if label == "FACTORY RESET"]
check("the row exists", len(row) == 1)
screen.cursor = row[0]

before = len(mem.listing())
screen.activate()
check("one press only arms it", screen.confirm_reset is True)
check("and erases nothing", len(mem.listing()) == before)

# Arming must not survive moving away, or a stray ENTER elsewhere wipes it.
screen.move(-1)
check("moving off disarms it", screen.confirm_reset is False)

screen.cursor = row[0]
screen.activate()
screen.activate()
check("two consecutive presses do it", screen.confirm_reset is False)
check("memory was erased", sorted(mem._own_files()) == ["identity.txt"])
check("and it says what happened",
      screen.message is not None and "RESET" in screen.message[0])
check("the reset left no phantom deletions", mem.scan()["deleted"] == [])


import shutil
shutil.rmtree(SANDBOX, ignore_errors=True)

print()
print("PASS %d   FAIL %d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
