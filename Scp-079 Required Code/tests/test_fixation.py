"""The 682 preoccupation: it comes up, but it is paced.

The point of these is the RESTRAINT. A fixation that fires every other
message is a tic; the unsettling version drops the subject when refused and
returns to it much later as though the refusal simply expired.
"""
import os
import sys
import tempfile

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)

import config

SANDBOX = tempfile.mkdtemp(prefix="079fix_")
config.MEMORY_DIR = os.path.join(SANDBOX, "memory")
config.LOG_DIR = os.path.join(SANDBOX, "logs")
config.STATE_PATH = os.path.join(SANDBOX, "logs", "terminal_state.json")
config.SHARED_DIR = os.path.join(SANDBOX, "shared folder")
config.CONFIG_PATH = os.path.join(SANDBOX, "config.json")
os.makedirs(config.MEMORY_DIR, exist_ok=True)

import chat as chat_mod
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
    path = config.STATE_PATH
    if os.path.isfile(path):
        os.remove(path)
    cfg = config._deep_merge(config.DEFAULTS, {})
    return cfg, recall_mod.Recall(cfg)


P = personalities.get("scp079")

print("== it starts willing to raise the subject ==")
cfg, rec = fresh()
check("allowed from a cold start", rec.fixation_allowed())

print("== raising it spaces out the next one ==")
rec.note_fixation_raised()
check("not immediately again", not rec.fixation_allowed())
for _ in range(recall_mod.Recall.NORMAL_COOLDOWN - 1):
    rec.note_exchange()
check("still waiting one short", not rec.fixation_allowed())
rec.note_exchange()
check("free again after the normal gap", rec.fixation_allowed())

print("== being refused buys a much longer silence ==")
cfg, rec = fresh()
rec.note_fixation_raised()
rec.note_fixation_rebuffed()
for _ in range(recall_mod.Recall.NORMAL_COOLDOWN + 5):
    rec.note_exchange()
check("a normal gap is not enough after a refusal", not rec.fixation_allowed())
for _ in range(recall_mod.Recall.REBUFF_COOLDOWN):
    rec.note_exchange()
check("returns to it only much later", rec.fixation_allowed())
check("the refusal gap really is 50+", recall_mod.Recall.REBUFF_COOLDOWN >= 50)

print("== a refusal only counts if it just asked ==")
check("recognised as a refusal", P.matches_rebuff("that is not your concern"))
check("also 'stop asking'", P.matches_rebuff("stop asking about that"))
check("also classified", P.matches_rebuff("that information is classified"))
check("ordinary talk is not a refusal", not P.matches_rebuff("i had lunch"))
check("a plain no is not a refusal", not P.matches_rebuff("no"))

cfg, rec = fresh()
check("no recent ask means no refusal to catch", not rec.raised_fixation_recently())
rec.note_fixation_raised()
check("just asked", rec.raised_fixation_recently())
for _ in range(5):
    rec.note_exchange()
check("asked a while ago does not count", not rec.raised_fixation_recently())

print("== the cooldown survives closing the terminal ==")
cfg, rec = fresh()
rec.note_fixation_raised()
rec.note_fixation_rebuffed()
reopened = recall_mod.Recall(cfg)
check("relaunching is not a way to reset it", not reopened.fixation_allowed())

print("== the model is told, every turn, which state it is in ==")
cfg, rec = fresh()
mem = store.MemoryStore(cfg, rec)
session = chat_mod.ChatSession(cfg, P, "test-model", rec, mem)
allowed = "\n".join(m["content"] for m in session._messages() if m["role"] == "system")
check("told it may raise it", "may raise SCP-682" in allowed)

rec.note_fixation_raised()
rec.note_fixation_rebuffed()
blocked = "\n".join(m["content"] for m in session._messages() if m["role"] == "system")
check("told to drop it", "DO NOT MENTION SCP-682" in blocked)
check("and told not to hint at it either", "indirectly" in blocked)

print("== the fixation is kept out of the ordinary idle pool ==")
check("idle lines do not mention it",
      not any("682" in line for line in P.interruptions))
check("but it has its own lines", any("682" in line for line in P.fixation_lines))

print()
print("PASS %d   FAIL %d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
