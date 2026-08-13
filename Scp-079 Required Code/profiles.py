"""Named snapshots of the settings, saved and reloaded on demand.

The point is that the terminal stops arguing with you. It shows what the
settings currently are, it can tell you when they suit the model badly, but
it never quietly rewrites them. If you want a particular arrangement kept,
you save it under a name and load it back whenever you like.

Only the settings a player actually tunes are captured - not the whole
config - so loading an old profile can never resurrect an unrelated stale
value or a path from a different machine.
"""

import json
import os

import config

STORE = os.path.join(config.LOG_DIR, "profiles.json")

# Exactly what a profile remembers. Anything outside this list is left alone
# on load, which is what makes loading an old profile safe.
CAPTURED = (
    ("ollama", "keep_alive"),
    ("ollama", "num_ctx"),
    ("ollama", "num_predict"),
    ("ollama", "num_gpu"),
    ("ollama", "temperature"),
    ("ollama", "timeout_seconds"),
    ("memory", "quota_bytes"),
    ("memory", "auto_note"),
    ("memory", "internet"),
)

# Shipped presets. These are starting points, never applied on their own.
BUILT_IN = {
    "LARGE MODEL": {
        "ollama.keep_alive": "30m",
        "ollama.num_ctx": 8192,
        "ollama.num_predict": 400,
        "ollama.num_gpu": 99,
    },
    "SMALL MODEL": {
        "ollama.keep_alive": "5m",
        "ollama.num_ctx": 4096,
        "ollama.num_predict": 200,
        "ollama.num_gpu": 99,
    },
    "CPU ONLY": {
        "ollama.keep_alive": "30m",
        "ollama.num_ctx": 4096,
        "ollama.num_predict": 200,
        "ollama.num_gpu": 0,
    },
}


def _get(cfg, section, key, default=None):
    return (cfg.get(section) or {}).get(key, default)


def capture(cfg):
    """The current settings, as a flat {"section.key": value} snapshot."""
    snapshot = {}
    for section, key in CAPTURED:
        value = _get(cfg, section, key)
        if value is not None:
            snapshot["%s.%s" % (section, key)] = value
    return snapshot


def apply(cfg, snapshot):
    """Write a snapshot into cfg. Unknown keys are ignored, so a profile
    written by a newer build cannot inject arbitrary settings."""
    allowed = {"%s.%s" % (s, k) for s, k in CAPTURED}
    applied = []
    for dotted, value in (snapshot or {}).items():
        if dotted not in allowed:
            continue
        section, key = dotted.split(".", 1)
        cfg.setdefault(section, {})[key] = value
        applied.append(dotted)
    return applied


def load_all():
    """{name: snapshot} - built-ins plus whatever the player saved."""
    saved = {}
    try:
        with open(STORE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            saved = {str(k): v for k, v in data.items() if isinstance(v, dict)}
    except Exception:
        saved = {}
    merged = dict(BUILT_IN)
    merged.update(saved)      # a saved profile may shadow a built-in name
    return merged


def user_profiles():
    """Only the ones the player saved - the built-ins cannot be deleted."""
    try:
        with open(STORE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return {str(k): v for k, v in data.items() if isinstance(v, dict)}
    except Exception:
        return {}


def save(name, cfg):
    """Store the current settings under `name`. Returns True on success."""
    name = (name or "").strip().upper()[:24]
    if not name:
        return False
    profiles = user_profiles()
    profiles[name] = capture(cfg)
    try:
        config.ensure_dirs()
        with open(STORE, "w", encoding="utf-8") as fh:
            json.dump(profiles, fh, indent=2)
        return True
    except Exception:
        return False


def delete(name):
    profiles = user_profiles()
    if name not in profiles:
        return False
    del profiles[name]
    try:
        with open(STORE, "w", encoding="utf-8") as fh:
            json.dump(profiles, fh, indent=2)
        return True
    except Exception:
        return False


def describe(snapshot):
    """Short human summary, for listing profiles on screen."""
    parts = []
    if "ollama.keep_alive" in snapshot:
        parts.append("KEEP %s" % snapshot["ollama.keep_alive"])
    if "ollama.num_ctx" in snapshot:
        parts.append("CTX %s" % snapshot["ollama.num_ctx"])
    if "ollama.num_gpu" in snapshot:
        parts.append("CPU ONLY" if snapshot["ollama.num_gpu"] == 0 else "GPU")
    return "  ".join(parts) or "NO SETTINGS"
