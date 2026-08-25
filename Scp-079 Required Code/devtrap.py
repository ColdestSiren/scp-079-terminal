"""The developer shortcut, and who counts as the developer.

Ctrl+F12 clears a lockout. It exists because there is no input box on the
refusal screen, so /unlock cannot be typed exactly when it is most needed,
and the lockout screen now names it to whoever hits their first timeout.

IT WORKS FOR EVERYONE, and that is the decision rather than an oversight.
Waiting out a timeout is not the game. There WAS a trap here - the shortcut
had been told to a friend, so on anyone else's machine it sprang instead of
working: a taunt, 079's face held on screen, and an hour that could not be
skipped. It is gone. A way to avoid a wait is meant for whoever is waiting,
and a game that advertises a shortcut and then punishes you for taking it is
just lying to you.

WHAT THE OWNER CHECK IS STILL FOR is everything the shortcut is not: /debug,
which sets hostility to whatever you like and fills the disk, and the code
locked save slots. Being told how to skip a wait should not come with either.
It is the Windows account name, because that is the only identity a local
game can check without inventing an account system - not security, and it
does not need to be.
"""

import getpass

import pygame

# The shortcut itself, in one place, because it is now something the game
# TELLS you rather than something you had to find. A hint that names the
# wrong keys is worse than no hint, and two copies of "CTRL+F12" - one in the
# handler, one in the text - is exactly how that happens.
#
# The label is derived from the binding rather than typed out beside it, so
# rebinding the key rewrites every place it is shown. pygame.key.name needs
# the module initialised, hence a function rather than a constant.
BYPASS_KEY = pygame.K_F12
BYPASS_MOD = pygame.KMOD_CTRL


def bypass_label():
    return "CTRL+" + pygame.key.name(BYPASS_KEY).upper()


def pressed_bypass(event):
    """Is this key event the escape hatch?"""
    return event.key == BYPASS_KEY and bool(event.mod & BYPASS_MOD)


# The account that owns /debug and its own save slots. Overridable in config
# so the check can be exercised from another machine.
DEFAULT_OWNER = "colde"


def current_user():
    try:
        return (getpass.getuser() or "").strip().lower()
    except Exception:               # noqa: BLE001
        return ""


def is_owner(cfg=None):
    """Is the person at this keyboard the one the shortcut belongs to?"""
    allowed = {DEFAULT_OWNER}
    extra = ((cfg or {}).get("devtrap") or {}).get("owners") or []
    for name in extra:
        if str(name).strip():
            allowed.add(str(name).strip().lower())
    return current_user() in allowed
