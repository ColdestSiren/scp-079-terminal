"""Settings profiles: saving, loading, and the rules loading must not break."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import profiles
import settings as settings_mod
import store

PASS = FAIL = 0


def check(label, ok):
    global PASS, FAIL
    if ok:
        PASS += 1
    else:
        FAIL += 1
        print("  FAIL: %s" % label)


def fresh_cfg():
    cfg = config.load()
    cfg["ollama"] = dict(cfg["ollama"])
    cfg["memory"] = dict(cfg["memory"])
    return cfg


def clean_memory(mem):
    for entry in mem.listing():
        try:
            os.remove(os.path.join(config.MEMORY_DIR, entry["name"]))
        except Exception:
            pass


print("== capture and apply ==")
cfg = fresh_cfg()
cfg["ollama"]["keep_alive"] = "30m"
cfg["ollama"]["num_ctx"] = 8192
snapshot = profiles.capture(cfg)
check("captures keep_alive", snapshot.get("ollama.keep_alive") == "30m")
check("captures context", snapshot.get("ollama.num_ctx") == 8192)

cfg["ollama"]["keep_alive"] = "5m"
profiles.apply(cfg, snapshot)
check("apply restores the saved value", cfg["ollama"]["keep_alive"] == "30m")

print("== a profile cannot inject arbitrary settings ==")
cfg = fresh_cfg()
before = cfg.get("window", {}).get("width")
profiles.apply(cfg, {"window.width": 12345, "ollama.keep_alive": "30m"})
check("unknown key ignored", cfg.get("window", {}).get("width") == before)
check("known key still applied", cfg["ollama"]["keep_alive"] == "30m")

print("== built-in presets are sane ==")
for name, snap in profiles.BUILT_IN.items():
    check("%s is applicable" % name, bool(profiles.apply(fresh_cfg(), snap)))
check("large model keeps the model resident",
      profiles.BUILT_IN["LARGE MODEL"]["ollama.keep_alive"] == "30m")
check("cpu preset really is cpu", profiles.BUILT_IN["CPU ONLY"]["ollama.num_gpu"] == 0)

print("== loading must not smuggle a capacity change past the format rule ==")
cfg = fresh_cfg()
mem = store.MemoryStore(cfg, None)
clean_memory(mem)
mem.set_quota(65536)

screen = settings_mod.SettingsScreen(cfg, mem, {"dim": 0, "text": 0, "warn": 0,
                                                "alarm": 0, "bright": 0, "system": 0})
profiles.save("TESTPROF", cfg)
saved = profiles.user_profiles()["TESTPROF"]
saved["memory.quota_bytes"] = 1536          # far below what we are about to store

import json
with open(profiles.STORE, "w", encoding="utf-8") as fh:
    json.dump({"TESTPROF": saved}, fh)

# with a file present, the capacity must NOT move
mem.write("keepme.txt", "x" * 2000)
names = sorted(profiles.load_all().keys())
screen.profile_index = names.index("TESTPROF")
screen.cursor = [r[0] for r in screen.rows].index("LOAD PROFILE")
screen.activate()
check("capacity held back while files exist", mem.quota == 65536)
check("told the user why", "FORMAT FIRST" in (screen.message or ("", ""))[0])
check("stored file survived untouched",
      any(e["name"] == "keepme.txt" for e in mem.listing()))

# once empty, the same load is allowed through
clean_memory(mem)
screen.activate()
check("capacity applies once memory is empty", mem.quota == 1536)

print("== save / delete round trip ==")
cfg = fresh_cfg()
cfg["ollama"]["keep_alive"] = "-1"
check("save reports success", profiles.save("SLOT 9", cfg))
check("appears in listing", "SLOT 9" in profiles.load_all())
check("round trips", profiles.load_all()["SLOT 9"]["ollama.keep_alive"] == "-1")
check("delete works", profiles.delete("SLOT 9"))
check("gone after delete", "SLOT 9" not in profiles.user_profiles())
check("built-ins survive deletion attempts", not profiles.delete("LARGE MODEL"))
check("built-in still listed", "LARGE MODEL" in profiles.load_all())

check("blank name refused", not profiles.save("   ", cfg))
check("describe is readable", "KEEP" in profiles.describe(profiles.BUILT_IN["LARGE MODEL"]))

# leave no test residue behind
profiles.delete("TESTPROF")
clean_memory(mem)
mem.set_quota(65536)

print("\nPASS %d   FAIL %d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
