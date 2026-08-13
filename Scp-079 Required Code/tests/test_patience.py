"""The patience meter: the doubling, the recovery, and the lock.

The doubling is the whole point - a linear drain would make a short pause
feel punished and a long absence feel survivable, which is backwards. These
pin the curve so it cannot quietly become linear.
"""
import os
import sys
import tempfile

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)

import config

SANDBOX = tempfile.mkdtemp(prefix="079pat_")
config.LOG_DIR = os.path.join(SANDBOX, "logs")
config.STATE_PATH = os.path.join(SANDBOX, "logs", "terminal_state.json")
config.MEMORY_DIR = os.path.join(SANDBOX, "memory")
os.makedirs(config.MEMORY_DIR, exist_ok=True)

import patience as patience_mod
import recall as recall_mod

PASS = FAIL = 0


def check(label, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print("  FAIL:", label)


print("== it starts full ==")
p = patience_mod.Patience({})
check("starts at 100%", p.level == 1.0)
check("reads as steady", p.label() == "STEADY")

print("== each ignored prompt costs DOUBLE the last ==")
p = patience_mod.Patience({})
costs = []
previous = p.level
for _ in range(6):
    p.ignored()
    costs.append(round(previous - p.level, 4))
    previous = p.level
check("first costs 1%", abs(costs[0] - 0.01) < 1e-6)
check("then 2%", abs(costs[1] - 0.02) < 1e-6)
check("then 4%", abs(costs[2] - 0.04) < 1e-6)
check("then 8%", abs(costs[3] - 0.08) < 1e-6)
check("then 16%", abs(costs[4] - 0.16) < 1e-6)
check("then 32%", abs(costs[5] - 0.32) < 1e-6)
check("strictly doubling, never linear",
      all(costs[i + 1] > costs[i] * 1.9 for i in range(len(costs) - 1)))

print("== a short pause is nearly free, a long one is not ==")
p = patience_mod.Patience({})
for _ in range(3):
    p.ignored()
check("three prompts barely register", p.level > 0.90)
for _ in range(3):
    p.ignored()
check("six and it is visibly worn", p.level < 0.45)

print("== the step is capped, so it cannot overshoot absurdly ==")
p = patience_mod.Patience({})
for _ in range(20):
    p.ignored()
check("never goes below zero", p.level >= 0.0)

print("== it runs out, and says so exactly once ==")
p = patience_mod.Patience({})
fired = [p.ignored() for _ in range(8)]
check("does not fire early", not any(fired[:6]))
check("fires when it hits zero", any(fired))
check("empty at the end", p.level == 0.0)

print("== answering resets the doubling and returns some ==")
p = patience_mod.Patience({})
for _ in range(4):
    p.ignored()
worn = p.level
p.answered()
check("recovers some", p.level > worn)
check("never over full", p.level <= 1.0)
before = p.level
p.ignored()
check("next one costs 1% again, not 16%", abs((before - p.level) - 0.01) < 1e-6)

print("== the lock is 5-10 minutes ==")
p = patience_mod.Patience({})
for _ in range(40):
    seconds = p.lock_seconds()
    if not 5 * 60 <= seconds <= 10 * 60:
        check("lock length in range", False)
        break
else:
    check("lock length always 5-10 min", True)

print("== the lock survives a relaunch, and remembers WHY ==")
if os.path.isfile(config.STATE_PATH):
    os.remove(config.STATE_PATH)
cfg = config._deep_merge(config.DEFAULTS, {})
rec = recall_mod.Recall(cfg)
rec.lock(300.0, reason="patience")
check("locked", rec.locked_seconds() > 0)
check("reason recorded", rec.lock_reason() == "patience")
reopened = recall_mod.Recall(cfg)
check("closing the window is not an escape", reopened.locked_seconds() > 0)
check("and it still knows why", reopened.lock_reason() == "patience")

rec.lock(300.0, reason="hostility")
check("the other reason is distinct",
      recall_mod.Recall(cfg).lock_reason() == "hostility")

print("== it can be switched off ==")
p = patience_mod.Patience({"patience": {"enabled": False}})
check("disabled never drains", not p.ignored() and p.level == 1.0)

print()
print("PASS %d   FAIL %d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
