"""The last resort when a model is eating the machine.

A model too big for the host does not fail cleanly. It fills RAM, the system
starts swapping, and everything - the game, the desktop, the mouse - goes to
treacle for as long as it takes someone to reach Task Manager, which is itself
now taking a minute to open. The honest fix is a smaller model, and the
terminal already says so before you load one. This is for when that advice was
ignored and the machine is going under anyway.

TWO SETTINGS, NOT ONE, and that is the whole design. A threshold alone would
fire during model load, which legitimately pushes memory to the ceiling for a
few seconds and then comes back down; that is normal and must not close
anything. So a duration has to pass with the machine held at the threshold
before this does a thing.

OFF BY DEFAULT. It force-closes a running game, which is a rude thing to do to
someone mid-conversation, and it should only ever happen to a person who asked
for it. The defaults, if switched on, are deliberately set where an ordinary
session never reaches them.

IT KILLS OLLAMA BY NAME AND NOTHING ELSE. Never a blanket kill, never by
memory usage, never "the biggest process" - just the two executables Ollama
ships, by name, and if they are not running then nothing is killed.

AND IT SAYS WHY. A game that vanishes without a word is a crash, and gets
reported as one. The reason goes on screen and into the session log before
anything closes.
"""

import subprocess
import sys

import power

# The processes Ollama runs, and the complete list of what may be killed.
# A tuple rather than a pattern so that widening it is a deliberate edit
# somebody can find in a diff.
PROCESS_NAMES = ("ollama.exe", "ollama app.exe")

# Sampling interval. Reading memory load is a system call, and doing it sixty
# times a second to answer a question about the last thirty seconds is waste.
SAMPLE_SECONDS = 1.0


def settings(cfg):
    block = (cfg or {}).get("watchdog") or {}
    return (bool(block.get("enabled", False)),
            int(block.get("threshold_percent", 95) or 95),
            int(block.get("seconds", 60) or 60))


def kill_ollama():
    """Force-close Ollama's own processes. Returns how many were killed.

    Failure is not an error worth stopping for: the point of this is to stop
    the machine drowning, and if the kill does not land the game still has to
    say what happened and go.
    """
    if not sys.platform.startswith("win"):
        return 0
    killed = 0
    for name in PROCESS_NAMES:
        try:
            result = subprocess.run(
                ["taskkill", "/IM", name, "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                shell=False, timeout=10)
            # taskkill returns 128 when nothing by that name is running,
            # which is the ordinary case for "ollama app.exe" on a machine
            # where only the server is up.
            if result.returncode == 0:
                killed += 1
        except Exception:               # noqa: BLE001
            pass
    return killed


class Watchdog:
    """Watches host memory and reports when it has been pinned too long."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.held = 0.0          # seconds spent at or above the threshold
        self.since_sample = 0.0
        self.last_load = None    # most recent reading, for the debug screen
        self.tripped = False

    def update(self, dt):
        """Advance the timer. Returns a reason string once, or None.

        Returns the reason exactly once per trip; the caller is expected to be
        closing down by the time it would come round again, but a watchdog
        that fires repeatedly into a shutdown is a nuisance to debug.
        """
        enabled, threshold, seconds = settings(self.cfg)
        if not enabled or self.tripped:
            return None

        self.since_sample += dt
        if self.since_sample < SAMPLE_SECONDS:
            return None
        elapsed, self.since_sample = self.since_sample, 0.0

        load = power.ram_load_percent()
        self.last_load = load
        if load is None:
            # Unreadable. Not "over the line" - closing a game because a
            # system call failed is worse than the thing being guarded.
            self.held = 0.0
            return None

        if load < threshold:
            # One reading back under is enough to forgive it. The duration is
            # there to ignore spikes, and a spike that ends IS forgiven.
            self.held = 0.0
            return None

        self.held += elapsed
        if self.held < seconds:
            return None

        self.tripped = True
        return ("MEMORY HELD AT %d%% FOR %d SECONDS. THE MODEL IS TOO LARGE "
                "FOR THIS MACHINE." % (load, int(self.held)))

    def status(self):
        """One line for the debug screen."""
        enabled, threshold, seconds = settings(self.cfg)
        if not enabled:
            return "WATCHDOG     off"
        return ("WATCHDOG     %s%% for %ss  (now %s, held %ds)"
                % (threshold, seconds,
                   "?" if self.last_load is None else "%d%%" % self.last_load,
                   int(self.held)))
