"""Host RAM vs the model, the two link lines, and 079's reach into sounds.

The RAM tests all pass an explicit figure. That is not tidiness - an earlier
version accepted a ram_gb argument and then silently re-read the real
machine, so every case measured whatever the developer happened to be sitting
at and proved nothing.
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

SANDBOX = tempfile.mkdtemp(prefix="079host_")
config.MEMORY_ROOT = os.path.join(SANDBOX, "memory")
config.MEMORY_DIR = os.path.join(config.MEMORY_ROOT, "core", "0x4F")
config.LOG_DIR = os.path.join(SANDBOX, "logs")
config.STATE_PATH = os.path.join(config.LOG_DIR, "terminal_state.json")
config.SHARED_DIR = os.path.join(SANDBOX, "shared folder")
config.SOUND_DIR = os.path.join(SANDBOX, "sounds")
config.CONFIG_PATH = os.path.join(SANDBOX, "config.json")
for d in (config.MEMORY_DIR, config.LOG_DIR, config.SOUND_DIR):
    os.makedirs(d, exist_ok=True)

import audio as audio_mod
import ollama
import personalities
import power
import tuning

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


GB = 1024 ** 3

# ---------------------------------------------------------------------------
section("reported RAM is not the sticker figure")
# ---------------------------------------------------------------------------
# THE BUG THIS EXISTS FOR: Windows reports 31.04 GB on a 32 GB machine because
# firmware reserves a slice. A naive "do you have 32?" told the developer's
# own 32 GB box it was too small for the model it obviously runs.
check("31.04 reads as a 32 GB machine", power.installed_ram_gb(31.04) == 32)
check("15.8 reads as a 16 GB machine", power.installed_ram_gb(15.8) == 16)
check("7.85 reads as an 8 GB machine", power.installed_ram_gb(7.85) == 8)
check("63.2 reads as a 64 GB machine", power.installed_ram_gb(63.2) == 64)
check("described with units", power.describe_ram(31.04) == "32 GB")

check("31.04 SATISFIES a 32 GB requirement", power.has_ram(32, total=31.04))
check("15.8 does not satisfy 32", not power.has_ram(32, total=15.8))
check("15.8 satisfies 16", power.has_ram(16, total=15.8))

# UNKNOWN MUST NEVER BLOCK. A system call that failed is not evidence of a
# small machine, and refusing to load over it would be worse than the risk.
# Driven by making the reading itself fail - passing total=None only means
# "not supplied, go and read it", which is a different thing entirely.
_saved_ram = power.ram_gb
power.ram_gb = lambda: None
try:
    check("unreadable RAM satisfies any requirement", power.has_ram(32))
    check("unreadable RAM describes as UNKNOWN", power.describe_ram() == "UNKNOWN")
    check("unreadable RAM gives no model concern",
          tuning.ram_check("qwen3.6:latest", 23 * GB) is None)
    check("unreadable RAM warns off nothing", tuning.too_heavy_for() == [])
finally:
    power.ram_gb = _saved_ram

# ---------------------------------------------------------------------------
section("the qwen rule says what was asked for")
# ---------------------------------------------------------------------------
c = tuning.ram_check("qwen3.6:latest", 23 * GB, ram_gb=15.8)
check("qwen3 on 16 GB is a concern", c is not None)
head = tuning.ram_headline(c)
check("it states what you have", "16 GB" in head)
check("it states the minimum", "32 GB" in head)
check("it names the family", "QWEN3" in head)
# The published minimum must NOT be inflated by the download size. 23 GB x 1.4
# + 2 came out as "the minimum for qwen3 is 34 GB", which is not a figure
# anyone who read the model card would recognise.
check("the listed minimum is not raised by file size",
      tuning.required_ram_gb("qwen3.6:latest", 23 * GB) == 32)

check("qwen3 on 32 GB is fine",
      tuning.ram_check("qwen3.6:latest", 23 * GB, ram_gb=31.04) is None)
check("qwen3 on 64 GB is fine",
      tuning.ram_check("qwen3.6:latest", 23 * GB, ram_gb=63.2) is None)
check("a small model on 8 GB is fine",
      tuning.ram_check("llama3.2:3b", 2 * GB, ram_gb=7.85) is None)

# qwen2.5 must not be read as qwen3 by an unlucky substring match.
check("qwen2.5 resolves to its own family",
      tuning.family_of("qwen2.5-coder:14b") == "qwen2.5")
check("qwen3 resolves to qwen3", tuning.family_of("qwen3.6:latest") == "qwen3")
check("qwen2.5 has a lower bar than qwen3",
      tuning.ram_check("qwen2.5-coder:14b", 9 * GB, ram_gb=15.8) is None)

# Unlisted models fall back to size.
big = tuning.ram_check("somethingelse:70b", 40 * GB, ram_gb=15.8)
check("an unlisted huge model is still caught", big is not None)
check("it is not described as a listed family", big and not big["listed"])
check("no size and no family means no opinion",
      tuning.ram_check("mystery:latest", 0, ram_gb=7.85) is None)

# ---------------------------------------------------------------------------
section("the memory line says what to avoid")
# ---------------------------------------------------------------------------
avoid16 = tuning.too_heavy_for(15.8)
check("16 GB is warned off qwen3", "qwen3" in avoid16)
check("16 GB is NOT warned off qwen2.5", "qwen2.5" not in avoid16)
avoid8 = tuning.too_heavy_for(7.85)
check("8 GB is warned off qwen2.5 too", "qwen2.5" in avoid8)
check("32 GB is warned off nothing", tuning.too_heavy_for(31.04) == [])
check("unknown RAM warns off nothing", tuning.too_heavy_for(None) is not None)

# ---------------------------------------------------------------------------
section("the boot lines")
# ---------------------------------------------------------------------------
cfg = config._deep_merge(config.DEFAULTS, {})
persona = personalities.get("scp079")
_real_ram = power.ram_gb


def boot_text(ram, **kw):
    power.ram_gb = lambda: ram
    try:
        rows = []
        for step in persona.build_boot(cfg, None, False, **kw):
            if step["kind"] == "line":
                rows.append(step["text"])
            elif step["kind"] in ("leader", "hold"):
                rows.append("%s %s" % (step["label"], step.get("status")))
        return "\n".join(rows).upper()
    finally:
        power.ram_gb = _real_ram


READABLE = {"found": True, "readable": True, "path": "p", "error": None}
BLOCKED = {"found": True, "readable": False, "path": "p",
           "error": "ACCESS IS DENIED"}
MISSING = {"found": False, "readable": False, "path": "p", "error": "NOT FOUND"}

text = boot_text(15.8, model="qwen3.6:latest", size=23 * GB, storage=READABLE)
check("memory line flags LOW", "CHECKING MEMORY LOW" in text)
check("it names the shortfall", "QWEN3 NEEDS 32 GB" in text)
check("the period flavour survives", "PARITY VERIFIED" in text)

text = boot_text(15.8, model="llama3.2:3b", size=2 * GB, storage=READABLE)
check("memory line is OK for a model that fits", "CHECKING MEMORY OK" in text)
check("but it still says what to avoid", "AVOID" in text and "QWEN3" in text)

text = boot_text(31.04, model="llama3.2:3b", size=2 * GB, storage=READABLE)
check("a big machine gets no avoid list", "AVOID" not in text)
check("it still reports the figure", "HOST 32 GB" in text)

# The two link lines, and the split between them.
text = boot_text(31.04, model="llama3.2:3b", size=2 * GB, storage=BLOCKED)
check("a blocked folder fails the HANDSHAKE", "ERROR ACCESSING LINK" in text)
check("it blames the right thing", "ANTIVIRUS" in text)
check("but LOCATING still succeeds", "NOT LOCATED" not in text)

text = boot_text(31.04, model="llama3.2:3b", size=2 * GB, storage=MISSING)
check("a missing store fails LOCATING", "NOT LOCATED" in text)
check("it says how to fix it", "OLLAMA PULL" in text)
check("but the HANDSHAKE still acks", "ERROR ACCESSING LINK" not in text)

text = boot_text(31.04, model="llama3.2:3b", size=2 * GB, storage=READABLE)
check("a healthy machine gets neither failure",
      "ERROR ACCESSING LINK" not in text and "NOT LOCATED" not in text)
check("no storage info at all is not a failure",
      "NOT LOCATED" not in boot_text(31.04, model="llama3.2:3b", storage=None))

# ---------------------------------------------------------------------------
section("the model store probe")
# ---------------------------------------------------------------------------
probe = ollama.storage_status()
check("it always answers with the shape callers expect",
      set(probe) >= {"path", "found", "readable", "error"})
check("it never raises on a real machine", isinstance(probe["found"], bool))
_env = os.environ.get("OLLAMA_MODELS")
os.environ["OLLAMA_MODELS"] = os.path.join(SANDBOX, "moved-models")
check("OLLAMA_MODELS is honoured", "moved-models" in ollama.models_dir())
check("a moved-but-absent store reports not found",
      ollama.storage_status()["found"] is False)
if _env is None:
    del os.environ["OLLAMA_MODELS"]
else:
    os.environ["OLLAMA_MODELS"] = _env

# ---------------------------------------------------------------------------
section("079 cannot reach the easter-egg sound")
# ---------------------------------------------------------------------------
# THE BUG: the explosion mp3 sits in sounds/ beside the player's own files, so
# it landed in 079's palette. It started issuing >>PLAY on it in conversation -
# the bang with no gif, no lockout and no joke.
check("the explosion filename is reserved",
      audio_mod._is_reserved("sound effect 1  explosion"))
check("the gif's odd spelling is reserved too",
      audio_mod._is_reserved("tenor_explosiom"))
check("fire is reserved", audio_mod._is_reserved("Fire"))
check("an ordinary sound is not reserved",
      not audio_mod._is_reserved("door slam"))
check("a player's own alarm sound is not reserved",
      not audio_mod._is_reserved("alarm loop 3"))


class FakeSound:
    def __init__(self):
        self.played = 0

    def set_volume(self, v):
        pass

    def play(self):
        self.played += 1


class Bare(audio_mod.Audio if hasattr(audio_mod, "Audio") else object):
    def __init__(self):
        self.enabled = True
        self.volume = 0.5
        self.custom = {}
        self.reserved = {}
        self.sounds = {}
        self.wants = {}


bare = Bare()
bang = FakeSound()
ordinary = FakeSound()
bare.reserved["sound_effect_1__explosio"] = bang
bare.custom["door_slam"] = ordinary

check("the bang is absent from 079's list",
      "sound_effect_1__explosio" not in bare.custom_names())
check("an ordinary sound IS in 079's list", "door_slam" in bare.custom_names())
check("079 cannot play the bang even by exact name",
      bare.play_custom("sound_effect_1__explosio") is False)
check("the bang did not sound", bang.played == 0)
check("079 can still play its own sounds",
      bare.play_custom("door_slam") is True and ordinary.played == 1)
check("the game CAN still fire the bang for the easter egg",
      bare.play_effect("explos") is True and bang.played == 1)

# ---------------------------------------------------------------------------
section("feedback sends only what it says it sends")
# ---------------------------------------------------------------------------
import feedback

payload = feedback.compose("bug", "the meter drains oddly", "llama3.2:3b")
check("the note itself is in the body", "the meter drains oddly" in payload["body"])
check("the version is attached", "1.0.0" in payload["body"])
check("the model is attached", "llama3.2:3b" in payload["body"])

# THE ONE THAT MATTERS. The screen promises the username is not sent, and a
# promise on screen is worth nothing without something holding it.
whoami = (os.environ.get("USERNAME") or os.environ.get("USER") or "colde")
check("the username is NOT in the body",
      whoami.lower() not in payload["body"].lower())
check("no home path leaks in", "users\\" not in payload["body"].lower())
check("no file paths at all", ":\\" not in payload["body"])

# ONE topic now, not three. Three meant three subscriptions on the owner's
# phone to see everything, and a bug report in a feed nobody added is no
# better than no bug report.
topics = {feedback.TOPICS[k][0] for k in feedback.TOPICS}
check("everything goes to a single topic", len(topics) == 1)
only = topics.pop()
check("it is namespaced to this project", only.startswith("scp079-"))
check("it carries an unguessable suffix", len(only.split("-")[-1]) >= 10)
check("not reusing the fish.exe topics", "fishexe" not in only)

# The category moved into the TITLE, which is what ntfy shows in bold above
# the body - so the feed is still sortable by eye without separate channels.
titles = {feedback.TOPICS[k][1] for k in feedback.TOPICS}
check("each category still has its own title", len(titles) == 3)
check("titles are prefixed consistently",
      all(t.startswith("Feedback-") for t in titles))
check("a bug is titled Feedback-Bug",
      feedback.TOPICS["bug"][1] == "Feedback-Bug")

# THE POINT OF ENCODING THEM. The client has to reach the topic, so this is
# obscurity and the source says so - but it must at least not be greppable,
# or publishing the repo hands the address to anyone who scrolls past.
_src = open(os.path.join(APP, "feedback.py"), encoding="utf-8").read()
check("the topic is not a plaintext string in the source", only not in _src)
check("the source is honest about what that achieves",
      "OBSCURITY, NOT SECURITY" in _src)

for args, why in ((("bug", ""), "an empty note"),
                  (("bug", "   \n  "), "whitespace only"),
                  (("nonsense", "hello"), "an unknown category")):
    try:
        feedback.compose(*args)
        check("%s is refused" % why, False)
    except feedback.FeedbackError:
        check("%s is refused" % why, True)

capped = feedback.compose("other", "x" * 5000)
check("an overlong note is capped", len(capped["body"]) < 2100)
check("the capped note still carries its context", "v1.0.0" in capped["body"])
check("three categories are offered", len(feedback.categories()) == 3)

shutil.rmtree(SANDBOX, ignore_errors=True)
print()
print("PASS %d   FAIL %d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
