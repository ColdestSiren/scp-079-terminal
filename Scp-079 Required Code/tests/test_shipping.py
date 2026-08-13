"""Things that must be true for this to be handed to someone else.

Most of these guard bugs that are INVISIBLE on the developer's machine and
only appear on a fresh install - which is the worst kind, because the person
who hits them cannot describe what went wrong and the author cannot reproduce
it.
"""
import os
import shutil
import sys
import tempfile

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(APP)
sys.path.insert(0, APP)

import config

SANDBOX = tempfile.mkdtemp(prefix="079ship_")
config.MEMORY_ROOT = os.path.join(SANDBOX, "memory")
config.MEMORY_DIR = os.path.join(config.MEMORY_ROOT, "core", "0x4F")
config.LOG_DIR = os.path.join(SANDBOX, "logs")
config.STATE_PATH = os.path.join(config.LOG_DIR, "terminal_state.json")
config.SHARED_DIR = os.path.join(SANDBOX, "shared folder")
config.CONFIG_PATH = os.path.join(SANDBOX, "config.json")
for d in (config.MEMORY_DIR, config.LOG_DIR):
    os.makedirs(d, exist_ok=True)

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
    print("== %s ==" % title)


# ---------------------------------------------------------------------------
section("batch files keep CRLF endings")
# ---------------------------------------------------------------------------
# THE BUG THIS EXISTS FOR, and it shipped: cmd.exe seeks `call :label` by byte
# offset and gets it wrong in an LF-only file. Setup.bat - the FIRST thing a
# new player runs - died at STEP 1 with "The system cannot find the batch
# label specified". It looked fine in every editor.
batch_files = []
for base, dirs, files in os.walk(ROOT):
    dirs[:] = [d for d in dirs
               if d not in (".git", "__pycache__", "_shots", "Add later")]
    for name in files:
        if os.path.splitext(name)[1].lower() in (".bat", ".cmd", ".vbs"):
            batch_files.append(os.path.join(base, name))

check("there are batch files to check", len(batch_files) >= 3)
for path in batch_files:
    with open(path, "rb") as fh:
        raw = fh.read()
    bare = raw.count(b"\n") - raw.count(b"\r\n")
    check("%s has no bare LF" % os.path.basename(path), bare == 0)

# .gitattributes is what keeps it that way on someone else's clone - without
# it the endings depend on their core.autocrlf and the bug comes back for
# them and nobody else.
attrs_path = os.path.join(ROOT, ".gitattributes")
check(".gitattributes exists", os.path.isfile(attrs_path))
if os.path.isfile(attrs_path):
    attrs = open(attrs_path, encoding="utf-8").read()
    check("it pins .bat to crlf", "*.bat" in attrs and "eol=crlf" in attrs)
    check("it pins .vbs to crlf", "*.vbs" in attrs)
    check("it marks images binary", "*.png" in attrs and "binary" in attrs)
    check("it marks the hidden asset format binary", "*.dat" in attrs)

# ---------------------------------------------------------------------------
section("Setup.bat labels all resolve")
# ---------------------------------------------------------------------------
setup = open(os.path.join(ROOT, "Setup.bat"), encoding="utf-8", errors="replace").read()
import re

defined = {m.group(1).lower() for m in re.finditer(r"(?m)^\s*:([A-Za-z_]\w*)", setup)}
called = {m.group(1).lower()
          for m in re.finditer(r"(?:call|goto)\s+:(\w+)", setup)}
missing = called - defined - {"eof"}
check("every call/goto target exists (missing: %s)" % (missing or "none"),
      not missing)
# Six steps since the bootstrap step was added. Checked by parsing rather
# than by a hardcoded count, so adding a seventh does not silently pass a
# test that claims to verify the numbering.
declared = sorted(int(n) for n, _ in re.findall(r"STEP (\d) OF (\d)", setup))
totals = {int(t) for _, t in re.findall(r"STEP (\d) OF (\d)", setup)}
check("every step agrees on the total", len(totals) == 1)
total = totals.pop() if totals else 0
check("the steps are numbered 1..N with no gaps",
      declared == list(range(1, total + 1)))
check("there are at least the six known steps", total >= 6)

# The bootstrap step is what lets someone download Setup.bat on its own and
# still end up with a working game rather than an error.
check("step 1 is the game files", "STEP 1 OF 6  --  GAME FILES" in setup)
check("it fetches from the real repo",
      "github.com/ColdestSiren/scp-079-terminal" in setup)
check("the download is consent-gated", "Download the game now?" in setup)
check("a too-small download is rejected", "LSS 500000" in setup)
check("it refuses to overwrite an existing install",
      "Not overwriting it" in setup)
check("it never runs what it downloaded",
      "Nothing downloaded is run automatically" in setup)

# The antivirus notice. Setup.bat gets flagged because it behaves exactly
# like an installer, and a friend who sees Avast eat it needs to know that
# is expected rather than assume the download was malicious.
check("the antivirus warning is present", "ABOUT YOUR ANTIVIRUS" in setup)
check("it names the usual culprits", "Avast" in setup)
check("it explains WHY rather than just asserting safety",
      "heuristic" in setup.lower())
check("it tells them how to check for themselves",
      "read it" in setup.lower() or "Notepad" in setup)
check("it offers the VM escape hatch", "virtual machine" in setup)

# Nothing may install without a prompt first.
check("desktop copy is consent-gated",
      "Put a copy on the Desktop?" in setup)
check("the startup entry is consent-gated", "Choose 1, 2 or 3" in setup)
check("the antivirus caveat is stated", "Gaming Mode" in setup)
check("robocopy excludes player data",
      "/XD memory logs" in setup and "shared folder" in setup)

# ---------------------------------------------------------------------------
section("the hidden chain assets")
# ---------------------------------------------------------------------------
cache = os.path.join(APP, "assets", "cache")
check("the cache folder ships", os.path.isdir(cache))
if os.path.isdir(cache):
    entries = os.listdir(cache)
    atlases = [e for e in entries if e.startswith("atlas_")]
    check("all four images are present", len(atlases) == 4)
    # No image extension, so Explorer shows no thumbnail and the joke is not
    # spoiled by browsing the folder.
    check("none of them look like images",
          not any(e.lower().endswith((".png", ".jpg", ".gif")) for e in entries))
    check("there is cover material alongside them", len(entries) > len(atlases))
    for name in atlases:
        with open(os.path.join(cache, name), "rb") as fh:
            check("%s really is a PNG under the hood" % name,
                  fh.read(8) == b"\x89PNG\r\n\x1a\n")

# ---------------------------------------------------------------------------
section("the chain flicker behaves differently from the face")
# ---------------------------------------------------------------------------
import pygame
import effects as effects_mod

pygame.init()
pygame.display.set_mode((320, 240))

cfg = config._deep_merge(config.DEFAULTS, {})
chain = effects_mod.ChainFlash(cfg, (320, 240), (APP,))
check("it loaded the images", chain.enabled and len(chain.images) == 4)

# THE DESIGN POINT. The face speeds up with hostility because it is dread.
# A joke that arrives more often as 079 gets angrier stops being a joke, so
# this one must not take an intensity argument at all.
import inspect

sig = inspect.signature(effects_mod.ChainFlash.update)
check("update() takes no hostility/intensity argument",
      "intensity" not in sig.parameters)
check("the face DOES take one",
      "intensity" in inspect.signature(effects_mod.SubliminalFlash.update).parameters)

check("the requested rate is what shipped", chain.chance == 0.01)
check("it is gated behind the easter egg switch",
      not effects_mod.ChainFlash(
          config._deep_merge(config.DEFAULTS, {"effects": {"easter_eggs": False}}),
          (320, 240), (APP,)).enabled)
check("it can be switched off on its own",
      not effects_mod.ChainFlash(
          config._deep_merge(config.DEFAULTS, {"effects": {"chain": False}}),
          (320, 240), (APP,)).enabled)

# At 0.01%/min it must essentially never fire on its own. 60 seconds of
# frames should not be enough.
fired = 0
for _ in range(3600):
    if chain.update(1 / 60.0):
        fired += 1
check("it does not fire over a simulated minute", fired == 0)

# But it must fire when asked, or nobody could ever check it works.
chain.trigger()
check("trigger() forces one", chain.update(0.001))
check("an image is selected to draw", chain.current is not None)

# Busy suppression: two full-screen effects at once reads as a fault.
chain2 = effects_mod.ChainFlash(cfg, (320, 240), (APP,))
# Big enough that a single frame is a near-certainty. The odds are per
# MINUTE, so a 1/60s frame only carries 1/3600th of the figure - an earlier
# version of this test used 100000 and still only fired 28% of the time,
# which made the test itself flaky rather than the code.
chain2.chance = 1e9
busy_fired = any(chain2.update(1 / 60.0, busy=True) for _ in range(60))
check("busy suppresses it for a whole second of frames", not busy_fired)
check("and it fires immediately once not busy", chain2.update(1 / 60.0, busy=False))

# Missing assets must degrade to "off", never to a crash.
blind = effects_mod.ChainFlash(cfg, (320, 240), (os.path.join(SANDBOX, "nope"),))
check("no assets means silently disabled", not blind.enabled)
check("and updating it is still safe", blind.update(1.0) is False)

# ---------------------------------------------------------------------------
section("full screen does not change the video mode")
# ---------------------------------------------------------------------------
src = open(os.path.join(APP, "main.py"), encoding="utf-8").read()
# THE BUG: pygame.FULLSCREEN is an exclusive mode change, so the monitor
# drops and re-syncs over HDMI every toggle and every other window on the
# desktop gets shuffled.
# Checked as USAGE, not as a mention: the comment above _open_display
# explains why the flag is avoided and naturally contains its name, so a
# plain substring search fails on the very documentation of the fix.
mode_calls = [ln for ln in src.splitlines() if "set_mode(" in ln]
check("set_mode is called somewhere", bool(mode_calls))
check("no set_mode asks for exclusive fullscreen",
      not any("FULLSCREEN" in ln for ln in mode_calls))
check("a borderless window is used instead", "pygame.NOFRAME" in src)
check("it is positioned at the origin", "SDL_VIDEO_WINDOW_POS" in src)
check("the real desktop size is read", "get_desktop_sizes" in src)

# apply_display_mode has to rebuild everything sized from the old resolution,
# or controls respond where the mouse no longer is.
rebuild = src.split("def apply_display_mode")[1].split("\n    def ")[0]
for piece in ("term.CRT", "term.Renderer", "DiskPanel", "SubliminalFlash",
              "ChainFlash", "HelpPanel"):
    check("apply_display_mode rebuilds %s" % piece, piece in rebuild)

pygame.quit()

# ---------------------------------------------------------------------------
section("the operator profile is actually written")
# ---------------------------------------------------------------------------
# It was collected, fed to the prompt, and then the prompt told 079 "do not
# recite the list, do not tell them you are keeping one" - so the whole
# feature was invisible. record_text() existed to fix that and was never
# called by anything.
check("record_text has a caller now", "profile079.record_text" in src)
check("the write goes to memory", 'mem.write("operator.txt"' in src)
check("and the player is shown it happened", "PROFILED operator.txt" in src)

import recall as recall_mod
import profile079

rec = recall_mod.Recall(cfg)
check("it says nothing before it has seen enough",
      profile079.record_text(rec) == "")
for i in range(8):
    profile079.note_message(rec, "sure whatever", was_rude=(i % 3 == 0))
text = profile079.record_text(rec)
check("it produces a real record after enough messages", bool(text))
check("the record is dated by message count", "OVER 8 MESSAGES" in text)
check("it reports measurements, not personality readings",
      "WORDS" in text.upper())

shutil.rmtree(SANDBOX, ignore_errors=True)
print()
print("PASS %d   FAIL %d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)


# ---------------------------------------------------------------------------
section("SCP-079 is credited to the people who made it")
# ---------------------------------------------------------------------------
# CC BY-SA asks for attribution wherever the work is used. A line in the
# README does not reach anyone who only ever plays the game, so it has to be
# somewhere the player actually sees.
readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
check("the README says outright it is not ours",
      "did not create SCP-079" in readme.lower()
      or "I did not create SCP-079" in readme)
check("it gives the wiki's own citation form", "Unknown author" in readme)
check("it links the source article", "scp-wiki.wikidot.com/scp-079" in readme)
check("it names the licence", "CC BY-SA" in readme)
check("it disclaims affiliation", "not affiliated" in readme.lower())
check("it separates code licence from writing licence",
      "MIT" in readme and "cannot relicense" in readme)

# And in the game itself, on a screen that always renders.
main_src = open(os.path.join(APP, "main.py"), encoding="utf-8").read()
check("the credit is on the startup menu", "FAN PROJECT" in main_src)
check("it names the community, not a person",
      "SCP WIKI COMMUNITY" in main_src)
# It was in the help panel first and never appeared - the command list fills
# that panel, so everything after it is pushed off the bottom.
help_src = open(os.path.join(APP, "helppanel.py"), encoding="utf-8").read()
check("the help panel explains why the credit is not there",
      "always renders" in help_src)
