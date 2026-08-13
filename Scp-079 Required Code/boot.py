"""Boot diagnostics: the step vocabulary and the runner that plays it.

The CONTENT of a boot sequence belongs to a personality (see
personalities/), not here - this module only knows how to type a label,
fill in dotted leaders, pop a status bracket, and pause. That split is what
lets a second personality ship its own boot without touching the engine.
"""

import random

LINE, LEADER, PAUSE, BLANK, HOLD = "line", "leader", "pause", "blank", "hold"


# --- step builders ---------------------------------------------------------
def line(text, color="text", cps=90):
    return {"kind": LINE, "text": text, "color": color, "cps": cps}


def leader(label, status="OK", width=46, color="text", status_color="bright",
           dot_delay=0.055, cps=110):
    """'CHECKING MEMORY........OK' - the label types, then the dots fill in
    one at a time, then the status appears."""
    dots = max(3, width - len(label))
    return {
        "kind": LEADER,
        "label": label,
        "dots": dots,
        "status": status,
        "color": color,
        "status_color": status_color,
        "dot_delay": dot_delay,
        "cps": cps,
    }


def hold(label, ok="ONLINE", fail_status="FAIL", waiting="  LOADING", max_dots=30,
         min_dots=38, dot_delay=0.14, cps=110, color="dim", status_color="text",
         fail_color="alarm", hold_id="link"):
    """A leader that waits for the outside world before it resolves.

    The boot stalls here, filling in dots, until release() or fail() is
    called - which is how a backend problem surfaces as a failed diagnostic
    line inside the boot instead of an error screen bolted on before it.
    """
    return {
        "kind": HOLD,
        # which wait this is, so the app can tell "waiting for the model" from
        # "waiting for the operator to type a code"
        "id": hold_id,
        "label": label,
        "status": ok,
        "fail_status": fail_status,
        "waiting": waiting,
        "max_dots": max_dots,
        "min_dots": min_dots,
        "dot_delay": dot_delay,
        "cps": cps,
        "color": color,
        "status_color": status_color,
        "fail_color": fail_color,
    }


def pause(seconds):
    return {"kind": PAUSE, "seconds": seconds}


def blank():
    return {"kind": BLANK}


class BootRunner:
    """Walks a boot script, writing into a Console, without ever blocking.

    Timing is randomized two ways so no two startups are identical: one
    `run_scale` for the whole boot, plus per-step jitter on top of it.
    """

    STATUS_DELAY = 0.10

    def __init__(self, script, console, theme, speed=1.0):
        self.script = list(script)
        self.console = console
        self.theme = theme
        self.speed = max(0.05, float(speed))
        self.run_scale = random.uniform(0.85, 1.25)
        self.i = 0
        self.step = None
        self.phase = None
        self.finished = False
        self.failed = False
        self.holding = False
        self.holding_id = None
        self._release = None
        self.wait = 0.0
        self.dots_done = 0
        self._next_step()

    def release(self):
        """Backend is healthy - let the boot finish normally."""
        if self.holding:
            self._release = (True, None)

    def fail(self, steps):
        """Backend is not healthy - stamp the held line FAIL and play `steps`
        instead of the rest of the script."""
        if self.holding:
            self._release = (False, list(steps or []))

    def _color(self, key):
        if isinstance(key, tuple):
            return key
        return self.theme.get(key, self.theme["text"])

    def _jitter(self, base):
        return max(0.005, base * self.run_scale * random.uniform(0.75, 1.35) / self.speed)

    def _next_step(self):
        if self.i >= len(self.script):
            self.step = None
            self.finished = True
            return
        self.step = self.script[self.i]
        self.i += 1
        kind = self.step["kind"]
        self.dots_done = 0

        if kind == BLANK:
            self.console.blank()
            self._next_step()
            return
        if kind == PAUSE:
            self.phase = "wait"
            self.wait = self._jitter(self.step["seconds"])
            return
        if kind == LINE:
            self.phase = "type"
            self.console.start_stream(self._color(self.step["color"]),
                                      cps=self.step["cps"] * self.speed)
            self.console.feed(self.step["text"])
            self.console.finish_stream()
            return
        if kind in (LEADER, HOLD):
            self.phase = "label"
            self.holding = (kind == HOLD)
            # which wait this is, so the app can tell "loading the model" from
            # "waiting for the operator to type a code"
            self.holding_id = self.step.get("id") if kind == HOLD else None
            self.console.start_stream(self._color(self.step["color"]),
                                      cps=self.step["cps"] * self.speed)
            self.console.feed(self.step["label"])
            return

    def update(self, dt):
        """Advance the script. The Console's own update() is driven by the
        main loop, so this only decides WHEN to feed it more text."""
        if self.finished or self.step is None:
            return
        step = self.step
        kind = step["kind"]

        if kind == PAUSE:
            self.wait -= dt
            if self.wait <= 0.0:
                self._next_step()
            return

        if kind == LINE:
            # committed once the console has typed everything and closed it
            if not self.console.has_live_line:
                self._next_step()
            return

        if kind == HOLD:
            if self.phase == "label":
                if self.console.live_caught_up:
                    self.phase = "dots"
                    # Say what the wait IS. Loading a 20-30GB model takes tens
                    # of seconds and a line of silent dots reads as a hang.
                    # The live text is discarded on commit, which rewrites the
                    # row as "<label>....ONLINE", so this only ever shows while
                    # the wait is actually happening.
                    if step.get("waiting"):
                        self.console.feed(step["waiting"])
                    self.wait = self._jitter(step["dot_delay"])
                return
            if self._release is not None:
                ok, failure_steps = self._release
                self._release = None
                self.holding = False
                self.console.cancel_stream()
                # A failure can come back before any dots were drawn, so pad
                # out to the same column the other leader lines resolve at -
                # otherwise the status runs straight into the label.
                dots = max(self.dots_done, step["min_dots"] - len(step["label"]))
                self.console.write_segments([
                    (self._color(step["color"]), step["label"] + "." * dots),
                    (self._color(step["status_color"] if ok else step["fail_color"]),
                     step["status"] if ok else step["fail_status"]),
                ])
                if not ok:
                    # drop the rest of the normal boot, play the failure tail
                    self.script = self.script[: self.i] + list(failure_steps or [])
                    self.failed = True
                self._next_step()
                return
            self.wait -= dt
            if self.wait <= 0.0 and self.dots_done < step["max_dots"]:
                self.console.feed(".")
                self.dots_done += 1
                self.wait = self._jitter(step["dot_delay"])
            return

        if kind == LEADER:
            if self.phase == "label":
                if self.console.live_caught_up:
                    self.phase = "dots"
                    self.wait = self._jitter(self.step["dot_delay"])
                return
            if self.phase == "dots":
                self.wait -= dt
                if self.wait > 0.0:
                    return
                # dots are fed one at a time so they fill in visibly rather
                # than typing at the label's speed
                self.console.feed(".")
                self.dots_done += 1
                if self.dots_done >= self.step["dots"]:
                    self.phase = "status"
                    self.wait = self._jitter(self.STATUS_DELAY)
                else:
                    self.wait = self._jitter(self.step["dot_delay"])
                return
            if self.phase == "status":
                self.wait -= dt
                if self.wait > 0.0:
                    return
                # the live line is already fully revealed, so swapping it for
                # the two-tone committed row is visually seamless
                self.console.cancel_stream()
                self.console.write_segments([
                    (self._color(self.step["color"]),
                     self.step["label"] + "." * self.step["dots"]),
                    (self._color(self.step["status_color"]), self.step["status"]),
                ])
                self._next_step()
                return

    def skip(self):
        """Fast-forward to the end (press any key during boot).

        Stops at a hold - you cannot skip past something the boot is
        genuinely still waiting on.
        """
        guard = 0
        # A hold that already has a release queued is not really waiting - keep
        # going so the queued result gets committed rather than stranding the
        # held line half-drawn.
        while not self.finished and guard < 200000:
            if self.holding and self._release is None:
                break
            self.console.update(1.0)
            self.update(1.0)
            guard += 1
        self.console.flush_stream()
