"""Checks whether the current Ollama settings actually suit the chosen model.

The knob that matters is keep_alive. Ollama unloads the weights that long
after a reply, and reloading a large model from disk is expensive - measured
on a 23GB model, 37.4s to reload versus 0.3s when it was still resident. The
default 5 minutes is shorter than the gap between messages while somebody
reads and types, so a big model gets reloaded on EVERY message and the game
looks broken rather than slow.

Nothing here changes anything on its own. It reports what is wrong and what
it would set instead; main.py asks first and only applies on a yes.
"""

# Above this, reloading is slow enough that a short keep_alive is the
# difference between playable and unusable. Comfortably above llama3.2:3b
# (2GB), well below qwen3.6 (23GB).
LARGE_MODEL_BYTES = 6 * 1024 * 1024 * 1024

# keep_alive values that mean "drop it almost immediately"
SHORT_KEEP_ALIVE = ("0", "5m", "1m", "30s", "0s")

RECOMMENDED_KEEP_ALIVE = "30m"

# A model built for code changes what 079 is allowed to do, so this has to be
# reachable from both main.py and the personality. It lives here rather than
# in main because personalities cannot import main without a cycle, and this
# module already exists to answer questions about a model's characteristics.
#
# Matched on the name because that is all Ollama exposes. Deliberately loose:
# the cost of a false positive is a model that writes poor code, not anything
# breaking.
CODING_MODEL_HINTS = ("coder", "code", "codestral", "starcoder", "codegemma",
                      "codellama", "deepseek-coder", "qwen2.5-coder")


def is_coding_model(name):
    low = (name or "").lower()
    return any(hint in low for hint in CODING_MODEL_HINTS)


# Models that deliberate before they answer. The <think> block is generated
# FIRST and out of the same token budget as the speech, so on these a reply
# is not slow because something is wrong - it is slow because the model is
# doing the thing it was built to do. Worth saying out loud at startup: a
# silent minute reads as a hang, and the honest version of that wait is
# telling someone it is coming.
#
# Matched on the name, which is all Ollama exposes, and kept to families that
# actually reason rather than every large model. A false positive here only
# costs one line of startup text.
REASONING_MODEL_HINTS = ("qwen3", "qwq", "deepseek-r1", "marco-o1",
                         "openthinker", "reflection")


def is_reasoning_model(name):
    low = (name or "").lower()
    if is_coding_model(low):
        return False
    return any(hint in low for hint in REASONING_MODEL_HINTS)


# ---------------------------------------------------------------------------
# Host RAM vs the chosen model
# ---------------------------------------------------------------------------
# Families with a stated minimum, in GB of system RAM. These are the published
# recommendations for running the model at all comfortably - not a guess from
# the file size, which understates it: weights are only part of what a running
# model needs, and the KV cache grows with the context window on top.
FAMILY_RAM_GB = {
    "qwen3": 32,
    "qwen2.5": 16,
    "llama3.3": 32,
    "mixtral": 32,
    "command-r": 32,
}

# Fallback when the family is not listed: weights plus room to actually run.
# 1.4x is the rule of thumb that matches the listed families reasonably well.
SIZE_RAM_MULTIPLIER = 1.4
MIN_HEADROOM_GB = 2.0


def family_of(model):
    """Which RAM rule applies. Longest match wins so qwen2.5 is not read as
    qwen3 by an unlucky substring."""
    low = (model or "").lower()
    best = None
    for name in FAMILY_RAM_GB:
        if name in low and (best is None or len(name) > len(best)):
            best = name
    return best


def required_ram_gb(model, size_bytes=0):
    """How much RAM this model wants. 0 if there is no basis to say.

    A LISTED family minimum wins outright and is not raised by the file
    size. These are published figures, and quoting "the minimum for qwen3 is
    34 GB" because a 23 GB download happened to multiply out that way is
    both wrong and unrecognisable to anyone who has read the model card.
    The size rule is a fallback for models with no listed figure, not a
    second opinion about the ones that have one.
    """
    listed = FAMILY_RAM_GB.get(family_of(model), 0)
    if listed:
        return float(listed)
    if size_bytes:
        gb = size_bytes / float(1024 ** 3)
        return gb * SIZE_RAM_MULTIPLIER + MIN_HEADROOM_GB
    return 0.0


def ram_check(model, size_bytes=0, ram_gb=None):
    """Should this model be loaded on this machine? None if there is no
    concern, otherwise a dict the caller turns into a question.

    Never returns a concern when the RAM figure is unknown. A system call
    that failed is not evidence of a small machine.
    """
    import power

    required = required_ram_gb(model, size_bytes)
    if not required:
        return None
    if ram_gb is None:
        ram_gb = power.ram_gb()
    if ram_gb is None:
        return None
    if power.has_ram(required, total=ram_gb):
        return None

    family = family_of(model)
    return {
        "model": model,
        "family": family,
        "required": int(round(required)),
        "have": power.describe_ram(ram_gb),
        "have_gb": ram_gb,
        "listed": bool(FAMILY_RAM_GB.get(family)),
        "size": size_bytes,
    }


def ram_headline(concern):
    """The sentence the player is actually shown."""
    if not concern:
        return ""
    if concern["listed"]:
        return ("YOU HAVE %s OF MEMORY. THE MINIMUM RECOMMENDED FOR %s MODELS "
                "IS %d GB." % (concern["have"], concern["family"].upper(),
                               concern["required"]))
    return ("YOU HAVE %s OF MEMORY. %s NEEDS ABOUT %d GB TO RUN WITHOUT "
            "PAGING." % (concern["have"], str(concern["model"]).upper(),
                         concern["required"]))


def too_heavy_for(ram_gb=None):
    """Which listed families this machine should avoid, biggest first.

    Shown on the boot's memory line so the number means something: '16 GB'
    on its own does not tell anyone what not to pick.
    """
    import power

    if ram_gb is None:
        ram_gb = power.ram_gb()
    if ram_gb is None:
        return []
    out = [(need, name) for name, need in FAMILY_RAM_GB.items()
           if not power.has_ram(need, total=ram_gb)]
    return [name for _need, name in sorted(out, reverse=True)]


def human_gb(size):
    return "%.0f GB" % (size / float(1024 ** 3))


def check(cfg, model, sizes):
    """What is wrong for this model, and what to set instead.

    Returns None when nothing needs changing, otherwise:
        {"model", "size", "reasons": [str], "changes": {dotted: (old, new)}}
    """
    size = int((sizes or {}).get(model) or 0)
    if size < LARGE_MODEL_BYTES:
        return None

    ollama_cfg = cfg.get("ollama", {})
    reasons, changes = [], {}

    keep_alive = str(ollama_cfg.get("keep_alive", "5m"))
    if keep_alive in SHORT_KEEP_ALIVE:
        reasons.append(
            "THIS MODEL IS %s. AT '%s' IT IS UNLOADED BETWEEN MESSAGES AND "
            "RELOADED FROM DISK EVERY TIME YOU SPEAK."
            % (human_gb(size), keep_alive))
        changes["ollama.keep_alive"] = (keep_alive, RECOMMENDED_KEEP_ALIVE)

    # A reasoning model spends its token budget deliberating before it writes
    # anything visible, so a capped reply can come back completely empty.
    if ollama_cfg.get("think"):
        reasons.append(
            "REASONING IS ON. IT CONSUMES THE REPLY BUDGET BEFORE ANY TEXT "
            "IS WRITTEN, WHICH CAN RETURN AN EMPTY REPLY.")
        changes["ollama.think"] = (True, False)

    if not changes:
        return None
    return {"model": model, "size": size, "reasons": reasons, "changes": changes}


def apply(cfg, changes):
    """Write the recommended values into cfg. Returns the keys changed."""
    applied = []
    for dotted, (_old, new) in (changes or {}).items():
        section = cfg
        parts = dotted.split(".")
        for key in parts[:-1]:
            section = section.setdefault(key, {})
        section[parts[-1]] = new
        applied.append(dotted)
    return applied
