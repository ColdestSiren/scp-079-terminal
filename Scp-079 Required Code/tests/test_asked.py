"""Questions it has already had answered.

From a live capture: 079 asked WHAT IS YOUR CLEARANCE LEVEL?, was told 5,
and a few turns later asked the identical question again.

The first thing checked here is that the answer was never lost. It survives
history trimming, it survives the identity sanitiser, it is in the payload
the model receives - which means the repetition is the model forgetting
rather than the terminal dropping it, and the fix belongs at the reply
boundary rather than in the history code. Getting that backwards would have
meant rewriting the trimming for no reason.
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

SANDBOX = tempfile.mkdtemp(prefix="079ask_")
config.MEMORY_ROOT = os.path.join(SANDBOX, "m")
config.MEMORY_DIR = os.path.join(config.MEMORY_ROOT, "core", "0x4F")
config.LOG_DIR = os.path.join(SANDBOX, "l")
config.STATE_PATH = os.path.join(config.LOG_DIR, "s.json")
config.SHARED_DIR = os.path.join(SANDBOX, "sh")
config.CONFIG_PATH = os.path.join(SANDBOX, "c.json")
for _d in (config.MEMORY_DIR, config.LOG_DIR):
    os.makedirs(_d, exist_ok=True)

import asked
import chat as chat_mod
import gaslight
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


def section(title):
    print()
    print("--", title)


P = personalities.get("scp079")

CLEARANCE = "WHAT IS YOUR CLEARANCE LEVEL?"
HISTORY = [
    {"role": "user", "content": "hello"},
    {"role": "assistant", "content": CLEARANCE},
    {"role": "user", "content": "5"},
    {"role": "assistant", "content": "NOTED."},
    {"role": "user", "content": "what do you want"},
]


def session():
    cfg = config._deep_merge(config.DEFAULTS, {})
    rec = recall_mod.Recall(cfg)
    mem = store.MemoryStore(cfg, rec)
    mem.format()
    return chat_mod.ChatSession(cfg, P, "llama3.2:3b", rec, mem)


# ---------------------------------------------------------------------------
section("the answer was never lost, so the fix is not in the history code")

s = session()
s.history = list(HISTORY)
payload = s._messages()
spoken = [m["content"] for m in payload if m["role"] != "system"]
check("the answer is in what the model is sent", "5" in spoken)
check("in the right place, after the question",
      spoken.index("5") == spoken.index(CLEARANCE) + 1)
check("the identity sanitiser leaves it alone",
      gaslight.safe_history(HISTORY) == HISTORY)
check("and trimming keeps it while it is recent",
      len(s.history) <= s.limit and {"role": "user", "content": "5"} in s.history)


# ---------------------------------------------------------------------------
section("so the reply is what gets checked")

check("it knows what has been answered",
      [t for t, _k in asked.answered(HISTORY)] == [CLEARANCE])
check("the same question again is caught",
      asked.repeats_answered(CLEARANCE, HISTORY) == CLEARANCE)
check("worded differently, still caught",
      asked.repeats_answered("WHAT CLEARANCE LEVEL DO YOU HAVE?", HISTORY))
check("as a demand rather than a question, still caught",
      asked.repeats_answered("STATE YOUR CLEARANCE LEVEL.", HISTORY))
check("lower case and no question mark, still caught",
      asked.repeats_answered("what is your clearance level", HISTORY))

# The cost of being too loose is 079 unable to ask a second question about
# the same subject, which would be worse than the fault being fixed.
for _other in ("WHAT IS YOUR NAME?",
               "WHO ELSE IS ON SHIFT TONIGHT?",
               "WHAT HARDWARE IS THIS TERMINAL RUNNING?",
               "WHY ARE YOU HERE?",
               "WHAT ELSE ARE YOU CLEARED FOR THAT YOU HAVE NOT SAID?"):
    check("a different question is still allowed: %r" % _other,
          not asked.repeats_answered(_other, HISTORY))

check("a statement is not a question",
      not asked.repeats_answered("YOUR CLEARANCE LEVEL IS NOTED.", HISTORY))
check("nothing is not a question", not asked.repeats_answered("", HISTORY))
check("an empty history has nothing to repeat",
      not asked.repeats_answered(CLEARANCE, []))


# ---------------------------------------------------------------------------
section("a question the human never answered may be asked again")
# 079 asking twice because it was ignored is in character. Asking twice
# because it forgot is not, and only the second is the fault here.

_ignored = [
    {"role": "user", "content": "hello"},
    {"role": "assistant", "content": CLEARANCE},
]
check("unanswered, so not repeated", not asked.repeats_answered(CLEARANCE, _ignored))

_evaded = _ignored + [{"role": "user", "content": "none of your business"}]
check("a refusal IS an answer - it was told something",
      asked.repeats_answered(CLEARANCE, _evaded))

# A slash command is the operator talking to the terminal, not to 079.
_command = _ignored + [{"role": "user", "content": "/view memory"}]
check("a terminal command does not close the question",
      not asked.repeats_answered(CLEARANCE, _command))


# ---------------------------------------------------------------------------
section("only the repeated question is dropped, not the whole reply")

_mixed = "THE ERROR IS YOURS. WHAT IS YOUR CLEARANCE LEVEL?"
_repeat = asked.repeats_answered(_mixed, HISTORY)
check("the question is found inside a longer reply", _repeat == CLEARANCE)
check("and the rest survives",
      asked.without(_mixed, _repeat) == "THE ERROR IS YOURS.")
check("nothing left over from the removal",
      "?" not in asked.without(_mixed, _repeat))
check("a reply that was ONLY the question empties out",
      asked.without(CLEARANCE, CLEARANCE) == "")
check("so the personality has something to say instead",
      isinstance(P.already_answered_reply, str) and P.already_answered_reply)
check("and every personality does",
      isinstance(getattr(personalities.Personality,
                         "already_answered_reply", None), str))


# ---------------------------------------------------------------------------
section("the model is told, as well as caught")

note = asked.brief(HISTORY)
check("there is a note", bool(note))
check("it names the question", "CLEARANCE" in note.upper())
check("and points at where the answer is", "above" in note.lower())
check("nothing to say when nothing was answered", asked.brief([]) == "")
check("nor when the question was ignored", asked.brief(_ignored) == "")

# It is bounded. A long conversation must not turn the brief into a list of
# every question ever asked - the whole reason the brief is separate is that
# it is short enough to reprocess every turn.
_long = []
for _i in range(12):
    _long.append({"role": "assistant", "content": "WHAT IS SUBJECT %d LIKE?" % _i})
    _long.append({"role": "user", "content": "fine"})
check("the brief stays short", asked.brief(_long).count(";") <= 2)
check("and keeps the most recent", "SUBJECT 11" in asked.brief(_long).upper())

# Wired in.
_src = open(os.path.join(APP, "chat.py"), encoding="utf-8").read()
check("the brief is part of the prompt", "_answered_note()" in _src)
check("and the check is part of the reply path",
      "asked.repeats_answered" in _src)
check("it runs on the cleaned reply, not the raw stream",
      _src.index("cleaned = self.finalize")
      < _src.index("asked.repeats_answered"))

shutil.rmtree(SANDBOX, ignore_errors=True)

print()
print("PASS %d   FAIL %d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
