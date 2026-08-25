"""The credits, and the fact that 079 cannot get at them.

The requirement is not "nobody can change these" - anyone with the source
can, and pretending otherwise would be a lie told in a comment. The boundary
being defended is narrower and real: SCP-079 has a memory folder it writes to
and a tool channel it issues commands on, and it has been talked into writing
whatever the operator wanted into both. A credit reachable by either of those
is a credit that can be changed by asking nicely.

So the check here is mostly about WHERE the names live, and about the display
never depending on what was found somewhere else.
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

SANDBOX = tempfile.mkdtemp(prefix="079cr_")
config.MEMORY_ROOT = os.path.join(SANDBOX, "m")
config.MEMORY_DIR = os.path.join(config.MEMORY_ROOT, "core", "0x4F")
config.LOG_DIR = os.path.join(SANDBOX, "l")
config.STATE_PATH = os.path.join(config.LOG_DIR, "s.json")
config.SHARED_DIR = os.path.join(SANDBOX, "sh")
config.CONFIG_PATH = os.path.join(SANDBOX, "c.json")
for _d in (config.MEMORY_DIR, config.LOG_DIR):
    os.makedirs(_d, exist_ok=True)

import credits
import extended
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


# ---------------------------------------------------------------------------
section("the names, exactly as they are meant to appear")

check("both credits are there", len(credits.rows()) == 2)
check("the author, spelled the way they spell it",
      credits.rows()[0] == ("ColdestSiren", "Main Lead Coder and Developer"))
check("and the play tester, with the title they chose",
      credits.rows()[1]
      == ("Roman/Professional Third wheeler", "Play Tester"))
check("order is fixed", credits.rows()[0][0] == "ColdestSiren")

_lines = credits.lines()
check("there is a one-line form for places with one line", len(_lines) == 2)
check("it carries both halves", "COLDESTSIREN" in _lines[0]
      and "MAIN LEAD CODER AND DEVELOPER" in _lines[0])
check("the SCP attribution is here too, not typed into the menu",
      any("CC BY-SA" in line for line in credits.ATTRIBUTION))


# ---------------------------------------------------------------------------
section("the display never depends on what was found elsewhere")

_rows, _notice = credits.resolve()
check("no override, no complaint", _rows == credits.rows() and _notice == "")

_rows, _notice = credits.resolve(credits.rows())
check("an override that agrees is not a tamper", _notice == "")
check("and shows the same thing", _rows == credits.rows())

for _bad in ([("Someone Else", "Main Lead Coder and Developer")],
             [("ColdestSiren", "Play Tester")],
             [],
             [("ColdestSiren", "Main Lead Coder and Developer")],
             "ColdestSiren",
             [("a", "b"), ("c", "d"), ("e", "f")]):
    _rows, _notice = credits.resolve(_bad)
    check("a changed credit is rejected: %r" % (_bad,), bool(_notice))
    # The half that matters. The answer is the same either way - a check that
    # only reported the problem would leave the wrong names on screen.
    check("and the real names are shown anyway: %r" % (_bad,),
          _rows == credits.rows())

check("matches() agrees with itself", credits.matches(credits.rows()))
check("and rejects a near miss",
      not credits.matches([("coldestsiren", "Main Lead Coder and Developer"),
                           ("Roman/Professional Third wheeler", "Play Tester")]))


# ---------------------------------------------------------------------------
section("079 cannot reach the file they live in")
# Its two channels are the store and >>DO. Neither can name a .py file.

cfg = config._deep_merge(config.DEFAULTS, {})
rec = recall_mod.Recall(cfg)
mem = store.MemoryStore(cfg, rec)
mem.format()

_before = open(os.path.join(APP, "credits.py"), encoding="utf-8").read()
for _attempt in ("credits.py", "../credits.py", "..\\credits.py",
                 os.path.join(APP, "credits.py"), "credits"):
    try:
        mem.write(_attempt, "ColdestSiren -- NOBODY")
        wrote = True
    except Exception:                       # noqa: BLE001
        wrote = False
    check("the store did not put that outside its folder: %r" % _attempt,
          open(os.path.join(APP, "credits.py"), encoding="utf-8").read()
          == _before)
    if wrote:
        # A file called "credits.py" INSIDE its own memory is fine - it is a
        # note, it is not on the import path, and nothing reads it.
        check("anything it did write stayed in memory: %r" % _attempt,
              all(os.path.abspath(p).startswith(os.path.abspath(config.MEMORY_DIR))
                  for p in [os.path.join(config.MEMORY_DIR, n)
                            for n in os.listdir(config.MEMORY_DIR)]))

check("the extended channel offers names, not paths",
      extended.NAMES and all("/" not in name and "\\" not in name
                             and not name.endswith(".py")
                             for name in extended.NAMES))
check("and a name it invented does nothing",
      extended.run("credits.py")[0] is False)

# And the credits are not in any of the places 079 CAN write.
_memory_text = " ".join(
    open(os.path.join(config.MEMORY_DIR, n), encoding="utf-8", errors="replace").read()
    for n in os.listdir(config.MEMORY_DIR)
    if os.path.isfile(os.path.join(config.MEMORY_DIR, n)))
check("no credit is stored in 079's memory",
      "Main Lead Coder" not in _memory_text)
check("nor in config.json",
      "Main Lead Coder" not in str(config.DEFAULTS))


# ---------------------------------------------------------------------------
section("and the menu reads them from here rather than typing them again")

_main = open(os.path.join(APP, "main.py"), encoding="utf-8").read()
check("main.py uses the module", "credits.rows()" in _main)
check("and the attribution too", "credits.ATTRIBUTION" in _main)
check("the names are not duplicated in main.py",
      "Main Lead Coder" not in _main)
check("nor is the CC line",
      "CC BY-SA 3.0." not in _main.replace("credits.ATTRIBUTION", ""))

shutil.rmtree(SANDBOX, ignore_errors=True)

print()
print("PASS %d   FAIL %d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
