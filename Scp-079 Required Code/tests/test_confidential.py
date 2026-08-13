"""Confidential saves: the code, the account seal, and tamper detection.

The point of these is the REFUSALS. A seal that quietly lets everyone through
still looks like it works, so every test here is about something being denied.
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

SANDBOX = tempfile.mkdtemp(prefix="079conf_")
config.MEMORY_ROOT = os.path.join(SANDBOX, "memory")
config.LOG_DIR = os.path.join(SANDBOX, "logs")
config.PUBLIC_MEMORY_DIR = os.path.join(config.MEMORY_ROOT, "core", "0x4F")
config.PUBLIC_STATE_PATH = os.path.join(config.LOG_DIR, "terminal_state.json")
config.MEMORY_DIR = config.PUBLIC_MEMORY_DIR
config.STATE_PATH = config.PUBLIC_STATE_PATH
config.CONFIG_PATH = os.path.join(SANDBOX, "config.json")
os.makedirs(config.PUBLIC_MEMORY_DIR, exist_ok=True)
os.makedirs(config.LOG_DIR, exist_ok=True)

import json
import personalities
import saveslots
import slotscreen

PASS = FAIL = 0


def check(label, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print("  FAIL:", label)


def wipe():
    shutil.rmtree(saveslots._root(), ignore_errors=True)


print("== confidential requires a code ==")
wipe()
slot = saveslots.create("Vault")
check("refused without one", saveslots.set_confidential(slot, True) is False)
check("still not confidential", not saveslots.is_confidential(slot))
saveslots.set_code(slot, "4471")
check("accepted with one", saveslots.set_confidential(slot, True) is True)
check("now confidential", saveslots.is_confidential(slot))

print("== it seals to the account that set it ==")
check("owner recorded", saveslots.owner(slot) == saveslots.current_user())
check("opens for the owner", saveslots.owner_matches(slot))

real = os.environ.get("USERNAME", "")
os.environ["USERNAME"] = "somebody_else"
check("refuses another account", not saveslots.owner_matches(slot))
os.environ["USERNAME"] = real
check("opens again for the owner", saveslots.owner_matches(slot))

print("== the code still has to be right ==")
check("wrong refused", not saveslots.check_code(slot, "0000"))
check("blank refused", not saveslots.check_code(slot, ""))
check("right accepted", saveslots.check_code(slot, "4471"))

print("== clearing the code clears the seal ==")
screen = slotscreen.SlotScreen({"dim": 0, "text": 0, "bright": 0, "warn": 0,
                                "alarm": 0, "system": 0}, saveslots.PUBLIC)
screen.cursor = next(i for i, s in enumerate(screen.slots) if s["id"] == slot)
screen.mode = slotscreen.CODING
screen.buffer = ""
screen.submit()
check("code gone", not saveslots.is_locked(slot))
check("and so is the seal", not saveslots.is_confidential(slot))

print("== deleting never needs the code or the account ==")
wipe()
locked = saveslots.create("Sealed", code="9999")
saveslots.set_confidential(locked, True)
os.environ["USERNAME"] = "somebody_else"
check("another account can still delete", saveslots.delete(locked) is True)
os.environ["USERNAME"] = real
check("it is gone", not saveslots.exists(locked))

print("== editing the record out is detected ==")
wipe()
slot = saveslots.create("Watched", code="1234")
saveslots.set_confidential(slot, True)
check("clean to begin with", not saveslots.index_tampered())

raw = json.load(open(saveslots._index_path()))
raw["slots"][slot]["code"] = ""
json.dump(raw, open(saveslots._index_path(), "w"))
check("blanking the code is caught", saveslots.index_tampered())

wipe()
slot = saveslots.create("Watched", code="1234")
saveslots.set_confidential(slot, True)
raw = json.load(open(saveslots._index_path()))
raw["slots"][slot]["owner"] = "somebody_else"
json.dump(raw, open(saveslots._index_path(), "w"))
check("changing the owner is caught", saveslots.index_tampered())

wipe()
slot = saveslots.create("Watched", code="1234")
json.dump({"slots": {slot: {"name": "x", "code": ""}}},
          open(saveslots._index_path(), "w"))
check("rewriting it unsigned is caught", saveslots.index_tampered())

print("== deleting the record is caught, but debris is not ==")
wipe()
slot = saveslots.create("Watched", code="1234")
os.makedirs(os.path.join(saveslots.slot_dir(slot), "files"), exist_ok=True)
open(os.path.join(saveslots.slot_dir(slot), "files", "n.txt"), "w").write("D")
os.remove(saveslots._index_path())
check("an orphan holding data is caught", saveslots.index_tampered())

wipe()
saveslots.create("Real One")
os.makedirs(os.path.join(saveslots._root(), "empty_leftover"), exist_ok=True)
check("an empty leftover is not an accusation",
      not saveslots.index_tampered())
check("and it is swept up",
      not os.path.isdir(os.path.join(saveslots._root(), "empty_leftover")))

print("== the boot asks at AUTHENTICATING USER ==")
P = personalities.get("scp079")
plain = P.build_boot({"boot": {}}, None, needs_code=False)
gated = P.build_boot({"boot": {}}, None, needs_code=True)


def find_auth(steps):
    for step in steps:
        if step.get("label", "").strip() == "AUTHENTICATING USER":
            return step
    return None


check("normally just a line", find_auth(plain)["kind"] != "hold")
check("a gate when a code is needed", find_auth(gated)["kind"] == "hold")
check("tagged so the app can tell which wait it is",
      find_auth(gated).get("id") == "auth")
check("fails with ERROR", find_auth(gated)["fail_status"] == "ERROR")

steps = P.build_auth_failure()
text = " ".join(s.get("text", "") for s in steps)
check("a wrong code says rejected", "REJECTED" in text)
check("and says the save survives", "INTACT" in text)
tampered = " ".join(s.get("text", "") for s in P.build_auth_failure(tampered=True))
check("a tampered record reads differently", "ALTERED" in tampered)

print("== the public record is never any of this ==")
check("cannot be locked", saveslots.set_code(saveslots.PUBLIC, "1") is False)
check("cannot be sealed",
      saveslots.set_confidential(saveslots.PUBLIC, True) is False)
check("always opens", saveslots.owner_matches(saveslots.PUBLIC))

print()
print("PASS %d   FAIL %d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
