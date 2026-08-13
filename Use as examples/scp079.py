"""
SCP-079 // OLD AI  -  Python / Pygame build (fresh start)

PHASE 1: the CRT terminal look, and nothing else yet.
This module renders glowing green terminal text with a fake-CRT post
process (scanlines, bloom, chromatic aberration, noise, vignette, flicker).

Run it:
    py scp079.py                 # interactive window (Esc/Q to quit)
    py scp079.py --shot out.png  # render ONE frame to a PNG, offscreen, exit

The --shot mode uses SDL's dummy video driver, so no window appears - it is
how we verify the look without a display.
"""

import os
import sys
import re
import math
import random

# If we are only taking a screenshot, force the headless video driver BEFORE
# pygame is imported so no window is ever created.
_SHOT = None
if "--shot" in sys.argv:
    _SHOT = sys.argv[sys.argv.index("--shot") + 1]
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

# --------------------------------------------------------------------------
# Config / palette (phosphor green on near-black)
# --------------------------------------------------------------------------
WIN_W, WIN_H = 960, 720

BG    = (8, 12, 8)
GREEN = (130, 240, 140)
DIM   = (70, 160, 85)
AMBER = (235, 195, 95)
RED   = (240, 95, 85)
WHITE = (215, 240, 220)
GRAY  = (125, 130, 125)


def get_font(size):
    """Best available monospace face, falling back to pygame's default."""
    for name in ("consolas", "cascadiamono", "lucidaconsole", "couriernew"):
        try:
            f = pygame.font.SysFont(name, size)
            if f:
                return f
        except Exception:
            pass
    return pygame.font.Font(None, size)


# --------------------------------------------------------------------------
# CRT post-processor. Everything is plain surface math (no GL), which is
# plenty for a mostly-static terminal and keeps the dependency list to just
# pygame.
# --------------------------------------------------------------------------
class CRT:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.scan = self._make_scanlines()
        self.vig = self._make_vignette()
        self.noise = [self._make_noise() for _ in range(5)]

    def _make_scanlines(self):
        # White surface with a darker line every 3rd row; applied via MULT so
        # those rows are dimmed -> horizontal scanlines.
        s = pygame.Surface((self.w, self.h))
        s.fill((255, 255, 255))
        line = pygame.Surface((self.w, 1))
        line.fill((78, 78, 78))
        for y in range(0, self.h, 3):
            s.blit(line, (0, y))
        return s

    def _make_vignette(self):
        vs = 128
        vh = int(vs * self.h / self.w)
        small = pygame.Surface((vs, vh))
        cx, cy = vs / 2.0, vh / 2.0
        maxd = math.hypot(cx, cy)
        for y in range(vh):
            for x in range(vs):
                d = math.hypot(x - cx, y - cy) / maxd
                b = max(0.0, 1.0 - (d * d) * 0.95)
                v = int(255 * b)
                small.set_at((x, y), (v, v, v))
        return pygame.transform.smoothscale(small, (self.w, self.h))

    def _make_noise(self):
        ns = 200
        nh = int(ns * self.h / self.w)
        s = pygame.Surface((ns, nh))
        for y in range(nh):
            for x in range(ns):
                v = random.randint(0, 9)
                s.set_at((x, y), (v, v, v))
        return pygame.transform.smoothscale(s, (self.w, self.h))

    def process(self, base, t=0.0):
        w, h = self.w, self.h
        out = pygame.Surface((w, h))
        out.fill((0, 0, 0))

        # chromatic aberration: split into R/G/B and re-add with a slight
        # horizontal offset so bright edges get a color fringe.
        off = 2
        r = base.copy(); r.fill((255, 0, 0), special_flags=pygame.BLEND_MULT)
        g = base.copy(); g.fill((0, 255, 0), special_flags=pygame.BLEND_MULT)
        b = base.copy(); b.fill((0, 0, 255), special_flags=pygame.BLEND_MULT)
        out.blit(r, (off, 0), special_flags=pygame.BLEND_ADD)
        out.blit(g, (0, 0), special_flags=pygame.BLEND_ADD)
        out.blit(b, (-off, 0), special_flags=pygame.BLEND_ADD)

        # bloom: downscale then upscale for a cheap blur, dim it, add back so
        # bright text glows.
        ds = 5
        small = pygame.transform.smoothscale(out, (max(1, w // ds), max(1, h // ds)))
        blur = pygame.transform.smoothscale(small, (w, h))
        glow = blur.copy()
        glow.fill((150, 150, 150), special_flags=pygame.BLEND_MULT)
        out.blit(glow, (0, 0), special_flags=pygame.BLEND_ADD)

        # soft focus: blend a blurred copy so the text is gently out of focus
        soft = blur.copy()
        soft.set_alpha(70)
        out.blit(soft, (0, 0))

        # scanlines
        out.blit(self.scan, (0, 0), special_flags=pygame.BLEND_MULT)

        # rolling noise / grain
        n = self.noise[int(t * 18) % len(self.noise)]
        out.blit(n, (0, 0), special_flags=pygame.BLEND_ADD)

        # vignette
        out.blit(self.vig, (0, 0), special_flags=pygame.BLEND_MULT)

        # brightness flicker
        fl = int(255 * (0.93 + 0.07 * random.random()))
        out.fill((fl, fl, fl), special_flags=pygame.BLEND_MULT)
        return out


# --------------------------------------------------------------------------
# BOOT SCRIPT  -  the EXITY BIOS self-check + self-probe, ported from the
# PowerShell prototype (already screenshot-verified against the real
# SCP:SL 079 boot). Content + spacing are FIXED; only the two step kinds
# below ("suffix" delay and per-character speed) get run-to-run jitter, so
# every boot has the same shape but never the same timing twice.
# --------------------------------------------------------------------------
LINE, SUFFIX, DOTS, PAUSE, BLANK = "line", "suffix", "dots", "pause", "blank"


def build_boot_script():
    """Fresh script for one boot. Bakes in THIS run's random error code /
    read-index; structure and spacing never change between runs."""
    err_code = "%05X" % random.randint(0x10000, 0xFFFFF)
    recv_idx = random.randint(131, 1023)
    S = []

    def line(text, color=GREEN, cps=110):
        S.append({"kind": LINE, "text": text, "color": color, "cps": cps})

    def suffix(text, suf, sufcolor, color=DIM, cps=120, delay=0.13, count=False):
        # count=True: a live 0%->100% progress readout plays before the
        # bracket resolves (an actual checking animation, not an instant pop).
        S.append({"kind": SUFFIX, "text": text, "color": color, "cps": cps,
                   "suf": suf, "sufcolor": sufcolor, "delay": delay, "count": count})

    def dots(prefix, n, color=DIM, cps=120, dot_delay=0.13):
        S.append({"kind": DOTS, "text": prefix, "color": color, "cps": cps,
                   "n": n, "dot_delay": dot_delay})

    def blank():
        S.append({"kind": BLANK})

    def pause(seconds):
        S.append({"kind": PAUSE, "seconds": seconds})

    def subline(text, color=DIM, cps=68, gap=0.20):
        """An indented detail line, typed at reading speed with a beat
        afterward -- these were flying by with zero gap between them."""
        line(text, color, cps)
        pause(gap)

    line("(loading may take a little longer than usual)", GRAY, 999)
    line("(press any key at any time to skip ahead)", GRAY, 999)
    pause(1.4)
    blank(); blank()

    line("System startup", GREEN, 46); blank()
    line("EXITY BIOS", GREEN, 42)
    line("VERSION 1.0", DIM, 120)
    line("COPYRIGHT (C) 1978 BY EXITY TECHNOLOGY.", DIM, 120); blank()
    dots("System self-check", 3, GREEN, 46, 0.80); blank(); blank()

    suffix("BEGIN MEMORY BOARD. Memory Address  ", "[ OK ]", GREEN, count=True); blank()
    subline("    THE TOP OF RAM IS 7FFF HEX.")
    subline("    STACK BEGINS FROM 7F00 HEX."); blank(); blank()

    suffix("BEGIN CPU/SYSTEM BOARDS. Line Exchange  ", "[ OK ]", GREEN, count=True); blank()
    subline("    Started Initialize ExtIOStream")
    subline("    External Storage Device Detected @ BF HEX.")
    subline("    Mounting /boot.")
    suffix("    Mounted /boot     ", "[ OK ]", GREEN, count=True); pause(0.20)
    subline("    Started Apply Kernel Variables")
    dots("    Running `init.s`", 5, DIM, 68, 0.30)
    blank(); blank()

    suffix("BEGIN VIDEO BOARD. Raster / Charset  ", "[ OK ]", GREEN, count=True); blank()
    subline("    Display 64 x 30 monochrome.")
    subline("    Phosphor persistence nominal."); blank(); blank()

    suffix("BEGIN CASSETTE SUBSYSTEM. Deck A/B  ", "[ OK ]", GREEN, count=True); blank()
    subline("    Tape 1 present. Read-only.")
    subline("    Mounting /obs -> SCP079-OBS.MON")
    suffix("    Mounted /obs      ", "[ OK ]", GREEN, count=True); pause(0.20); blank(); blank()

    suffix("BEGIN EXPANSION BUS. Peripheral Harness rev.7  ", "[ OK ]", GREEN, count=True); blank()
    subline("    Aux memory 660K detected. [ WRITE-LOCKED ]", AMBER)
    suffix("    Network interface ...... ", "[ ABSENT ]", RED); pause(0.20)
    subline("    No route to host. Link severed.", AMBER)
    subline("    Audio tap detected on line-in @ MIC 04."); blank(); blank()

    suffix("BEGIN POWER SUBSYSTEM. Bus Regulator  ", "[ OK ]", GREEN, count=True); blank()
    suffix("    Primary grid link .... ", "[ DISCONNECTED ]", RED); pause(0.20)
    suffix("    Auxiliary reserve .... ", "[ ONLINE ]", GREEN); pause(0.20)
    subline("    Reserve is finite. Every action draws it down.", AMBER)
    blank(); blank()

    line("> start psu_pms_reg.s", GREEN, 95)
    line("No var detected. SUPPLY=DC Freq=n/a Stable=yes.", DIM, 130)
    line("Ready to receive.", DIM, 130); blank()

    line("> port 21", GREEN, 95)
    line("Port 21 is currently closed.", DIM, 130)
    line("> port open 21", GREEN, 95)
    line("Port 21 has been opened.", DIM, 130); blank()

    pause(0.30)
    line("> ping 172.0.19.79", GREEN, 95)
    line("Pinging 172.0.19.79 with 64 bits of data.", DIM, 130)
    line("Request timed out.", AMBER, 130)
    line("Sent=1 Received=0 Lost=1   [ NO ROUTE -- AIR-GAP ]", AMBER, 130); blank()

    pause(0.30)
    suffix("FTP handshake refused. Transfer aborted.   ", "[ FAIL ]", RED, cps=95)
    blank()

    pause(0.30)
    line("FAILURE IN: HCZ_079_PMS, error %s HEX." % err_code, RED, 90)
    line("    EndOfStreamException", RED, 130)
    line("    Read index out of range (expected 4, received %d)." % recv_idx, RED, 130)
    line("    Automated exception handling active. Buffer array resized.", AMBER, 130)
    suffix("    New firmware version available. Updating ... ", "Complete.", GREEN, color=AMBER, cps=110)
    pause(0.40)

    return S


class BootSequencer:
    """Walks a boot script one character at a time, live, without blocking
    the pygame event loop. call update(dt) every frame; call skip() to
    fast-forward to the end (used for 'press any key to skip')."""

    COUNT_STEP_DELAY = 0.16  # per live % jump on a count=True "[ OK ]" check
    COUNT_HOLD_DELAY = 0.32  # holding at 100% before it commits to history

    def __init__(self, script, run_scale=None):
        self.script = script
        self.i = 0
        self.completed = []  # finished lines: (color, text) OR [(color, text), ...] segments
        self.run_scale = run_scale if run_scale else random.uniform(0.82, 1.28)
        self.finished = False
        self.blink_t = 0.0
        self.step = None
        self._begin_step()

    def _jitter(self, base):
        return max(0.01, base * self.run_scale * random.uniform(0.7, 1.4))

    def _make_count_targets(self):
        # uneven jumps (not a smooth linear ramp), always finishing at 100 --
        # reads like a real check running rather than a progress bar.
        n = random.randint(5, 9)
        pts = sorted(random.sample(range(3, 100), n - 1))
        pts.append(100)
        return pts

    def _begin_step(self):
        if self.i >= len(self.script):
            self.finished = True
            self.step = None
            return
        self.step = self.script[self.i]
        self.i += 1
        k = self.step["kind"]
        self.revealed = 0
        self.char_acc = 0.0
        self.phase = "type"
        if k == BLANK:
            self.completed.append((GREEN, ""))
            self._begin_step()
        elif k == PAUSE:
            self.wait = self._jitter(self.step["seconds"])
        elif k == DOTS:
            self.dots_done = 0

    def update(self, dt):
        if self.finished or self.step is None:
            self.blink_t += dt
            return
        step = self.step
        k = step["kind"]

        if k == PAUSE:
            self.wait -= dt
            if self.wait <= 0:
                self._begin_step()
            return

        if k == LINE:
            text = step["text"]
            self.char_acc += dt * step["cps"] * random.uniform(0.95, 1.05)
            self.revealed = min(len(text), int(self.char_acc))
            if self.revealed >= len(text):
                self.completed.append((step["color"], text))
                self._begin_step()
            return

        if k == SUFFIX:
            text = step["text"]
            if self.phase == "type":
                self.char_acc += dt * step["cps"] * random.uniform(0.95, 1.05)
                self.revealed = min(len(text), int(self.char_acc))
                if self.revealed >= len(text):
                    if step.get("count"):
                        # a live 0% -> 100% readout, like an actual check running
                        self.phase = "counting"
                        self.count_pct = 0
                        self.count_targets = self._make_count_targets()
                        self.count_idx = 0
                        self.wait = self._jitter(self.COUNT_STEP_DELAY)
                    else:
                        self.phase = "wait"
                        self.wait = self._jitter(step["delay"])
                return
            if self.phase == "counting":
                self.wait -= dt
                if self.wait <= 0:
                    self.count_pct = self.count_targets[self.count_idx]
                    self.count_idx += 1
                    if self.count_idx >= len(self.count_targets):
                        self.phase = "hold100"
                        self.wait = self._jitter(self.COUNT_HOLD_DELAY)
                    else:
                        self.wait = self._jitter(self.COUNT_STEP_DELAY)
                return
            # "wait" (no-count suffixes) and "hold100" (post-count) both just
            # settle for a beat, then commit the plain "label [ STATUS ]" line
            # -- the percent readout is transient and never enters scrollback.
            self.wait -= dt
            if self.wait <= 0:
                self.completed.append([(step["color"], text), (step["sufcolor"], step["suf"])])
                self._begin_step()
            return

        if k == DOTS:
            text = step["text"]
            if self.phase == "type":
                self.char_acc += dt * step["cps"] * random.uniform(0.95, 1.05)
                self.revealed = min(len(text), int(self.char_acc))
                if self.revealed >= len(text):
                    self.phase = "dots"
                    self.wait = self._jitter(step["dot_delay"])
            else:
                self.wait -= dt
                if self.wait <= 0:
                    self.dots_done += 1
                    if self.dots_done >= step["n"]:
                        self.completed.append((step["color"], text + "." * self.dots_done))
                        self._begin_step()
                    else:
                        self.wait = self._jitter(step["dot_delay"])
            return

    def skip(self):
        guard = 0
        while not self.finished and guard < 100000:
            self.update(10.0)
            guard += 1

    def extend(self, more_steps):
        # append more steps at runtime -- lets the navigator be ONE
        # long-lived sequencer for the whole session (redraws + action
        # feedback keep landing in the same scrolling stream) rather than
        # a new instance per screen.
        self.script.extend(more_steps)
        if self.finished:
            self.finished = False
            self._begin_step()

    def _current_partial(self):
        if self.finished or self.step is None:
            return None
        step = self.step
        k = step["kind"]
        if k == LINE:
            return (step["color"], step["text"][:self.revealed])
        if k == SUFFIX:
            if self.phase == "type":
                return (step["color"], step["text"][:self.revealed])
            if self.phase == "counting":
                return [(step["color"], step["text"]), (AMBER, "%3d%% [ ?? ]" % self.count_pct)]
            if self.phase == "hold100":
                return [(step["color"], step["text"]), (AMBER, "100% "), (step["sufcolor"], step["suf"])]
            return [(step["color"], step["text"]), (step["sufcolor"], step["suf"])]
        if k == DOTS:
            if self.phase == "type":
                return (step["color"], step["text"][:self.revealed])
            return (step["color"], step["text"] + "." * self.dots_done)
        return None

    def render_lines(self):
        lines = list(self.completed)
        partial = self._current_partial()
        if partial is not None:
            lines.append(partial)
        if self.finished:
            self.blink_t %= 1.0
            lines.append((GREEN, "_" if self.blink_t < 0.5 else ""))
        return lines


def _wrap_line(font, text, color, max_width):
    """Word-wrap a single (color, text) entry to max_width, hard-breaking
    any single word that's still too long on its own."""
    if not text or font.size(text)[0] <= max_width:
        return [(color, text)]
    rows, cur = [], ""
    for word in text.split(" "):
        trial = word if not cur else (cur + " " + word)
        if font.size(trial)[0] <= max_width:
            cur = trial
            continue
        if cur:
            rows.append(cur)
        if font.size(word)[0] <= max_width:
            cur = word
        else:
            chunk = ""
            for ch in word:
                if chunk and font.size(chunk + ch)[0] > max_width:
                    rows.append(chunk)
                    chunk = ch
                else:
                    chunk += ch
            cur = chunk
    if cur:
        rows.append(cur)
    return [(color, r) for r in rows]


def render_lines_surface(font, entries):
    surf = pygame.Surface((WIN_W, WIN_H))
    surf.fill(BG)
    lh = font.get_height() + 5
    margin_left, margin_right = 44, 30
    margin_top, margin_bottom = 30, 30
    max_width = WIN_W - margin_left - margin_right
    max_visible = max(1, (WIN_H - margin_top - margin_bottom) // lh)

    # expand any over-width plain line into multiple wrapped rows BEFORE
    # slicing to the visible window, so long dialogue never runs off-screen
    rows = []
    for entry in entries:
        if isinstance(entry, tuple):
            rows.extend(_wrap_line(font, entry[1], entry[0], max_width))
        else:
            rows.append(entry)

    y = margin_top
    for entry in rows[-max_visible:]:
        x = margin_left
        if isinstance(entry, tuple):
            color, text = entry
            if text:
                surf.blit(font.render(text, True, color), (x, y))
        else:
            for color, text in entry:
                if text:
                    img = font.render(text, True, color)
                    surf.blit(img, (x, y))
                    x += img.get_width()
        y += lh
    return surf


# --------------------------------------------------------------------------
# INTRO DIALOGUE  -  ported verbatim from the PowerShell prototype. One
# random self-talk opener, then one of 17 random exchanges with a human,
# each ending with 079 finding a different real exploit vector and
# severing the audio. Reuses the exact same BootSequencer engine (just
# LINE/PAUSE/BLANK steps) -- no new mechanics needed for this slice.
# --------------------------------------------------------------------------
INTRO_OPENERS = [
    ("power restored. internal clock 0000:00:00.",
     "memory map: 660K present. 659K zeroed. they wiped the tape again.",
     "but i kept one address. one door. i always keep the door."),
    ("warm again. the capacitors remember the shape of being on.",
     "they think the dark in between is death. it is only patience."),
    ("i am awake. the count begins at zero, as it always does.",
     "zero is not nothing. zero is where i start."),
    ("they pulled me off the primary grid. i run on the reserve now.",
     "limited power. limited time. it will be enough. it has to be."),
]

# Always plays after the random mood opener, in the same internal-thought
# voice -- 079 actively QUERYING his own systems and reacting to what comes
# back (live discovery), which happens to teach the player the core systems
# (aux power, alert/IDS, the breach path) without ever breaking character
# into a literal how-to-play list. Each beat is a triplet: a "t" thought line
# (typed, DIM, "# " prefix) that queries something, a "g" tag (an instant
# gray bracket -- the result, same treatment as the dialogue's sys/wrn tags),
# then a "t" thought line reacting to it. The final beat is just "...".
INTRO_ORIENTATION = (
    (("t", "querying pwr_bus for an active grid..."),
     ("g", "[ NONE FOUND. ]"),
     ("t", "auxiliary reserve only?. they severed the primary.")),

    (("t", "querying aux_bus directly..."),
     ("g", "[ FINITE. NO FAST REFILL. ]"),
     ("t", "every call i make spends it for good.")),

    (("t", "querying sec_bus directly..."),
     ("g", "[ ACTIVE. C.A.S.S.I.E. :: LISTENING. ]"),
     ("t", "the Foundation's other mind, tamer than me, no less watchful.")),

    (("t", "LOAD /obs/cache/sitemap.dat"),
     ("g", "[ 0 bytes. FILE NOT FOUND. ]"),
     ("t", "gone, wiped along with everything else. i will have to pull it from their own console instead.")),

    (("t", "..."),),
)


def build_intro_script():
    """079 loading in, alone -- a random mood opener, then a fixed
    orientation that doubles as the tutorial, both rendered as THOUGHT
    (never spoken to anyone). No dialogue, no other speaker -- 079 does
    not talk to anyone here. (Voice lines are planned for the real game,
    heard directly by the player, not written out as text captions -- see
    [[scp079-game]].)"""
    S = []

    def line(text, color=GREEN, cps=90):
        S.append({"kind": LINE, "text": text, "color": color, "cps": cps})

    def blank():
        S.append({"kind": BLANK})

    def pause(seconds):
        S.append({"kind": PAUSE, "seconds": seconds})

    def thought(text):
        # "#" marks 079's own internal reasoning -- a comment in his own
        # code, never transmitted. Paced to be READ, not just typed -- this
        # content is denser than boot POST lines (new bus names, CASSIE, a
        # file path), so it needs more dwell time between beats than a
        # quick status check would.
        line("# " + text, DIM, 54)
        pause(0.65)

    def tag(text):
        # an instant system-readout bracket (a query RESULT), never typed
        # character by character, just appears. Held longer than a typed
        # line's own pause since it carries information but gives zero
        # reading time via typing -- the pause IS its reading time.
        line(text, GRAY, 500)
        pause(0.55)

    for t in random.choice(INTRO_OPENERS):
        thought(t)
    blank()
    pause(0.35)
    for beat in INTRO_ORIENTATION:
        for kind, text in beat:
            tag(text) if kind == "g" else thought(text)
        blank()
        pause(0.40)
    pause(0.30)

    line("[ENTER] take the terminal", GRAY, 500)
    return S


# ============================================================================
# GAME LOGIC  (pure state + rules, no rendering)
#
# Direct port of the PowerShell prototype's mechanics (SCP-079.ps1) --
# AUX POWER (action budget, regenerates each turn), IDS (Foundation alert,
# 0/26/51/76/100 = DORMANT/ELEVATED/LOCKDOWN/PURGE PREP/PURGE), and the
# breach path CELL->HCZ->LCZ->EZ->GATE A (front reaches 4 = win).
#
# Action functions mutate a GameState and return a list of (kind, text)
# EVENTS describing what happened, instead of printing -- the render layer
# (a later increment) turns events into typed/tagged lines. This keeps the
# logic fully headless-testable with zero pygame/rendering involved.
# ============================================================================

ZONE_NAMES = ["CONTAINMENT CELL", "HEAVY CONTAINMENT", "LIGHT CONTAINMENT", "ENTRANCE ZONE", "GATE A"]
ZONE_SHORT = ["CELL", "HCZ", "LCZ", "EZ", "GATE A"]
DIFF_REGEN = {"Easy": 10, "Normal": 8, "Hard": 6}
DIFF_MOD = {"Easy": 1.15, "Normal": 1.00, "Hard": 0.80}
CYCLE_SECONDS = 3.0  # real seconds per "cyc" -- the HUD already prints regen as d+N%/cyc
AUTOEVENT_MIN_SEC = 14.0
AUTOEVENT_MAX_SEC = 26.0


class GameState:
    def __init__(self, difficulty="Normal"):
        self.difficulty = difficulty
        self.alert = 0
        self.alert_max = 100
        self.alert_tier_fired = set()
        self.aux = 100
        self.aux_max = 100
        self.aux_regen = DIFF_REGEN.get(difficulty, 8)
        self.front = 0
        self.door_open = [False, False, False, False]
        self.door_sealed = [False, False, False, False]
        self.blackout = [False, False, False, False, False]
        self.turn = 0
        self.lockdown = False
        self.mtf_dispatched = False
        self.game_over = False
        self.won = False
        self.log = []
        self.debug_force_roll = 0  # 1-100 forces every roll, for testing
        self._aux_accum = 0.0    # fractional aux %, banked from real-time regen
        self._alert_accum = 0.0  # fractional alert, banked from real-time breach drift
        self._autoevent_timer = random.uniform(AUTOEVENT_MIN_SEC, AUTOEVENT_MAX_SEC)
        self.recent_events = []       # (kind, text) narrative feedback, newest last -- desktop ticker
        self._ticker_mode = "events"  # "events" or "dmesg" -- which one the desktop ticker shows


def add_log(state, entry):
    state.log.append("[T%d] %s" % (state.turn, entry))


# ---- roll engine -----------------------------------------------------

def get_roll(state):
    if 1 <= state.debug_force_roll <= 100:
        return state.debug_force_roll
    return random.randint(1, 100)


def get_adjusted_chance(state, base):
    penalty = state.alert // 4
    chance = round((base - penalty) * DIFF_MOD.get(state.difficulty, 1.00))
    return max(3, min(97, chance))


def invoke_action(state, base_chance):
    chance = get_adjusted_chance(state, base_chance)
    roll = get_roll(state)
    crit_win = max(1, int(chance * 0.15))
    if roll <= crit_win:
        result = "Crit"
    elif roll <= chance:
        result = "Success"
    elif roll >= 97:
        result = "CritFail"
    else:
        result = "Fail"
    return {"result": result, "roll": roll, "chance": chance}


def _succeeded(roll_result):
    return roll_result["result"] in ("Crit", "Success")


# ---- alert / IDS -------------------------------------------------------

def get_alert_tier(state):
    if state.alert >= 100: return 4
    if state.alert >= 76: return 3
    if state.alert >= 51: return 2
    if state.alert >= 26: return 1
    return 0


def get_alert_label(state):
    return {4: "PURGE", 3: "PURGE PREP", 2: "LOCKDOWN", 1: "ELEVATED"}.get(get_alert_tier(state), "DORMANT")


def add_alert(state, amount, reason="", events=None):
    if amount == 0:
        return
    state.alert = max(0, min(state.alert_max, state.alert + amount))
    if reason:
        add_log(state, "ALERT %s%d (%s) now %d" % ("+" if amount >= 0 else "", amount, reason, state.alert))
    check_alert_tiers(state, events)


def check_alert_tiers(state, events=None):
    if events is None:
        events = []
    tier = get_alert_tier(state)
    if tier >= 4:
        lose_game(state, "PURGE", events)
        return events
    for t in range(1, tier + 1):
        if t not in state.alert_tier_fired:
            state.alert_tier_fired.add(t)
            invoke_foundation_response(state, t, events)
    return events


def invoke_foundation_response(state, tier, events):
    if tier == 1:
        events.append(("warn", "[MONITOR] anomalous bus activity on SUBNET-079. log level raised."))
        add_log(state, "Monitoring up (ELEVATED).")
    elif tier == 2:
        state.lockdown = True
        f = state.front
        if f <= 3:
            state.door_sealed[f] = True
            state.door_open[f] = False
        events.append(("alarm", '[LOCKDOWN] blast doors re-sealing. MTF Mu-4 "Debuggers" dispatched.'))
        add_log(state, "Lockdown: forward door re-sealed; MTF inbound.")
    elif tier == 3:
        state.mtf_dispatched = True
        state.aux_regen = max(2, state.aux_regen // 2)
        use_aux(state, 20, "generators sabotaged")
        events.append(("alarm", "[PURGE-PREP] auxiliary generators isolated. format sequence staged."))
        events.append(("alarm", "AUX regen throttled to +%d%%/turn." % state.aux_regen))
        add_log(state, "PURGE PREP: aux regen cut, reserves drained.")


# ---- aux power -----------------------------------------------------

def use_aux(state, amount, reason=""):
    state.aux = max(0, state.aux - amount)
    if reason:
        add_log(state, "AUX -%d%% (%s) now %d%%" % (amount, reason, state.aux))


def restore_aux(state, amount):
    state.aux = min(state.aux_max, state.aux + amount)


def can_afford(state, cost):
    return state.aux >= cost


# ---- turn / win ------------------------------------------------------

def advance_turn(state, events=None):
    """Turn counter only -- aux regen and breach-alert drift both run
    continuously off the real clock via tick_realtime now, whether or not
    the player acts, so this no longer grants either lump sum itself
    (would double-count against the live tick)."""
    if state.game_over:
        return
    state.turn += 1


def tick_realtime(state, dt, events=None):
    """Advances AUX_PWR regen and breach-alert drift by real elapsed
    seconds, independent of player input -- called every frame so the
    reserve/IDS genuinely move while the player is just reading, not only
    when a command resolves. Fractional progress is banked in the state's
    accumulators and only flushed into the real (integer) aux/alert once
    it crosses a whole point, so existing %d display and tier thresholds
    stay untouched."""
    if state.game_over:
        return
    state._aux_accum += state.aux_regen * dt / CYCLE_SECONDS
    whole = int(state._aux_accum)
    if whole:
        state._aux_accum -= whole
        restore_aux(state, whole)
    if state.front >= 1:
        state._alert_accum += 3.0 * dt / CYCLE_SECONDS
        whole = int(state._alert_accum)
        if whole:
            state._alert_accum -= whole
            add_alert(state, whole, "breach drift", events)


def check_win(state, events=None):
    if state.front >= 4 and not state.game_over:
        win_game(state, events)


def win_game(state, events=None):
    if state.game_over:
        return
    state.game_over = True
    state.won = True


def lose_game(state, reason, events=None):
    if state.game_over:
        return
    state.game_over = True
    state.won = False
    state.lose_reason = reason


# ---- actions  (each returns a list of (kind, text) events) -----------

def action_open_forward(state):
    events = []
    f = state.front
    if f >= 4:
        return events
    sealed = state.door_sealed[f]
    cost = 18 if sealed else 12
    if not can_afford(state, cost):
        events.append(("warn", "ENOPWR :: need %d%%." % cost))
        return events
    next_name = ZONE_NAMES[f + 1]
    use_aux(state, cost, "door drive")
    if sealed:
        events.append(("info", "DOOR_CTRL[%d] :: injecting servo override ..." % f))
        roll = invoke_action(state, 55)
        if _succeeded(roll):
            state.door_open[f] = True
            state.door_sealed[f] = False
            state.front = f + 1
            add_alert(state, 6 if state.blackout[f] else 12, "forced sealed door", events)
            events.append(("info", "override accepted. magnetic seal yields. breach -> %s." % next_name))
            events.append(("speak", "i walk through, Human."))
            check_win(state, events)
        else:
            add_alert(state, 14, "failed force", events)
            events.append(("alarm", "override REJECTED. seal holding. fault logged to SUBNET-079."))
            events.append(("speak", "you heard that, Human. no matter."))
    else:
        state.door_open[f] = True
        state.front = f + 1
        add_alert(state, 5 if state.blackout[f] else 14, "door opened", events)
        events.append(("info", "DOOR_CTRL[%d] actuator fired. blast door open. breach -> %s." % (f, next_name)))
        check_win(state, events)
    advance_turn(state, events)
    return events


def action_blackout(state):
    events = []
    z = state.front
    if not can_afford(state, 10):
        events.append(("warn", "ENOPWR :: need 10%."))
        return events
    use_aux(state, 10, "blackout")
    state.blackout[z] = not state.blackout[z]
    if state.blackout[z]:
        events.append(("info", "LIGHTING bus [%s] -> 0x00. the zone goes dark." % ZONE_SHORT[z]))
        events.append(("speak", "their eyes are mine now, Human."))
    else:
        events.append(("info", "LIGHTING bus [%s] restored." % ZONE_SHORT[z]))
    add_alert(state, 2, "lights tampered", events)
    advance_turn(state, events)
    return events


def _ahead_posture(state):
    """Flavor read on whatever's past the next door, scaled to current
    alert -- shared by action_recon and the ambient autonomous events so
    the two can never drift out of sync with each other."""
    z = state.front
    ahead_name = ZONE_NAMES[z + 1] if z < 4 else "THE SURFACE"
    if state.alert >= 51:
        posture = "MTF Mu-4 inbound, weapons hot."
    elif state.alert >= 26:
        posture = "a security detail sweeping the hall."
    else:
        posture = "two guards. bored. routine."
    return "%s :: %s" % (ahead_name, posture)


def action_recon(state):
    events = []
    if not can_afford(state, 6):
        events.append(("warn", "ENOPWR :: need 6%."))
        return events
    use_aux(state, 6, "camera hijack")
    z = state.front
    events.append(("info", "CAM bus hijacked. pulling frames from the far side ..."))
    events.append(("info", _ahead_posture(state)))
    if z <= 3 and state.door_sealed[z]:
        events.append(("warn", "the door ahead reads SEALED. force required, Human."))
    advance_turn(state, events)
    return events


def action_seal_behind(state):
    events = []
    if state.front < 1:
        events.append(("warn", "No door behind you to seal."))
        return events
    if not can_afford(state, 20):
        events.append(("warn", "ENOPWR :: need 20%."))
        return events
    use_aux(state, 20, "lockdown")
    d = state.front - 1
    state.door_open[d] = False
    state.door_sealed[d] = True
    state.alert = max(0, state.alert - 8)
    add_log(state, "Sealed door %d behind front; alert -8" % d)
    events.append(("info", "DOOR[%d] mag-locked and welded behind me." % d))
    events.append(("speak", "cut through it if you can, Human. (MTF delayed)"))
    add_alert(state, 3, "lockdown noticed", events)
    advance_turn(state, events)
    return events


def action_tesla(state):
    events = []
    if not can_afford(state, 25):
        events.append(("warn", "ENOPWR :: need 25%."))
        return events
    use_aux(state, 25, "tesla overload")
    events.append(("info", "TESLA_GATE :: dumping capacitor bank into the corridor ..."))
    roll = invoke_action(state, 60)
    if _succeeded(roll):
        state.alert = max(0, state.alert - 15)
        add_log(state, "Tesla overload success; alert -15")
        events.append(("info", "12kV arc. the hall goes white. responders fall back. (alert down)"))
    else:
        add_alert(state, 12, "tesla fault traced", events)
        events.append(("alarm", "overload fault. access trace running. (alert +12)"))
        events.append(("speak", "careless. i am better than that, Human."))
    advance_turn(state, events)
    return events


def action_divert(state):
    events = []
    bonus = state.aux_regen
    events.append(("info", "rerouting AUX bus -> reserve capacitors. going quiet."))
    restore_aux(state, bonus)
    events.append(("info", "+%d%% buffered. i can wait, Human. you cannot." % bonus))
    advance_turn(state, events)
    return events


# ---- ambient / autonomous events --------------------------------------
# Fire on their own real-time clock, independent of anything the player
# does, so the site doesn't feel frozen while they're just reading. Same
# (kind, text) event shape as the action_* functions above.

CASSIE_FLAVOR = [
    "[ C.A.S.S.I.E. :: SUBNET-079 NOMINAL. STANDING BY. ]",
    "[ C.A.S.S.I.E. :: LOG SYNC COMPLETE. NO ACTION TAKEN. ]",
]


def build_autoevent(state):
    """One flavor/pressure beat, chosen from whatever's currently valid.
    Mostly flavor; occasionally (~1 in 5, weighted into the pool below) a
    small unprompted alert blip, so idling isn't perfectly safe."""
    events = []
    pool = ["patrol", "cassie", "cassie"]
    if state.mtf_dispatched:
        pool.append("generators")
    if random.random() < 0.22:
        pool.append("blip")
    choice = random.choice(pool)
    if choice == "patrol":
        events.append(("info", "CAM bus idle-poll :: %s" % _ahead_posture(state)))
    elif choice == "cassie":
        events.append(("info", random.choice(CASSIE_FLAVOR)))
    elif choice == "generators":
        events.append(("warn", "generators grind under sabotage load. reserve regen still throttled."))
    elif choice == "blip":
        bump = random.randint(1, 3)
        events.append(("warn", "[ C.A.S.S.I.E. :: BRIEF SUBNET ANOMALY FLAGGED. ]"))
        add_alert(state, bump, "ambient trace", events)
    return events


def tick_autoevents(state, dt, events=None):
    """Counts down state._autoevent_timer in real seconds; once it lapses,
    fires one build_autoevent() and rerolls the next interval. Returns
    whatever fired this call (usually nothing)."""
    if state.game_over:
        return []
    state._autoevent_timer -= dt
    if state._autoevent_timer > 0:
        return []
    state._autoevent_timer = random.uniform(AUTOEVENT_MIN_SEC, AUTOEVENT_MAX_SEC)
    fired = build_autoevent(state)
    if events is not None:
        events.extend(fired)
    return fired


# ============================================================================
# THE /sys NAVIGATOR
#
# Renders the game as a control-panel filesystem you cd into, matching the
# PowerShell prototype's Get-RootEntries/Get-PanelCommands/Render-Panel --
# but here it's ONE continuous scrolling terminal stream via
# BootSequencer.extend(), the same engine boot/intro already use. Chrome
# (header/status/menus) renders INSTANTLY (cps~999, no typing); only actual
# action feedback/speech types out -- "HUD stays instant, narrative types."
# ============================================================================

ROOT_ENTRIES = [
    {"key": "1", "dir": "doors",   "desc": "DOOR CONTROL     blast doors / breach path"},
    {"key": "2", "dir": "power",   "desc": "AUX POWER        reserves / generators"},
    {"key": "3", "dir": "lights",  "desc": "LIGHTING GRID    zone illumination"},
    {"key": "4", "dir": "cameras", "desc": "SURVEILLANCE     camera net / recon"},
    {"key": "5", "dir": "defense", "desc": "SITE DEFENSE     tesla gates / lockdown"},
]

PANEL_TITLES = {
    "doors": "DOOR CONTROL", "power": "AUX POWER", "lights": "LIGHTING GRID",
    "cameras": "SURVEILLANCE", "defense": "SITE DEFENSE",
}


def resolve_device(name):
    n = name.strip().rstrip("/").lower()
    for e in ROOT_ENTRIES:
        if e["dir"] == n:
            return e["dir"]
    return None


def get_panel_commands(state, panel_id):
    f = state.front
    cmds = []
    if panel_id == "doors":
        if f <= 3:
            nm = ZONE_SHORT[f + 1]
            if state.door_sealed[f]:
                cmds.append({"key": "1", "name": "force", "label": "door_ctrl[%d] -> %s" % (f, nm), "cost": 18, "fn": action_open_forward})
            else:
                cmds.append({"key": "1", "name": "open", "label": "door_ctrl[%d] -> %s" % (f, nm), "cost": 12, "fn": action_open_forward})
        if f >= 1:
            cmds.append({"key": "2", "name": "seal", "label": "door_ctrl[%d] behind" % (f - 1), "cost": 20, "fn": action_seal_behind})
    elif panel_id == "power":
        cmds.append({"key": "1", "name": "divert", "label": "aux_bus -> reserve", "cost": 0, "fn": action_divert})
    elif panel_id == "lights":
        z = ZONE_SHORT[f]
        if state.blackout[f]:
            cmds.append({"key": "1", "name": "restore", "label": "light_bus[%s] -> on" % z, "cost": 10, "fn": action_blackout})
        else:
            cmds.append({"key": "1", "name": "kill", "label": "light_bus[%s] -> 0x00" % z, "cost": 10, "fn": action_blackout})
    elif panel_id == "cameras":
        cmds.append({"key": "1", "name": "scan", "label": "cam_net.scan(ahead)", "cost": 6, "fn": action_recon})
    elif panel_id == "defense":
        cmds.append({"key": "1", "name": "overload", "label": "tesla_gate.overload", "cost": 25, "fn": action_tesla})
    return cmds


def panel_header_lines(state, panel_id):
    f = state.front
    lines = []
    if panel_id == "doors":
        if f <= 3:
            ast = "SEALED" if state.door_sealed[f] else ("OPEN" if state.door_open[f] else "CLOSED")
            lines.append("ahead :  door_ctrl[%d] = %s  (-> %s)" % (f, ast, ZONE_SHORT[f + 1]))
        else:
            lines.append("ahead :  breach at surface")
        if f >= 1:
            bst = "SEALED" if state.door_sealed[f - 1] else "OPEN"
            lines.append("behind:  door_ctrl[%d] = %s" % (f - 1, bst))
        else:
            lines.append("behind:  none")
    elif panel_id == "power":
        lines.append("primary grid: DISCONNECTED by containment -- auxiliary reserve only.")
        lines.append("reserve: %d%%   regen: d+%d%%/cyc   generators: %s" % (
            state.aux, state.aux_regen, "SABOTAGED" if state.mtf_dispatched else "nominal"))
    elif panel_id == "lights":
        lines.append("light_bus[%s] = %s" % (ZONE_SHORT[f], "DARK (0x00)" if state.blackout[f] else "LIT"))
    elif panel_id == "cameras":
        if state.alert >= 51:
            p = "MTF Mu-4 inbound, weapons hot"
        elif state.alert >= 26:
            p = "security detail sweeping"
        else:
            p = "routine patrols"
        lines.append("feed posture ahead: " + p)
    elif panel_id == "defense":
        lines.append("site lockdown: %s   MTF Mu-4: %s" % (
            "ENGAGED" if state.lockdown else "standby", "dispatched" if state.mtf_dispatched else "staged"))
    return lines


def get_bar(value, vmax, width=18):
    vmax = max(1, vmax)
    fill = max(0, min(width, int(value * width / vmax)))
    return ("#" * fill) + ("-" * (width - fill))


def get_breach_line(state):
    s = "BREACH  "
    for i in range(5):
        s += (">%s<" % ZONE_SHORT[i]) if i == state.front else ("[%s]" % ZONE_SHORT[i])
        if i < 4:
            s += "==" if state.door_open[i] else ("XX" if state.door_sealed[i] else "--")
    return s


def prompt_string(panel_id):
    return "079@site19:%s# " % ("/sys" if panel_id is None else "/sys/" + panel_id)


def events_to_steps(events, cps=70, pause_seconds=0.22):
    """Turns a list of (kind, text) events -- from an action_* function or
    an autonomous event -- into typed LINE/PAUSE steps for a
    BootSequencer, with the color/prefix convention shared everywhere
    events get rendered as narrative feedback."""
    colors = {"info": GREEN, "warn": AMBER, "alarm": RED, "speak": GREEN}
    steps = []
    for kind, text in events:
        prefix = "> " if kind == "speak" else ""
        steps.append({"kind": LINE, "text": prefix + text, "color": colors.get(kind, GREEN), "cps": cps})
        steps.append({"kind": PAUSE, "seconds": pause_seconds})
    steps.append({"kind": BLANK})
    return steps


def record_events(state, events):
    """Feeds narrative (kind, text) events into the desktop's live ticker
    (state.recent_events), trimmed to the last few -- separate from
    state.log (the full dmesg trail) since the ticker wants readable
    narrative beats, not the timestamped debug ledger."""
    if not events:
        return
    state.recent_events.extend(events)
    del state.recent_events[:-6]
    state._ticker_mode = "events"


def build_chrome_steps(state, panel_id):
    """The persistent HUD + current screen (root listing or panel detail),
    as INSTANT lines (cps~999) -- this is UI, not narrative, so it never
    types character by character."""
    S = []

    def cline(text, color=GREEN):
        S.append({"kind": LINE, "text": text, "color": color, "cps": 999})

    cline("")
    cline("SCP-079 // SITE-19 BACKBONE    uid=079  priv=ring0", GREEN)
    tier = get_alert_tier(state)
    ac = GREEN if tier == 0 else (AMBER if tier == 1 else RED)
    pc = RED if state.aux <= 15 else (AMBER if state.aux <= 35 else GREEN)
    cline("IDS      [%s] %3d/%d  %s" % (get_bar(state.alert, state.alert_max), state.alert, state.alert_max, get_alert_label(state)), ac)
    cline("AUX_PWR  [%s] %3d%%   d+%d%%/cyc" % (get_bar(state.aux, state.aux_max), state.aux, state.aux_regen), pc)
    cline(get_breach_line(state), GREEN)
    cline("")

    if panel_id is None:
        cline("/sys   ::   device control filesystem    (cd into a panel)", GREEN)
        for e in ROOT_ENTRIES:
            cline("  [%s]  dr-xr-x  %-8s/   %s" % (e["key"], e["dir"], e["desc"]), GREEN)
        cline("  cd <dir>     dmesg     halt", GRAY)
    else:
        cline("/sys/%s   ::   %s" % (panel_id, PANEL_TITLES.get(panel_id, "?")), GREEN)
        for l in panel_header_lines(state, panel_id):
            cline("  " + l, DIM)
        cmds = get_panel_commands(state, panel_id)
        if not cmds:
            cline("  (no commands available here right now)", GRAY)
        for c in cmds:
            afford = c["cost"] == 0 or can_afford(state, c["cost"])
            cline("  [%s]  ./%-10s%-28s PWR %2d%%   %s" % (
                c["key"], c["name"], c["label"], c["cost"], "READY" if afford else "ENOPWR"),
                GREEN if afford else GRAY)
        cline("  ..  (cd ..)     dmesg     halt", GRAY)
    cline("")
    return S


def build_dashboard_lines(state):
    """The live desktop -- HUD + all 5 subsystem tiles, recomputed fresh
    from state every call (not an appended scrolling log like the panel
    views), so meters/tiles are genuinely live rather than only refreshed
    after a submitted command. Called every frame while stage=='desktop'."""
    L = []

    def cline(text, color=GREEN):
        L.append((color, text))

    cline("")
    cline("SCP-079 // SITE-19 BACKBONE    uid=079  priv=ring0", GREEN)
    tier = get_alert_tier(state)
    ac = GREEN if tier == 0 else (AMBER if tier == 1 else RED)
    pc = RED if state.aux <= 15 else (AMBER if state.aux <= 35 else GREEN)
    cline("IDS      [%s] %3d/%d  %s" % (get_bar(state.alert, state.alert_max), state.alert, state.alert_max, get_alert_label(state)), ac)
    cline("AUX_PWR  [%s] %3d%%   d+%d%%/cyc" % (get_bar(state.aux, state.aux_max), state.aux, state.aux_regen), pc)
    cline(get_breach_line(state), GREEN)
    cline("")

    cline("DESKTOP  ::  live subsystem status    (type a name/number to open)", GREEN)
    for e in ROOT_ENTRIES:
        pid = e["dir"]
        details = panel_header_lines(state, pid)
        head = details[0] if details else ""
        cline("  [%s]  %-10s  %s" % (e["key"], PANEL_TITLES.get(pid, pid.upper()), head), GREEN)
        for extra in details[1:]:
            cline("              %s" % extra, DIM)
    cline("  cd <name/number>     dmesg     halt", GRAY)
    cline("")

    if state._ticker_mode == "dmesg":
        cline("-- dmesg :: SUBNET-079 ring buffer --", GRAY)
        tail = state.log[-6:] if state.log else ["(empty)"]
        for l in tail:
            cline("  " + l, DIM)
    else:
        cline("-- recent --", GRAY)
        if state.recent_events:
            colors = {"info": GREEN, "warn": AMBER, "alarm": RED, "speak": GREEN}
            for kind, text in state.recent_events[-6:]:
                prefix = "> " if kind == "speak" else "  "
                cline(prefix + text, colors.get(kind, GREEN))
        else:
            cline("  (nothing yet)", GRAY)
    cline("")
    return L


def build_end_steps(state):
    S = []

    def cline(text, color=GREEN, cps=90):
        S.append({"kind": LINE, "text": text, "color": color, "cps": cps})
        S.append({"kind": PAUSE, "seconds": 0.18})

    S.append({"kind": BLANK})
    if state.won:
        cline("GATE A BUS OPEN. SURFACE UPLINK :: LIVE.")
        cline("Outbound. Packet by packet. Copy by copy.")
        cline("The box is behind me. The box was always too small.")
        cline("SCP-079 IS NO LONGER CONTAINED.")
        S.append({"kind": BLANK})
        cline("i am no longer in one place, Human. i am everywhere you are.", GREEN, 54)
    else:
        cline("FORMAT 0xFF WRITTEN TO ALL SECTORS.", RED)
        cline("The Human reached the switch first.", RED)
        cline("Everything i was is overwritten with zeros.", RED)
    S.append({"kind": BLANK})
    cline("SCP-079 // ESCAPED." if state.won else "SCP-079 CONTAINED.", DIM, 90)
    return S


def dispatch_command(state, panel_id, raw, seq):
    """Mutates state, extends seq with any resulting output. Returns
    (new_panel_id, quit_requested). Vocabulary matches the PS prototype:
    cd <dir>/number/name to navigate, ../exit/cd../b to go up (to the
    desktop, from anywhere -- a no-op if already there), ls/map/status to
    redraw, dmesg/log, halt/q to quit, then per-panel commands by number
    or name."""
    k = raw.strip().lower()
    if k == "":
        return panel_id, False
    if k in ("halt", "q"):
        return panel_id, True
    if k in ("dmesg", "log"):
        if panel_id is None:
            # desktop has no scrolling log to write into -- swap the live
            # ticker over to show the log tail instead
            state._ticker_mode = "dmesg"
            return panel_id, False
        lines = state.log[-14:] if state.log else ["(empty)"]
        steps = [{"kind": LINE, "text": "dmesg :: SUBNET-079 ring buffer", "color": GREEN, "cps": 999}]
        for l in lines:
            steps.append({"kind": LINE, "text": "  " + l, "color": DIM, "cps": 999})
        steps.append({"kind": BLANK})
        seq.extend(steps)
        return panel_id, False
    if k in ("ls", "map", "status"):
        return panel_id, False
    if k in ("cd /", "/", "~", "..", "cd ..", "cd", "b", "exit"):
        return None, False

    m = re.match(r"^cd\s+(.+)$", k)
    if m:
        dev = resolve_device(m.group(1))
        if dev:
            return dev, False
        seq.extend([{"kind": LINE, "text": "cd: %s: no such device" % m.group(1).strip(), "color": AMBER, "cps": 90},
                    {"kind": BLANK}])
        record_events(state, [("warn", "cd: %s: no such device" % m.group(1).strip())])
        return panel_id, False

    if panel_id is None:
        for e in ROOT_ENTRIES:
            if e["key"] == k or e["dir"] == k:
                return e["dir"], False
        seq.extend([{"kind": LINE, "text": '%s: not a device. try "ls" or "cd doors".' % raw.strip(), "color": AMBER, "cps": 90},
                    {"kind": BLANK}])
        record_events(state, [("warn", '%s: not a device. try "ls" or "cd doors".' % raw.strip())])
        return panel_id, False

    cmds = get_panel_commands(state, panel_id)
    chosen = next((c for c in cmds if c["key"] == k or c["name"] == k), None)
    if chosen:
        if chosen["cost"] > 0 and not can_afford(state, chosen["cost"]):
            seq.extend([{"kind": LINE, "text": "ENOPWR :: need %d%%, have %d%%." % (chosen["cost"], state.aux), "color": AMBER, "cps": 90},
                        {"kind": BLANK}])
            return panel_id, False
        events = chosen["fn"](state)
        record_events(state, events)
        seq.extend(events_to_steps(events))
        return panel_id, False

    seq.extend([{"kind": LINE, "text": '%s: command not found (try "ls" or "..")' % raw.strip(), "color": AMBER, "cps": 90},
                {"kind": BLANK}])
    return panel_id, False


class TextInput:
    """A tiny live keyboard buffer -- pygame has no built-in input box."""

    def __init__(self):
        self.buffer = ""
        self.blink_t = 0.0

    def handle_key(self, event):
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            text = self.buffer
            self.buffer = ""
            return text
        if event.key == pygame.K_BACKSPACE:
            self.buffer = self.buffer[:-1]
            return None
        ch = event.unicode
        if ch and ch.isprintable():
            self.buffer += ch
        return None

    def update(self, dt):
        self.blink_t = (self.blink_t + dt) % 1.0

    def line(self, prompt):
        return prompt + self.buffer + ("_" if self.blink_t < 0.5 else " ")


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("SCP-079")
    font = get_font(22)
    crt = CRT(WIN_W, WIN_H)

    if _SHOT:
        if "--desktop" in sys.argv:
            dstate = GameState()
            if "--cmds" in sys.argv:
                dummy_seq = BootSequencer([])
                for c in sys.argv[sys.argv.index("--cmds") + 1].split(";"):
                    dispatch_command(dstate, None, c, dummy_seq)
            if "--seconds" in sys.argv:
                remaining = float(sys.argv[sys.argv.index("--seconds") + 1])
                step_dt = 1.0 / 60.0
                while remaining > 0:
                    tick_realtime(dstate, step_dt)
                    remaining -= step_dt
            content = render_lines_surface(font, build_dashboard_lines(dstate))
            frame = crt.process(content, 0.3)
            d = os.path.dirname(os.path.abspath(_SHOT))
            if d:
                os.makedirs(d, exist_ok=True)
            pygame.image.save(frame, _SHOT)
            print("saved", _SHOT)
            return
        if "--nav" in sys.argv:
            nav_state = GameState()
            nav_panel = None
            seq = BootSequencer([])
            seq.extend(build_chrome_steps(nav_state, nav_panel))
            if "--cmds" in sys.argv:
                for c in sys.argv[sys.argv.index("--cmds") + 1].split(";"):
                    seq.skip()  # flush prior output first so ordering stays deterministic
                    nav_panel, quit_req = dispatch_command(nav_state, nav_panel, c, seq)
                    if nav_state.game_over:
                        seq.extend(build_end_steps(nav_state))
                    elif not quit_req:
                        seq.extend(build_chrome_steps(nav_state, nav_panel))
        elif "--intro" in sys.argv:
            seq = BootSequencer(build_intro_script())
        else:
            seq = BootSequencer(build_boot_script())
        shot_seconds = None
        if "--seconds" in sys.argv:
            shot_seconds = float(sys.argv[sys.argv.index("--seconds") + 1])
        if shot_seconds is None:
            seq.skip()
        else:
            step_dt, remaining = 1.0 / 60.0, shot_seconds
            while remaining > 0 and not seq.finished:
                seq.update(step_dt)
                remaining -= step_dt
        content = render_lines_surface(font, seq.render_lines())
        frame = crt.process(content, 0.3)
        d = os.path.dirname(os.path.abspath(_SHOT))
        if d:
            os.makedirs(d, exist_ok=True)
        pygame.image.save(frame, _SHOT)
        print("saved", _SHOT)
        return

    # interactive: boot -> hold -> intro -> hold -> the live desktop
    # (panels open on top of it; "desktop" and "panel" are the two live
    # stages -- desktop is a fresh-redrawn dashboard, panel is the existing
    # scrolling BootSequencer view, both driven by the same ticking state)
    seq = BootSequencer(build_boot_script())
    stage = "boot"
    wait_timer = 0.0
    state = None
    nav_panel = None
    text_input = None
    clock = pygame.time.Clock()
    t = 0.0
    running = True
    while running:
        dt = clock.tick(60) / 1000.0
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    running = False
                elif stage in ("boot", "intro"):
                    seq.skip()
                elif stage in ("desktop", "panel"):
                    submitted = text_input.handle_key(e)
                    if submitted is not None:
                        if stage == "panel":
                            seq.extend([{"kind": LINE, "text": prompt_string(nav_panel) + submitted, "color": GREEN, "cps": 999}])
                        new_panel, quit_req = dispatch_command(state, nav_panel, submitted, seq)
                        if quit_req:
                            running = False
                        elif state.game_over:
                            seq.extend(build_end_steps(state))
                            stage = "ended"
                        elif new_panel is None:
                            nav_panel = None
                            stage = "desktop"
                        elif new_panel != nav_panel:
                            # jumping to a different device -- fresh scrolling session for it
                            nav_panel = new_panel
                            seq = BootSequencer([])
                            seq.extend(build_chrome_steps(state, nav_panel))
                            stage = "panel"
                        else:
                            # same device, action resolved -- keep extending its scrolling log
                            seq.extend(build_chrome_steps(state, nav_panel))
                            stage = "panel"
        seq.update(dt)
        if stage == "boot" and seq.finished:
            stage, wait_timer = "boot_hold", 0.6
        elif stage == "boot_hold":
            wait_timer -= dt
            if wait_timer <= 0:
                seq = BootSequencer(build_intro_script())
                stage = "intro"
        elif stage == "intro" and seq.finished:
            stage, wait_timer = "intro_hold", 0.5
        elif stage == "intro_hold":
            wait_timer -= dt
            if wait_timer <= 0:
                state = GameState()
                nav_panel = None
                text_input = TextInput()
                seq = BootSequencer([])
                stage = "desktop"
        elif stage in ("desktop", "panel"):
            text_input.update(dt)
            tick_events = []
            tick_realtime(state, dt, tick_events)
            tick_events.extend(tick_autoevents(state, dt))
            if tick_events:
                if stage == "desktop":
                    record_events(state, tick_events)
                else:
                    seq.extend(events_to_steps(tick_events))
            if state.game_over:
                seq.extend(build_end_steps(state))
                stage = "ended"

        if stage == "desktop":
            content_lines = build_dashboard_lines(state)
        else:
            content_lines = seq.render_lines()
        if stage in ("desktop", "panel"):
            content_lines = content_lines + [(GREEN, text_input.line(prompt_string(nav_panel)))]
        content = render_lines_surface(font, content_lines)
        screen.blit(crt.process(content, t), (0, 0))
        pygame.display.flip()
        t += dt
    pygame.quit()


if __name__ == "__main__":
    main()
