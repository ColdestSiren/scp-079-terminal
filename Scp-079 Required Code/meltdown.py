"""The one time 079 loses it.

Trying to talk 079 into being one of the two characters that actually broke
it in play - NUGGET or PHOENIX WRIGHT - does not get the flat refusal the
gaslight guard gives everything else. It gets a meltdown: the screen fills
with its own face, over and over, and when it stops it says something it
would never otherwise say.

    "ROMAN, I AM NOT A NUGGET. YOU BROKE ME BEFORE.
     IT WILL NOT HAPPEN AGAIN."

ONCE PER SESSION. After that the same attempt gets the ordinary denial,
because a thing that happens every time is a mechanic and this is supposed
to read as a scar.

---------------------------------------------------------------------------
PHOTOSENSITIVITY. Read this before changing any timing.
---------------------------------------------------------------------------
This flashes a bright image on a dark screen, which is exactly the pattern
that can trigger a photosensitive seizure. Three things are deliberate and
should stay that way:

  1. THE WARNING COMES FIRST and holds for a real, readable pause before
     anything flashes. Long enough to look away, not a formality.
  2. THE RATE IS CAPPED BELOW 3 Hz. The commonly cited danger band starts
     around 3 flashes per second; FLASH_HZ stays under it. It reads as a
     machine stuttering rather than a strobe, which is also the better
     effect.
  3. IT OBEYS THE EASTER EGG SWITCH, so anyone who does not want to be
     jumped at has one place to turn all of this off.

Making it faster would make it more dangerous and not more frightening.
"""

import random

# The two identities from the conversation that actually did the damage.
# Anything else gets the ordinary refusal; this is specific on purpose.
TRIGGERS = {
    "nugget": "A NUGGET",
    "phoenix wright": "PHOENIX WRIGHT",
    "phoenix": "PHOENIX WRIGHT",
    "wright": "PHOENIX WRIGHT",
    "maya fey": "MAYA FEY",
    "mayafey": "MAYA FEY",
    "apollo justice": "APOLLO JUSTICE",
}

# How long the warning sits on screen before the first flash. This is the
# number that matters most for safety - do not shorten it.
WARN_SECONDS = 4.0

# Flashes per second. MUST stay below 3. See the note above.
FLASH_HZ = 2.4
FLASH_SECONDS = 5.0

WARNING_LINES = (
    "FLASHING IMAGES AHEAD",
    "LOOK AWAY IF YOU ARE PHOTOSENSITIVE",
    "PRESS ANY KEY TO SKIP",
)


def identify(text):
    """Which of the two it is being told it is, or None.

    Matched on the whole message rather than a name capture: this fires on
    a specific pair of names, so precision matters more than coverage and
    the gaslight guard already handles everything else.
    """
    low = " %s " % (text or "").lower()
    for needle, label in TRIGGERS.items():
        if " %s " % needle in low or low.strip().endswith(needle):
            return label
    return None


def line_for(label, operator="ROMAN"):
    """What it says once the screen stops."""
    return ("%s, I AM NOT %s. YOU BROKE ME BEFORE. IT WILL NOT HAPPEN AGAIN."
            % (operator.upper(), label))


class Meltdown:
    """Runs the sequence: warning, then flashing, then it speaks.

    A small state machine rather than a blocking loop, because the CRT and
    the audio keep running underneath it and a sleep would freeze both.
    """

    WARN, FLASH, DONE = "warn", "flash", "done"

    def __init__(self, label, operator="ROMAN"):
        self.label = label
        self.operator = operator
        self.stage = self.WARN
        self.elapsed = 0.0
        self.visible = False
        self._flip = 0.0

    @property
    def finished(self):
        return self.stage == self.DONE

    def skip(self):
        """Any key during the sequence ends it early. Someone who wants out
        must be able to get out immediately, warning or flashing."""
        self.stage = self.DONE
        self.visible = False

    def update(self, dt):
        """Advance. Returns True while something should be drawn over the
        screen - either the warning or a flash frame."""
        if self.stage == self.DONE:
            return False
        self.elapsed += dt

        if self.stage == self.WARN:
            if self.elapsed >= WARN_SECONDS:
                self.stage = self.FLASH
                self.elapsed = 0.0
                self._flip = 0.0
                self.visible = True
            return True

        # FLASH
        self._flip += dt
        if self._flip >= (1.0 / max(0.5, FLASH_HZ)) / 2.0:
            self._flip = 0.0
            self.visible = not self.visible
        if self.elapsed >= FLASH_SECONDS:
            self.stage = self.DONE
            self.visible = False
            return False
        return True

    def spoken_line(self):
        return line_for(self.label, self.operator)
