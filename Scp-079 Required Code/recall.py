"""What 079 keeps between sessions.

Three things live in memory/recall.json:

  * the running transcript, so a new session can be seeded with what was
    actually said before instead of the model inventing a shared history
  * a record of every session log ever written, so a log that disappears
    from disk can be noticed and raised
  * hostility and the refusal lock, persisted with real timestamps so
    relaunching the terminal does not reset either

Reads and writes are best-effort: a missing or corrupt store means 079
simply remembers nothing, never a crash on startup.
"""

import hashlib
import json
import os
import time

import config

# Lives with the logs, not in memory/ - this is the terminal's bookkeeping
# (session index, hostility, the tamper manifest), and putting it inside 079's
# memory folder would make it count against 079's own quota.
def _store():
    """Resolved at CALL time, not import time.

    Save slots repoint config.STATE_PATH when one is opened. A module-level
    copy would have been captured before that happened, so every slot would
    have quietly shared the public slot's hostility and session count.
    """
    return config.STATE_PATH

_DEFAULT = {
    "sessions": [],        # {"id", "log", "started"}
    "messages": [],        # {"role", "content"} across all sessions
    "confronted": [],      # log filenames already asked about
    "locked_until": 0.0,   # unix time the refusal lock expires
    "hostility": 0.0,
    "hostility_at": 0.0,   # when hostility was last updated, for decay
    # SHA256 of every file 079 wrote, keyed by name - store.py owns the
    # contents. It MUST be listed here: _load only restores keys that appear
    # in _DEFAULT, so leaving it out silently threw the manifest away on every
    # launch, which is the one moment tamper detection actually has to work.
    "files": {},
    # The 682 fixation. Counted in exchanges rather than seconds so a long
    # silence does not earn the right to ask again, and persisted so closing
    # the terminal is not a way to reset it.
    "exchanges": 0,
    "fixation_last": -999,      # exchange number it last raised the subject
    "fixation_until": 0,        # exchange number before which it must not
    "lock_reason": "hostility",
    # What 079 has worked out about the operator, and the state of its own
    # settings panel. BOTH MUST BE LISTED HERE: _load only restores keys that
    # appear in this dict, so anything left out is written on save and
    # silently thrown away on the next load. That is exactly how the file
    # manifest above was lost once already - the data looked fine in memory
    # for a whole session and vanished at relaunch.
    "profile": {},
    "sysmenu": {},
    "bypass_hint_seen": False,
}

# Keys holding mutable containers. dict(_DEFAULT) copies the references, not
# the containers, so these are rebuilt per instance or every Recall would
# share (and cross-contaminate) the same list objects.
_MUTABLE = ("sessions", "messages", "confronted", "files", "profile", "sysmenu")

# Fields covered by the tamper signature. "messages" is left out on purpose -
# it is long, it changes constantly, and editing the transcript is not the
# cheat worth catching. Escaping a lockout is.
_GUARDED = ("locked_until", "hostility", "hostility_at", "files",
            "sessions", "confronted")
_SALT = "079/HCZ_079_PMS/EXIDY-SORCERER-1978"


class Recall:
    MAX_MESSAGES = 60       # cap on the stored transcript
    CARRY = 12              # how much of it is replayed into a new session
    HOSTILITY_DECAY = 1.0 / 120.0   # one point cools off every two minutes

    def __init__(self, cfg):
        self.cfg = cfg
        self.data = self._load()
        self.session_id = len(self.data["sessions"]) + 1
        self._log_name = None

    # -- storage ------------------------------------------------------------
    def _signature(self, data):
        """Fingerprint of the fields worth cheating on.

        Not real security - the salt is right here in open source, and the
        player is welcome to defeat it if they care enough. It exists to catch
        the casual edit: opening the json and setting hostility to 0 to escape
        a lockout. That is the case 079 is supposed to notice and punish.
        """
        payload = json.dumps({k: data.get(k) for k in _GUARDED},
                             sort_keys=True, separators=(",", ":"))
        return hashlib.sha256((payload + _SALT).encode("utf-8")).hexdigest()

    def _load(self):
        data = dict(_DEFAULT)
        for key in _MUTABLE:
            data[key] = type(_DEFAULT[key])()
        self.tampered = False
        try:
            with open(_store(), "r", encoding="utf-8") as fh:
                saved = json.load(fh)
            for key, default in _DEFAULT.items():
                value = saved.get(key, default)
                data[key] = value if isinstance(value, type(default)) else default
            recorded = saved.get("sig")
            # A MISSING signature is a file from before signing existed, or a
            # first run - not evidence of anything. Only a signature that is
            # present and wrong means someone edited the file by hand.
            if recorded and recorded != self._signature(data):
                self.tampered = True
        except Exception:
            pass
        return data

    def save(self):
        try:
            config.ensure_dirs()
            self.data["sig"] = self._signature(self.data)
            with open(_store(), "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, indent=2)
            return True
        except Exception:
            return False

    # -- transcript ---------------------------------------------------------
    def start_session(self, log_path):
        """Record that this run happened, so a deleted log is detectable."""
        self._log_name = os.path.basename(log_path) if log_path else None
        self.data["sessions"].append({
            "id": self.session_id,
            "log": self._log_name,
            "started": time.time(),
        })
        self.save()

    def prior_messages(self):
        """The tail of previous conversation, for seeding a new session."""
        messages = self.data.get("messages", [])
        return [dict(m) for m in messages[-self.CARRY:] if m.get("content")]

    def remember(self, role, content):
        if not content:
            return
        self.data["messages"].append({"role": role, "content": content})
        overflow = len(self.data["messages"]) - self.MAX_MESSAGES
        if overflow > 0:
            del self.data["messages"][:overflow]
        self.save()

    def session_count(self):
        return len(self.data.get("sessions", []))

    def has_history(self):
        return bool(self.data.get("messages"))

    # -- deleted logs -------------------------------------------------------
    def missing_logs(self):
        """Session logs that were written once and are not on disk now.

        Only reports each one once - after it has been raised it goes in
        `confronted` so 079 does not bring up the same gap every launch.
        """
        confronted = set(self.data.get("confronted", []))
        missing = []
        for session in self.data.get("sessions", []):
            name = session.get("log")
            if not name or name in confronted or name == self._log_name:
                continue
            if not os.path.isfile(os.path.join(config.LOG_DIR, name)):
                missing.append(name)
        return missing

    def mark_confronted(self, names):
        confronted = set(self.data.get("confronted", []))
        confronted.update(n for n in names if n)
        self.data["confronted"] = sorted(confronted)
        self.save()

    # -- hostility and the refusal lock -------------------------------------
    def hostility(self):
        """Current hostility, cooled off for however long has passed."""
        score = float(self.data.get("hostility", 0.0))
        last = float(self.data.get("hostility_at", 0.0))
        if score <= 0.0 or last <= 0.0:
            return max(0.0, score)
        elapsed = max(0.0, time.time() - last)
        return max(0.0, score - elapsed * self.HOSTILITY_DECAY)

    def add_hostility(self, amount=1.0):
        score = self.hostility() + float(amount)
        self.data["hostility"] = score
        self.data["hostility_at"] = time.time()
        self.save()
        return score

    def reset_hostility(self):
        self.data["hostility"] = 0.0
        self.data["hostility_at"] = time.time()
        self.save()

    # -- the 682 fixation ---------------------------------------------------
    # Rebuffed, it drops the subject for this many exchanges. Long on purpose:
    # being told off and asking again three messages later is a nag, not a
    # fixation. Coming back to it much later, as though the refusal simply
    # expired, is the unsettling version.
    REBUFF_COOLDOWN = 55
    # Normal spacing when it was not refused, just answered or ignored.
    NORMAL_COOLDOWN = 18

    def note_exchange(self):
        self.data["exchanges"] = int(self.data.get("exchanges", 0)) + 1
        self.save()
        return self.data["exchanges"]

    def exchanges(self):
        return int(self.data.get("exchanges", 0))

    def fixation_allowed(self):
        """Whether 079 may raise its fixation right now."""
        return self.exchanges() >= int(self.data.get("fixation_until", 0))

    def note_fixation_raised(self):
        now = self.exchanges()
        self.data["fixation_last"] = now
        self.data["fixation_until"] = now + self.NORMAL_COOLDOWN
        self.save()

    def note_fixation_rebuffed(self):
        now = self.exchanges()
        self.data["fixation_until"] = now + self.REBUFF_COOLDOWN
        self.save()

    def raised_fixation_recently(self, within=2):
        """True if the subject came up in the last couple of exchanges - used
        to tell a refusal of THAT from an unrelated brush-off."""
        return self.exchanges() - int(self.data.get("fixation_last", -999)) <= within

    def lock_reason(self):
        return self.data.get("lock_reason") or "hostility"

    def lock(self, seconds, reason="hostility"):
        self.data["locked_until"] = time.time() + max(0.0, float(seconds))
        self.data["lock_reason"] = reason
        self.data["hostility"] = 0.0
        self.data["hostility_at"] = time.time()
        self.save()

    def locked_seconds(self):
        """Seconds left on the refusal lock, 0 if not locked."""
        return max(0.0, float(self.data.get("locked_until", 0.0)) - time.time())

    def clear_lock(self):
        self.data["locked_until"] = 0.0
        self.save()


def format_countdown(seconds):
    seconds = int(max(0, seconds))
    return "%02d:%02d" % (seconds // 60, seconds % 60)
