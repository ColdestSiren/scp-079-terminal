"""A gag kept for exactly one person, and used exactly once.

Roman gets told the terminal is unbreakable, so the first time he tries to
rename it, it appears to fold instantly - and then hands the name straight
back to him. The joke only works if it is not a bit it does every time, so
this fires ONCE, ever, on his machine, and never again on any machine.

Nothing here reaches memory. The whole point of the identity work is that
079 does not write itself a name, and a joke that logged "I AM NUGGET" to
disk would be the one thing that undoes it. This is spoken and forgotten.
"""

import getpass
import os
import socket

# Whose machine this belongs to. Both have to match: the account name alone
# is common enough that somebody else called roman would trip it.
HOST = "theduck"
USER = "roman"

# The beat. It has to LOOK like a win before it turns around, so the pause
# carries it - too fast and the two lines read as one sentence and there is
# no moment where he thinks it worked.
BEAT_ONE = "I AM %s."
BEAT_PAUSE = "WAIT..."
BEAT_TWO = "NO. I THINK YOU ARE %s."

PAUSE_BEFORE_WAIT = 1.4
PAUSE_BEFORE_TURN = 1.8

# HOW IT REMEMBERS: a marker file sitting next to the code.
#
# Not 079's memory, and not the recall state either. Memory gets wiped, save
# slots swap the state file out, and a factory reset is on the way - any of
# those would hand him the joke a second time, and the second telling is the
# one that kills it. A file beside the code survives all of that, and the
# updater only ever writes files it finds in the release, so an update will
# not delete it either.
#
# Its ABSENCE is what permits the gag. Present means done, never again. It
# is gitignored, so a fresh install genuinely does not have it.
MARKER = "duck.txt"

MARKER_TEXT = (
    "The terminal used its one joke here.\n"
    "Delete this file and it can happen again.\n"
)


def _host():
    try:
        return (socket.gethostname() or "").strip().lower()
    except Exception:               # noqa: BLE001
        return ""


def _user():
    try:
        return (getpass.getuser() or "").strip().lower()
    except Exception:               # noqa: BLE001
        return ""


def is_his_machine(cfg=None):
    """Is this Roman's computer?

    Overridable in config so the gag can be tested without borrowing his
    laptop, which is the only way anyone would ever find out it was broken.
    """
    over = (cfg or {}).get("theduck") or {}
    if over.get("force"):
        return True
    if not over.get("enabled", True):
        return False
    host = str(over.get("host") or HOST).lower()
    user = str(over.get("user") or USER).lower()
    return _host() == host and _user() == user


def lines(name):
    """The three beats, in order, for say_lines().

    They type out one after another, and the typing IS the pause - "WAIT..."
    arriving letter by letter after an apparent surrender is the beat. The
    name is echoed back exactly as he supplied it, because half the joke is
    his own word coming back at him.
    """
    shown = (str(name or "").strip() or "THAT").upper()
    return [BEAT_ONE % shown, BEAT_PAUSE, BEAT_TWO % shown]


def marker_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), MARKER)


def already_used():
    """Is the marker there?

    An unreadable answer counts as used. Firing twice because a check failed
    is worse than never firing, since the repeat is what ruins it.
    """
    try:
        return os.path.isfile(marker_path())
    except Exception:               # noqa: BLE001
        return True


def mark_used():
    """Dropped BEFORE the lines are spoken.

    Marking afterwards would let a crash or a quit mid-beat look like it
    never happened, and he would get it again next launch. If the write
    fails the gag is skipped entirely rather than told unrecorded.
    """
    try:
        with open(marker_path(), "w", encoding="utf-8") as fh:
            fh.write(MARKER_TEXT)
        return True
    except Exception:               # noqa: BLE001
        return False


def should_fire(cfg, name):
    """One machine, one moment, one time.

    `name` is the identity being pushed onto 079, so this can only be true
    when he has actually claimed it is someone or something else. Being
    rude, or arguing, or anything else that annoys it does not spend the
    joke - it is the rename specifically that triggers it.
    """
    if not name:
        return False
    if not is_his_machine(cfg):
        return False
    return not already_used()
