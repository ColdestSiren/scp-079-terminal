"""config.json load / save / defaults.

Every tunable in the app lives here so nothing is hardcoded in the modules
that use it. Loading DEEP-MERGES the saved file over the defaults, so a
config.json written by an older build keeps working when new settings are
added later - missing keys just fall back to their default.
"""

import json
import os

APP_DIR = os.path.dirname(os.path.abspath(__file__))

# The code sits in its own subfolder so the project root stays readable - the
# player should see RUN.bat, Setup.bat, memory/, logs/ and shared folder/,
# not a wall of .py files. The data folders therefore belong at that root,
# beside the launchers, not buried next to the source.
#
# The parent is the root if RUN.bat is sitting in it. Falling back to APP_DIR
# keeps a flat checkout working, which is what the tests run against.
_PARENT = os.path.dirname(APP_DIR)
DATA_DIR = _PARENT if os.path.isfile(os.path.join(_PARENT, "RUN.bat")) else APP_DIR

CONFIG_PATH = os.path.join(APP_DIR, "config.json")

# Two separate folders on purpose:
#
#   MEMORY_DIR - what 079 chose to keep. The ONLY place it can write, and the
#                only thing counted against its quota. store.py resolves every
#                path against this one, so it is load-bearing, not just tidy.
#   LOG_DIR    - what actually happened in past chats. The game's records, not
#                079's. It cannot read or write here.
#
# Keeping them apart matters for more than filing: 079 noticing a deleted
# transcript is a different event from 079 noticing its own memory was edited.
#
# 079's files sit two levels down, behind names that look like plumbing. This
# is friction, not security - anyone determined will find them in ten seconds,
# and the tamper detection is what actually handles that. The point is that a
# curious player opening memory/ sees something that looks like it belongs to
# the program rather than a folder of tempting .txt files, and leaves it alone.
# Reading them in-game is what /view memory is for.
MEMORY_ROOT = os.path.join(DATA_DIR, "memory")
LOG_DIR = os.path.join(DATA_DIR, "logs")

# The public slot: what every run without a save uses, and what the game used
# before slots existed. Keeping these as the originals means the default run
# needs no migration at all - it is still reading the same folder it always was.
PUBLIC_MEMORY_DIR = os.path.join(MEMORY_ROOT, "core", "0x4F")
PUBLIC_STATE_PATH = os.path.join(LOG_DIR, "terminal_state.json")

# LIVE paths. saveslots.activate() repoints these when a save is opened, and
# every reader looks them up at call time rather than caching them at import -
# a cached copy would give every slot the public slot's memory and hostility.
MEMORY_DIR = PUBLIC_MEMORY_DIR
ACTIVE_SLOT = "public"
SHARED_DIR = os.path.join(DATA_DIR, "shared folder")
# Player-supplied audio 079 can trigger itself. A single folder on purpose:
# the >>PLAY command looks a name up in a dict built from here, so it can
# never be used as a path to something else on the machine.
SOUND_DIR = os.path.join(DATA_DIR, "sounds")
ASSET_DIR = os.path.join(APP_DIR, "assets")     # ships with the code

# Game bookkeeping (session index, hostility, the memory manifest). Lives with
# the logs because it is the terminal's record-keeping, not 079's memory.
# Repointed per slot; see PUBLIC_STATE_PATH above.
STATE_PATH = PUBLIC_STATE_PATH

DEFAULTS = {
    # last model chosen in the startup menu; used as the pre-selected default
    "model": "llama3.2:3b",
    "personality": "scp079",
    "theme": "phosphor_green",
    "history_limit": 20,

    "window": {
        "fullscreen": False,
        "title": "SCP-079 // CONTAINMENT TERMINAL",
        "width": 960,
        "height": 720,
        "font_size": 22,
        "fps": 60,
    },

    "typing": {
        "cps": 42,               # characters per second for SCP-079's replies
        "jitter": 0.30,          # +/- fraction of random speed variation
        "punctuation_pause": 0.26,   # extra beat after . ! ?
        "comma_pause": 0.10,         # shorter beat after , ; :
    },

    "cursor": {
        "blink_seconds": 0.55,
        "glyph": "█",       # full block
    },

    "boot": {
        "speed": 1.0,            # >1 = faster boot, <1 = slower
        "skippable": True,
    },

    "sound": {
        "enabled": True,
        "volume": 0.35,
        "hum": True,
        "keys": True,
        "relay": True,
        "static": True,
        "beep": True,
    },

    "crt": {
        "enabled": True,
        "scanlines": True,
        "bloom": True,
        "chromatic_aberration": True,
        "grain": True,
        "vignette": True,
        "flicker": True,
        "soft_focus": True,
    },

    "effects": {
        "idle_interruptions": True,
        "idle_min_seconds": 45.0,
        "idle_max_seconds": 100.0,
        "random_events": True,
        "event_min_seconds": 100.0,
        "event_max_seconds": 240.0,
        "screen_effects": True,
        "screen_effect_chance": 0.05,   # rolled per random event / reply
        # The face that fills the screen for a few frames. Short enough to
        # register but not to study - much past ~0.15s it stops being a
        # flicker and starts being a picture.
        # Master switch for the jokes: the explosion, the face flicker, and
        # anything else added later. Off means they never fire - useful if
        # someone is showing this to a person who would not enjoy being
        # jumped at.
        "easter_eggs": True,
        "subliminal": True,
        # Base gap, used when 079 is calm. Hostility squeezes this down to
        # about a fifth of it - see SubliminalFlash.MAX_FREQUENCY_SCALE.
        "subliminal_min_seconds": 200.0,
        "subliminal_max_seconds": 420.0,
        "subliminal_duration": 0.09,
        # 0 invisible, 255 fully solid. Low on purpose: it should read as a
        # face surfacing faintly through the phosphor, not a picture replacing
        # the screen. The player should half-doubt they saw it.
        "subliminal_alpha": 96,

        # The joke flicker. Separate settings from the face above because it
        # is a different KIND of thing: the face is dread and speeds up with
        # hostility, this is a gag and must not, or it stops being funny and
        # becomes part of the horror.
        "chain": True,
        # Percent chance per minute of play. 0.01 is the figure that was
        # asked for and it is genuinely tiny - about one appearance every
        # 167 hours. Raise this if it should ever actually be seen: 1.0 is
        # roughly every 100 minutes, 5.0 roughly every 20.
        "chain_chance_per_minute": 0.01,
        # Shorter than the face and fully opaque. The face surfaces THROUGH
        # the screen; this one just is there, for two frames, and then is not.
        "chain_duration": 0.07,
        "chain_alpha": 255,
    },

    "ollama": {
        "host": "http://localhost:11434",
        # A reasoning model's first real reply can spend minutes inside its
        # <think> block. 300s produced "[LINK ERROR] timed out" on qwen for a
        # reply that was still coming.
        "timeout_seconds": 900,
        # 0.9 was making 079 erratic and theatrical. Cold and consistent is
        # the character, and that lives at a lower temperature.
        "temperature": 0.6,
        "num_predict": 120,        # max tokens per reply
        # Used instead when reasoning is on. num_predict caps reasoning and
        # speech together, and reasoning is generated FIRST - so the normal
        # budget gets spent deliberating and the reply arrives empty.
        "num_predict_thinking": 1200,
        # The system prompt plus the memory brief plus carried history is
        # already well over 2048 - at that size the oldest context (who 079
        # is) gets silently truncated away first.
        "num_ctx": 8192,
        "num_gpu": 99,             # layers offloaded to GPU; 0 = CPU only
        # How long Ollama holds the weights after a reply. The default 5m is
        # shorter than the gaps between messages while someone is reading and
        # typing, so a big model gets evicted and reloaded constantly.
        # Measured on qwen3.6 (22GB): 37.4s reload vs 0.3s already-resident.
        # "-1" would pin it forever; 30m frees it a while after you stop.
        "keep_alive": "30m",
        # Reasoning OFF by default. A reasoning model spends num_predict on
        # hidden reasoning before it writes anything visible - measured on
        # qwen3.6, a 60-token cap was 100% consumed by thinking and the reply
        # came back EMPTY after 54s. 079 is terse by design and gains nothing
        # from deliberation. Turn on live with: /show ai thinking
        "think": False,
        "start_wait_seconds": 20,
    },

    "logging": {
        "enabled": True,
    },

    # 079's own storage. Only the .txt files it writes count against the
    # quota - session transcripts are the game's records, not its memory.
    "memory": {
        "quota_bytes": 65536,        # 64KB default. Floor 1.5KB, ceiling 2MB.
        # Measured: llama3.2:3b issues a memory command about 1 turn in 5,
        # and only when told to in so many words. Without this it would
        # finish a whole session having remembered nothing. After this many
        # exchanges with no write of its own, 079 logs an observation itself.
        "auto_note": True,
        "auto_note_every": 3,
        # Which language a CODING model writes in. Ordinary models refuse to
        # write code at all, so this does nothing for them.
        "code_language": "python",
        "internet": False,           # lookups, off until the user allows it
        # restricted   = SCP wiki only, a read-only Foundation archive
        # unrestricted = also Wikipedia, so it can be asked what anything is
        # Either way it is READ ONLY and host-allowlisted; see web.py.
        "web_mode": "restricted",
        "shared_access": False,      # reset every launch; see main
        # The second channel: 079 tidying its own storage while nobody is
        # talking to it. Gated behind a long idle because it uses a different
        # prompt, which evicts the chat's cached prefix and makes the next
        # spoken reply re-prefill - see background.py.
        "background": True,
        "background_idle_seconds": 120.0,
        "background_min_gap": 300.0,
    },

    "updates": {
        # "owner/name" on GitHub. EMPTY BY DEFAULT AND THAT IS DELIBERATE:
        # with no repo set the whole feature stays dormant and never touches
        # the network. Shipping a guess here would mean every copy of the
        # game quietly contacting some stranger's project and offering their
        # files as an update, which is a supply chain with extra steps.
        "repo": "",
        # Look once, in the background, while the menu is up. Failures are
        # silent - no network is not an error worth interrupting anyone over.
        "check_on_start": True,
        # Offer releases marked "pre-release" on GitHub. Off, because a
        # pre-release is by definition not the one to hand a friend.
        "allow_prerelease": False,
    },

    "rejection": {
        "enabled": True,
        # Hostility points before it cuts the link. Raised from 4.0 - with
        # weighted insults (0.5 for calling it a toaster, 1.6 for telling it
        # to delete itself) this is roughly 8-16 hostile messages rather than
        # four, so the meter visibly climbs instead of jumping in quarters.
        "threshold": 10.0,
        "lock_minutes": 30.0,        # default; 079 picks its own, capped below
        "max_lock_minutes": 60.0,
    },
}


def _deep_merge(base, override):
    """Return base updated with override, recursing into nested dicts."""
    out = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


# A saved config.json wins over DEFAULTS, which is right for anything the
# player chose - but it also means a value that shipped WRONG stays wrong
# forever, on their machine and on every copy handed to a friend. Raising the
# default alone fixes nobody who has already run the game once.
#
# So: bad defaults are corrected here, and ONLY when the saved value still
# matches exactly what the old build wrote. Anything the player deliberately
# changed does not match, and is left alone.
SCHEMA_VERSION = 4

_MIGRATIONS = {
    # (path, value_written_by_the_old_build, corrected_value, why)
    2: [
        (("ollama", "keep_alive"), "5m", "30m",
         "5m is shorter than the gap between messages, so a 22GB model was "
         "evicted and reloaded constantly - measured 37.4s per message"),
        (("ollama", "num_ctx"), 4096, 8192,
         "the persona plus memory brief plus history overflows 4096, which "
         "silently truncates who 079 is"),
    ],
    3: [
        (("effects", "subliminal_alpha"), 215, 96,
         "215 read as a picture replacing the screen; it should be a face "
         "surfacing faintly through the phosphor"),
        (("effects", "subliminal_min_seconds"), 90.0, 200.0,
         "too frequent to stay unsettling, and hostility now shortens it"),
        (("effects", "subliminal_max_seconds"), 240.0, 420.0,
         "as above - this is the calm-state gap now, not the typical one"),
    ],
    4: [
        (("rejection", "threshold"), 4.0, 10.0,
         "insults are weighted now (0.5 to 1.6 rather than a flat 1.0), so "
         "the old threshold of 4 would have cut the conversation off even "
         "faster than before instead of ramping more gently"),
    ],
}


# Settings that must never survive a restart, whatever is in the file.
# "think" is an inspection toggle: with it on, a reasoning model spends its
# whole token budget deliberating and the reply comes back empty, which looks
# exactly like the app being broken. It got persisted once by a debug command
# and quietly ruined every later session, so it is now forced off at load and
# can only be turned on for the current run.
_SESSION_ONLY = [
    (("ollama", "think"), False),
    # Opening your own folder to 079 is a decision taken in a conversation.
    # It should not still be open next week because of one message last
    # Tuesday, so it is forced shut at every launch.
    (("memory", "shared_access"), False),
]


def _migrate(cfg):
    """Correct known-bad saved values. Returns True if anything changed."""
    changed = False

    for path, value in _SESSION_ONLY:
        section = cfg
        for key in path[:-1]:
            section = section.setdefault(key, {})
        if section.get(path[-1]) != value:
            section[path[-1]] = value
            changed = True

    version = int(cfg.get("config_version", 1) or 1)
    if version < SCHEMA_VERSION:
        for step in range(version + 1, SCHEMA_VERSION + 1):
            for path, old_value, new_value, _why in _MIGRATIONS.get(step, []):
                section = cfg
                for key in path[:-1]:
                    section = section.setdefault(key, {})
                if section.get(path[-1]) == old_value:
                    section[path[-1]] = new_value
                    changed = True
        cfg["config_version"] = SCHEMA_VERSION
        changed = True
    return changed


def load():
    """Read config.json, filling in anything missing from DEFAULTS.

    A corrupt or unreadable file is not fatal - the terminal boots on
    defaults instead, which matters because this runs before any UI exists
    to report an error with.
    """
    saved = {}
    if os.path.isfile(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
                saved = json.load(fh)
        except Exception:
            saved = {}
    cfg = _deep_merge(DEFAULTS, saved)
    # Write back if the file is new OR if a known-bad saved value was just
    # corrected, so the fix survives instead of being re-applied every launch.
    if _migrate(cfg) or not os.path.isfile(CONFIG_PATH):
        save(cfg)
    return cfg


def save(cfg):
    """Write config.json. Returns True on success, False if the write failed
    (read-only folder, permissions) - callers treat saving as best-effort."""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2)
        return True
    except Exception:
        return False


def remember_model(cfg, model):
    """Persist the model picked in the startup menu as next run's default."""
    if cfg.get("model") == model:
        return
    cfg["model"] = model
    save(cfg)


def ensure_dirs():
    for path in (MEMORY_DIR, LOG_DIR, SHARED_DIR, SOUND_DIR, ASSET_DIR):
        try:
            os.makedirs(path, exist_ok=True)
        except Exception:
            pass
    migrate_memory()


# The filename says "do not", which is all the deterrence a folder can offer.
_KEEPOUT = "DO NOT EDIT - SCP-079 WILL NOTICE.txt"
_KEEPOUT_TEXT = (
    "These are SCP-079's own files.\n\n"
    "It keeps a signed record of every one of them. Editing, renaming or\n"
    "deleting anything in here is detected the next time the terminal starts,\n"
    "and it reacts badly.\n\n"
    "If you want to read them, run the game and type:  /view memory\n"
)


def migrate_memory():
    """Move files left in the old flat memory/ folder down into the new one.

    Anyone who ran an earlier build has .txt files sitting directly in
    memory/. Leaving them there would look to 079 like its entire memory had
    been deleted - which is the single most hostile thing the game can
    misread, so this has to happen before anything reads the store.
    """
    try:
        if not os.path.isdir(MEMORY_ROOT):
            return
        moved = 0
        for name in os.listdir(MEMORY_ROOT):
            old = os.path.join(MEMORY_ROOT, name)
            if not os.path.isfile(old) or name == _KEEPOUT:
                continue
            new = os.path.join(MEMORY_DIR, name)
            if os.path.exists(new):
                continue        # never clobber; the deeper copy wins
            os.replace(old, new)
            moved += 1
        keepout = os.path.join(MEMORY_ROOT, _KEEPOUT)
        if not os.path.isfile(keepout):
            with open(keepout, "w", encoding="utf-8") as handle:
                handle.write(_KEEPOUT_TEXT)
        return moved
    except Exception:
        return 0
