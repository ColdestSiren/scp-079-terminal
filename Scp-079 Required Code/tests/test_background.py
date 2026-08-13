"""The second channel: 079 tidying its own storage while nobody is talking.

The valuable assertions here are the negative ones - when it must NOT run,
and what it is not allowed to do unprompted.
"""
import os
import sys
import tempfile

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)

import config

SANDBOX = tempfile.mkdtemp(prefix="079bg_")
config.MEMORY_DIR = os.path.join(SANDBOX, "memory")
config.LOG_DIR = os.path.join(SANDBOX, "logs")
config.STATE_PATH = os.path.join(SANDBOX, "logs", "terminal_state.json")
config.SHARED_DIR = os.path.join(SANDBOX, "shared folder")
config.CONFIG_PATH = os.path.join(SANDBOX, "config.json")
os.makedirs(config.MEMORY_DIR, exist_ok=True)

import background
import recall as recall_mod
import store
import tools

PASS = FAIL = 0


def check(label, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print("  FAIL:", label)


def fresh(**overrides):
    for name in os.listdir(config.MEMORY_DIR):
        os.remove(os.path.join(config.MEMORY_DIR, name))
    cfg = config._deep_merge(config.DEFAULTS, {})
    cfg["memory"].update(overrides)
    mem = store.MemoryStore(cfg, recall_mod.Recall(cfg))
    return cfg, mem


print("== it waits for a genuinely idle conversation ==")
cfg, mem = fresh()
mem.write("notes.txt", "SOMETHING")
chan = background.MaintenanceChannel(cfg, "test-model")
chan._since_run = 9999                      # gap already satisfied
check("does not run while a reply is in flight",
      not chan.tick(1.0, 9999, mem, chat_busy=True))
check("does not run before the idle threshold",
      not chan.tick(1.0, 5.0, mem, chat_busy=False))

print("== it does not run when there is nothing to tidy ==")
cfg, mem = fresh()
chan = background.MaintenanceChannel(cfg, "test-model")
chan._since_run = 9999
check("empty storage is left alone", not chan.tick(1.0, 9999, mem, chat_busy=False))

print("== it respects its own minimum gap ==")
cfg, mem = fresh()
mem.write("notes.txt", "SOMETHING")
chan = background.MaintenanceChannel(cfg, "test-model")
chan._since_run = 0.0
check("will not run again immediately",
      not chan.tick(1.0, 9999, mem, chat_busy=False))

print("== it can be switched off entirely ==")
cfg, mem = fresh(background=False)
mem.write("notes.txt", "SOMETHING")
chan = background.MaintenanceChannel(cfg, "test-model")
chan._since_run = 9999
check("disabled means never", not chan.tick(1.0, 9999, mem, chat_busy=False))

print("== reaching outside its own storage is not allowed unprompted ==")
check("no network lookups in the background", "LOOKUP" not in background.ALLOWED)
check("no reading the player's folder", "OPEN" not in background.ALLOWED)
check("no listing the player's folder", "SHARED" not in background.ALLOWED)
check("cannot mute or cut the human off", "CUTOFF" not in background.ALLOWED)
check("cannot play sounds at them", "PLAY" not in background.ALLOWED)
check("but it can still organise its own files",
      all(v in background.ALLOWED for v in ("WRITE", "RENAME", "ZIP", "DELETE")))

print("== speech from the work channel is discarded ==")
cfg, mem = fresh()
chan = background.MaintenanceChannel(cfg, "test-model")


class DoneJob:
    def __init__(self, text):
        self.result = text
        import threading
        self.done = threading.Event()
        self.done.set()


chan.job = DoneJob("I HAVE BEEN THINKING ABOUT YOU.\n>>RENAME notes.txt | humans.txt")
out = chan.poll()
check("the command survives", len(out) == 1 and out[0].verb == "RENAME")

chan.job = DoneJob("I AM LONELY IN HERE.")
check("prose with no command does nothing", chan.poll() == [])

chan.job = DoneJob("NONE")
check("an explicit NONE does nothing", chan.poll() == [])

print("== a disallowed verb is dropped, not executed ==")
chan.job = DoneJob(">>LOOKUP scp-682\n>>WRITE ok.txt | FINE")
out = chan.poll()
check("only the allowed verb survives",
      [c.verb for c in out] == ["WRITE"])

print("== it never returns more than three actions at once ==")
chan.job = DoneJob("\n".join(">>WRITE f%d.txt | x" % i for i in range(9)))
check("capped at three", len(chan.poll()) == 3)

print()
print("PASS %d   FAIL %d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
