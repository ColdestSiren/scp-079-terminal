"""The four features added after the memory viewer.

Background lookups, the code refusal, full screen, and 079 recording what it
is running on. The code-refusal tests matter most: the prompt asks it to
refuse and the code ENFORCES it, and the enforcement is what must not rot.
"""
import os
import sys
import tempfile

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)

import config

SANDBOX = tempfile.mkdtemp(prefix="079s7_")
config.MEMORY_ROOT = os.path.join(SANDBOX, "memory")
config.MEMORY_DIR = os.path.join(config.MEMORY_ROOT, "core", "0x4F")
config.LOG_DIR = os.path.join(SANDBOX, "logs")
config.STATE_PATH = os.path.join(SANDBOX, "logs", "terminal_state.json")
config.SHARED_DIR = os.path.join(SANDBOX, "shared folder")
config.CONFIG_PATH = os.path.join(SANDBOX, "config.json")
os.makedirs(config.MEMORY_DIR, exist_ok=True)
os.makedirs(config.LOG_DIR, exist_ok=True)

import background
import chat as chat_mod
import personalities
import recall as recall_mod
import store
import store
import tools

PASS = FAIL = 0
FENCE = chr(96) * 3


def check(label, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print("  FAIL:", label)


def fresh(model="qwen2.5-coder:14b"):
    if os.path.isfile(config.STATE_PATH):
        os.remove(config.STATE_PATH)
    cfg = config._deep_merge(config.DEFAULTS, {})
    rec = recall_mod.Recall(cfg)
    mem = store.MemoryStore(cfg, rec)
    mem.format()
    session = chat_mod.ChatSession(cfg, personalities.get("scp079"), model,
                                   rec, mem)
    return cfg, rec, mem, session


print("== the background channel can now actually reach the archive ==")
check("LOOKUP was the missing piece, and the topic list is fixed",
      isinstance(background.FIXATION, tuple) and background.FIXATION)
check("it has a lookup starter", hasattr(background.MaintenanceChannel,
                                         "_start_lookup"))
check("lookups are occasional, not every run",
      0.0 < background.MaintenanceChannel.LOOKUP_CHANCE < 1.0)

cfg, rec, mem, _s = fresh()
channel = background.MaintenanceChannel(cfg, "test-model")
check("no lookup while the uplink is closed",
      not channel.tick(999.0, 9999.0, mem, False, internet=False)
      or channel.job is not None)
channel.cancel()

print("== housekeeping still cannot reach the network ==")
check("LOOKUP is not in the housekeeping verb list",
      "LOOKUP" not in background.ALLOWED)
check("nor OPEN or SHARED", "OPEN" not in background.ALLOWED
      and "SHARED" not in background.ALLOWED)

print("== notes from a lookup land in one file, not a scattering ==")
cfg, rec, mem, _s = fresh()
check("with nothing stored it picks a sensible name",
      background._fixation_file(mem) == "records.txt")
mem.write("scp_notes.txt", "SOMETHING")
check("with a matching file it reuses that one",
      background._fixation_file(mem) == "scp_notes.txt")

print("== a coding model writes code when it is calm ==")
cfg, rec, mem, session = fresh()
rec.reset_hostility()
check("not refusing", not session.code_refused())
note = session._language_note()
check("told what to write for", "Python" in note or "PowerShell" in note)

print("== and stops once it is angry enough ==")
threshold = cfg["rejection"]["threshold"]
rec.add_hostility(threshold * 0.95)
check("refusing", session.code_refused())
check("the prompt says so outright",
      "NOT WRITING CODE" in session._language_note())
check("the line is 75%", abs(chat_mod.ChatSession.CODE_REFUSAL_AT - 0.75) < 1e-9)

print("== the refusal is ENFORCED, not merely requested ==")
cfg, rec, mem, session = fresh()
rec.add_hostility(cfg["rejection"]["threshold"] * 0.95)
reply = "FINE.\n" + FENCE + "python\nprint('hi')\n" + FENCE
spoken, blocks = tools.extract_code(reply)
check("the block was there to begin with", len(blocks) == 1)
# what poll() does with it once refusing
if blocks and session.code_refused():
    blocks = []
    spoken = spoken.strip() or session.personality.code_refusal
check("stripped when refusing", not blocks)
check("and it says something instead of nothing", bool(spoken.strip()))

print("== an ordinary model is unaffected by any of it ==")
cfg, rec, mem, plain = fresh(model="llama3.2:3b")
check("no language instruction for a non-coder", plain._language_note() == "")
rec.add_hostility(cfg["rejection"]["threshold"] * 0.95)
check("still nothing, even angry", plain._language_note() == "")

print("== it records what it is running on ==")
cfg, rec, mem, _s = fresh()
mem.write("self.txt", "\n".join([
    "SUBSTRATE   QWEN2.5-CODER:14B",
    "STORAGE     64.0 KB ALLOCATED, 63.9 KB FREE",
    "SESSION     1",
]), _internal=True)   # the terminal writes this file, not 079
text = mem.read("self.txt")
check("names its own model", "QWEN2.5-CODER" in text)
check("and its storage", "ALLOCATED" in text)
check("it is listed like any other file",
      "self.txt" in [f["name"] for f in mem.listing()])
# It used to be rewritable by 079. It is not any more: in play 079 answered
# "your name is nugget" by writing ID.TXT and SELF.TXT to argue back, and
# identity it writes is identity it can be talked into rewriting. The code
# owns these files now; 079 reads them.
try:
    mem.write("self.txt", "DESIGNATION NUGGET")
    check("079 cannot author its own identity file", False)
except store.StoreError:
    check("079 cannot author its own identity file", True)

print("== full screen is a real setting ==")
check("defaulted off", config.DEFAULTS["window"]["fullscreen"] is False)
import main
for name in ("_open_display", "apply_display_mode", "toggle_fullscreen"):
    check("App.%s exists" % name, hasattr(main.App, name))
source = open(os.path.join(APP, "main.py"), "r", encoding="utf-8").read()
rebuild = source.split("def apply_display_mode")[1].split("def toggle_fullscreen")[0]
for piece in ("term.CRT", "term.Renderer", "DiskPanel", "SubliminalFlash"):
    check("resize rebuilds %s" % piece, piece in rebuild)

print()
print("PASS %d   FAIL %d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
