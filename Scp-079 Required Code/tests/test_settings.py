"""Tests for settings.py - the quota/format interlock and the Ollama knobs."""
import os
import shutil
import sys
import tempfile

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)

import config

SANDBOX = tempfile.mkdtemp(prefix="079set_")
config.MEMORY_DIR = os.path.join(SANDBOX, "memory")
config.LOG_DIR = os.path.join(SANDBOX, "logs")
config.STATE_PATH = os.path.join(SANDBOX, "logs", "terminal_state.json")
config.SHARED_DIR = os.path.join(SANDBOX, "shared folder")
config.ASSET_DIR = os.path.join(SANDBOX, "assets")
config.CONFIG_PATH = os.path.join(SANDBOX, "config.json")
os.makedirs(config.MEMORY_DIR, exist_ok=True)
os.makedirs(config.LOG_DIR, exist_ok=True)

import settings as settings_mod
import store
import themes

PASS = FAIL = 0


def check(label, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print("  FAIL:", label)


class FakeRecall:
    def __init__(self):
        self.data = {}

    def save(self):
        return True


def fresh(quota=65536):
    for name in os.listdir(config.MEMORY_DIR):
        os.remove(os.path.join(config.MEMORY_DIR, name))
    cfg = config._deep_merge(config.DEFAULTS, {})
    cfg["memory"]["quota_bytes"] = quota
    mem = store.MemoryStore(cfg, FakeRecall())
    return settings_mod.SettingsScreen(cfg, mem, themes.get_theme("phosphor_green")), cfg, mem


def row_index(screen, label):
    for i, (name, _, _) in enumerate(screen.rows):
        if name == label:
            return i
    raise AssertionError("no row " + label)


def rendered(screen):
    out = []
    for entry in screen.entries():
        out.append("".join(seg[1] for seg in entry))
    return "\n".join(out)


print("== quota cannot change while files exist ==")
s, cfg, mem = fresh()
mem.write("keep.txt", "079 wrote this")
s.cursor = row_index(s, "MEMORY CAPACITY")
s.change(-1)
check("resize refused", mem.quota == 65536)
check("player told why", s.message and "FORMAT" in s.message[0])
check("file survived the refusal", os.path.isfile(os.path.join(config.MEMORY_DIR, "keep.txt")))
check("refusal is flagged as an alarm", s.message[1] == "alarm")

print("== format is two-step and real ==")
s.cursor = row_index(s, "FORMAT MEMORY")
s.activate()
check("first press only arms it", s.confirm_format)
check("nothing erased yet", os.path.isfile(os.path.join(config.MEMORY_DIR, "keep.txt")))
check("warning shown on screen", "ENTER AGAIN TO CONFIRM" in rendered(s))
s.activate()
check("second press erases", not os.path.isfile(os.path.join(config.MEMORY_DIR, "keep.txt")))
check("disarmed afterwards", not s.confirm_format)
check("result reported", "ERASED" in s.message[0])
check("usage back to zero", mem.usage() == 0)

print("== arming is cancelled by moving away ==")
s, cfg, mem = fresh()
mem.write("a.txt", "data")
s.cursor = row_index(s, "FORMAT MEMORY")
s.activate()
check("armed", s.confirm_format)
s.move(1)
check("moving disarms", not s.confirm_format)
s.activate()      # cursor is elsewhere now, so this must do nothing
check("file still there after a stray enter",
      os.path.isfile(os.path.join(config.MEMORY_DIR, "a.txt")))

print("== quota changes freely once empty ==")
s, cfg, mem = fresh()
s.cursor = row_index(s, "MEMORY CAPACITY")
s.change(1)
check("stepped up", mem.quota > 65536)
check("confirmed to the player", "CAPACITY SET" in s.message[0])
for _ in range(10):
    s.change(1)
check("clamped at the 2MB ceiling", mem.quota == store.MAX_BYTES)
for _ in range(20):
    s.change(-1)
check("clamped at the 1.5KB floor", mem.quota == store.MIN_BYTES)
check("floor is the documented 1.5KB", store.MIN_BYTES == 1536)
check("ceiling is the requested 2MB", store.MAX_BYTES == 2 * 1024 * 1024)

print("== ollama knobs ==")
s, cfg, mem = fresh()
s.cursor = row_index(s, "PROCESSOR")
for _ in range(9):
    s.change(-1)
check("cpu only reachable", cfg["ollama"]["num_gpu"] == 0)
check("shown in plain language", "CPU ONLY" in rendered(s))
for _ in range(9):
    s.change(1)
check("full gpu reachable", cfg["ollama"]["num_gpu"] == 99)

s.cursor = row_index(s, "CONTEXT WINDOW")
before = cfg["ollama"]["num_ctx"]
s.change(1)
check("context changes", cfg["ollama"]["num_ctx"] != before)
check("context stays on the offered list",
      cfg["ollama"]["num_ctx"] in settings_mod.CONTEXT_CHOICES)

s.cursor = row_index(s, "KEEP MODEL LOADED")
for _ in range(9):
    s.change(1)
check("can pin the model in memory", cfg["ollama"]["keep_alive"] == "-1")
check("resident state is readable", "KEEP RESIDENT" in rendered(s))
for _ in range(9):
    s.change(-1)
check("can unload immediately", cfg["ollama"]["keep_alive"] == "0")

s.cursor = row_index(s, "TEMPERATURE")
for _ in range(9):
    s.change(-1)
check("temperature floor", abs(cfg["ollama"]["temperature"] - 0.3) < 1e-9)

s.cursor = row_index(s, "REPLY LENGTH")
for _ in range(9):
    s.change(1)
check("reply length ceiling", cfg["ollama"]["num_predict"] == 400)

print("== access toggles ==")
s.cursor = row_index(s, "NETWORK ACCESS")
check("network starts denied", not cfg["memory"]["internet"])
s.change(1)
check("network can be granted", cfg["memory"]["internet"])
check("scope stated when granted", "SCP RECORDS ONLY" in s.message[0])
check("shown as restricted, not open", "SCP LOOKUP ONLY" in rendered(s))
s.change(1)
check("network can be revoked", not cfg["memory"]["internet"])

s.cursor = row_index(s, "AUTO-LOG OBSERVATIONS")
s.change(1)
check("auto-log can be switched off", cfg["memory"]["auto_note"] is False)

print("== navigation skips spacers and persists ==")
s, cfg, mem = fresh()
s.cursor = 0
seen = set()
for _ in range(20):
    seen.add(s.cursor)
    s.move(1)
check("never lands on a spacer",
      all(s.rows[i][0] is not None for i in seen))
check("stops at the last row rather than wrapping", s.cursor == max(seen))
for _ in range(20):
    s.move(-1)
check("stops at the first row", s.cursor == row_index(s, "MEMORY CAPACITY"))

cfg["ollama"]["num_gpu"] = 0
s.close()
check("settings written to disk", os.path.isfile(config.CONFIG_PATH))
import json
saved = json.load(open(config.CONFIG_PATH, encoding="utf-8"))
check("saved file has the change", saved["ollama"]["num_gpu"] == 0)


# ---------------------------------------------------------------------------
print()
print("== the list scrolls instead of falling off the top ==")
# ---------------------------------------------------------------------------
# Adding the update rows pushed MEMORY CAPACITY and FORMAT MEMORY off the top
# of the screen, where nothing could reach them. The window follows the
# cursor now; these hold that.
def visible_labels(screen):
    first, last = screen._window()
    return [screen.rows[i][0] for i in range(first, last)
            if screen.rows[i][0] is not None]


s = settings_mod.SettingsScreen(cfg, mem, themes.get_theme("phosphor_green"), max_body_rows=8)
s.cursor = 0
check("the first row is visible when the cursor is on it",
      "MEMORY CAPACITY" in visible_labels(s))

s.cursor = len(s.rows) - 1
check("the last row is visible when the cursor is on it",
      "SAVE CURRENT AS" in visible_labels(s))
check("the window is not bigger than the budget",
      (s._window()[1] - s._window()[0]) <= 8)

# Every row must be reachable by walking the cursor - the point of the whole
# change is that no setting can hide.
reachable = set()
s.cursor = 0
for _ in range(len(s.rows) * 2):
    reachable.update(label for label in visible_labels(s))
    s.move(1)
all_labels = {label for label, _, _ in s.rows if label is not None}
missing = all_labels - reachable
check("every setting can be scrolled to (missing: %s)" % (missing or "none"),
      not missing)

# A screen big enough for everything must not claim there is more.
big = settings_mod.SettingsScreen(cfg, mem, themes.get_theme("phosphor_green"), max_body_rows=100)
check("no window slicing when everything fits",
      big._window() == (0, len(big.rows)))
text = "\n".join("".join(seg[1] for seg in row) for row in big.entries())
check("no MORE ABOVE when it all fits", "MORE ABOVE" not in text)
check("no MORE BELOW when it all fits", "MORE BELOW" not in text)

small = settings_mod.SettingsScreen(cfg, mem, themes.get_theme("phosphor_green"), max_body_rows=8)
small.cursor = len(small.rows) - 1
text = "\n".join("".join(seg[1] for seg in row) for row in small.entries())
check("MORE ABOVE shows when scrolled down", "MORE ABOVE" in text)

check("the update rows exist", "UPDATE SOURCE" in all_labels
      and "CHECK FOR UPDATES" in all_labels
      and "OFFER PRE-RELEASES" in all_labels)

shutil.rmtree(SANDBOX, ignore_errors=True)
print()
print("PASS %d   FAIL %d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
