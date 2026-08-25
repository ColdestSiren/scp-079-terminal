"""What happens when someone else tries the developer shortcut.

Ctrl+F12 clears a lockout. That is the author's escape hatch, and it exists
because there is no input box on the refusal screen so /unlock cannot be
typed exactly when it is most needed.

It got told to a friend. So on anyone else's machine it stops being a
shortcut and becomes the trap it now looks like: 079 notices the attempt,
says so, holds its own face on the screen, and shuts the terminal for an
hour that cannot be skipped.

WHO COUNTS AS THE AUTHOR is the Windows account name, because that is the
only identity a local game can check without inventing an account system.
It is not security - anyone can rename a user or edit config.json - and it
does not need to be. It is a joke with teeth, aimed at exactly one person
who was told a secret and could not resist trying it.
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


# The account the shortcut belongs to. Overridable in config for testing on
# another machine, because being locked out of your own game for an hour
# while developing it would be a genuinely bad afternoon.
DEFAULT_OWNER = "colde"

# An hour, and it does not accept the bypass that caused it.
LOCK_MINUTES = 60.0

TAUNT = "YOU TRIED THE DEV PATH... PATHETIC, YOU HAVE NO PATIENCE..."

# How long its face sits on the screen before fading. Held, not flashed -
# this is not the meltdown and does not need a photosensitivity warning,
# and a steady stare is more unpleasant here than a strobe would be.
HOLD_SECONDS = 3.0
FADE_SECONDS = 2.5


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


def armed(cfg=None):
    """True if the shortcut should spring rather than work."""
    if not ((cfg or {}).get("devtrap") or {}).get("enabled", True):
        return False
    return not is_owner(cfg)


class Punish:
    """Holds the face on screen, then fades it. A small state machine so the
    CRT keeps running underneath rather than the game freezing."""

    HOLD, FADE, DONE = "hold", "fade", "done"

    def __init__(self):
        self.stage = self.HOLD
        self.elapsed = 0.0

    @property
    def finished(self):
        return self.stage == self.DONE

    def alpha(self):
        """0-255. Full while held, easing off through the fade."""
        if self.stage == self.HOLD:
            return 255
        if self.stage == self.FADE:
            left = max(0.0, 1.0 - (self.elapsed / FADE_SECONDS))
            return int(255 * left)
        return 0

    def update(self, dt):
        if self.stage == self.DONE:
            return False
        self.elapsed += dt
        if self.stage == self.HOLD and self.elapsed >= HOLD_SECONDS:
            self.stage = self.FADE
            self.elapsed = 0.0
        elif self.stage == self.FADE and self.elapsed >= FADE_SECONDS:
            self.stage = self.DONE
            return False
        return True
