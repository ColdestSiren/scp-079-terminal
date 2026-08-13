"""Save slots: separate memory, separate 079, optional code.

The isolation tests are the important ones. If slots ever start sharing
memory or hostility that is a silent failure - the game keeps working and
just quietly stops being separate conversations.
"""
import os
import sys
import tempfile

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)

import config

SANDBOX = tempfile.mkdtemp(prefix="079slot_")
config.MEMORY_ROOT = os.path.join(SANDBOX, "memory")
config.LOG_DIR = os.path.join(SANDBOX, "logs")
config.PUBLIC_MEMORY_DIR = os.path.join(config.MEMORY_ROOT, "core", "0x4F")
config.PUBLIC_STATE_PATH = os.path.join(config.LOG_DIR, "terminal_state.json")
config.MEMORY_DIR = config.PUBLIC_MEMORY_DIR
config.STATE_PATH = config.PUBLIC_STATE_PATH
config.SHARED_DIR = os.path.join(SANDBOX, "shared folder")
config.CONFIG_PATH = os.path.join(SANDBOX, "config.json")
os.makedirs(config.PUBLIC_MEMORY_DIR, exist_ok=True)
os.makedirs(config.LOG_DIR, exist_ok=True)

import recall as recall_mod
import saves
import saveslots
import slotscreen
import store

PASS = FAIL = 0
CFG = config._deep_merge(config.DEFAULTS, {})


def check(label, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print("  FAIL:", label)


def open_slot(ident):
    saveslots.activate(ident)
    rec = recall_mod.Recall(CFG)
    return rec, store.MemoryStore(CFG, rec)


print("== the public slot exists and cannot be removed or locked ==")
saveslots.activate(saveslots.PUBLIC)
check("public is listed first", saveslots.all_slots()[0]["id"] == saveslots.PUBLIC)
check("cannot be deleted", saveslots.delete(saveslots.PUBLIC) is False)
check("cannot be locked", saveslots.set_code(saveslots.PUBLIC, "1234") is False)
check("is never confidential", not saveslots.is_locked(saveslots.PUBLIC))

print("== a slot gets its own memory files ==")
pub_rec, pub_mem = open_slot(saveslots.PUBLIC)
pub_mem.format()
pub_mem.write("public_note.txt", "EVERYONE SEES THIS.")

night = saveslots.create("Night Shift")
n_rec, n_mem = open_slot(night)
n_mem.format()
n_mem.write("private_note.txt", "ONLY HERE.")

check("slot sees only its own", [f["name"] for f in n_mem.listing()]
      == ["private_note.txt"])
_r, pub_mem = open_slot(saveslots.PUBLIC)
check("public sees only its own", [f["name"] for f in pub_mem.listing()]
      == ["public_note.txt"])

print("== and its own 079 ==")
n_rec, _m = open_slot(night)
n_rec.reset_hostility()
n_rec.add_hostility(7.0)
n_rec.note_exchange()
n_rec.note_exchange()
check("slot is angry", n_rec.hostility() > 6.0)

p_rec, _m = open_slot(saveslots.PUBLIC)
check("public is not", p_rec.hostility() < 0.5)
check("and has its own exchange count", p_rec.exchanges() != n_rec.exchanges()
      or p_rec.exchanges() == 0)

reopened, _m = open_slot(night)
check("the slot remembers being angry", reopened.hostility() > 6.0)
check("and its exchanges", reopened.exchanges() >= 2)

print("== transcripts do not leak between slots ==")
saveslots.activate(saveslots.PUBLIC)
saves.save("test-model", [[((1, 2, 3), "PUBLIC TALK")]], [], 1)
saveslots.activate(night)
check("the slot has no public transcript", saves.load("test-model") is None)
saves.save("test-model", [[((1, 2, 3), "PRIVATE TALK")]], [], 1)
entry = saves.load("test-model")
check("it has its own", entry and "PRIVATE" in entry["rows"][0][0][1])
saveslots.activate(saveslots.PUBLIC)
entry = saves.load("test-model")
check("and public still has its own", entry and "PUBLIC" in entry["rows"][0][0][1])

print("== the code gates opening, and nothing else ==")
locked = saveslots.create("Locked", code="4471")
check("marked confidential", saveslots.is_locked(locked))
check("wrong code refused", not saveslots.check_code(locked, "0000"))
check("empty refused", not saveslots.check_code(locked, ""))
check("right code accepted", saveslots.check_code(locked, "4471"))
check("an unlocked slot accepts anything",
      saveslots.check_code(night, "whatever"))

print("== deleting never needs the code ==")
check("deletes while still locked", saveslots.delete(locked) is True)
check("and it is gone", not saveslots.exists(locked))

print("== deleting a slot takes its files with it ==")
doomed = saveslots.create("Doomed")
_r, d_mem = open_slot(doomed)
d_mem.write("gone.txt", "SOON")
path = os.path.join(saveslots.slot_dir(doomed), "files", "gone.txt")
check("file was written", os.path.isfile(path))
saveslots.activate(saveslots.PUBLIC)
saveslots.delete(doomed)
check("directory removed", not os.path.isdir(saveslots.slot_dir(doomed)))
check("public untouched", os.path.isfile(
    os.path.join(config.PUBLIC_MEMORY_DIR, "public_note.txt")))

print("== names collide safely rather than merging ==")
a = saveslots.create("Same Name")
b = saveslots.create("Same Name")
check("two saves, two ids", a != b and saveslots.exists(a) and saveslots.exists(b))
saveslots.delete(a)
saveslots.delete(b)

print("== the picker warns that a code is not encryption ==")
text = slotscreen.WARNING.upper()
check("says it is not encryption", "NOT ENCRYPTION" in text)
check("and says the files stay readable", "READ" in text)

print("== recall resolves its path at call time, not import time ==")
source = open(os.path.join(APP, "recall.py"), "r", encoding="utf-8").read()
check("no module-level STORE capture", "\nSTORE = config." not in source)
check("uses a resolver", "_store()" in source)

saveslots.activate(saveslots.PUBLIC)
print()
print("PASS %d   FAIL %d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
