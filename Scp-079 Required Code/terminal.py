"""The CRT display layer: post-processing, the scrolling text console,
the typewriter, and keyboard input.

Nothing in here knows about Ollama, SCP-079, or the boot sequence - it is
just "an old monitor you can print text to", so other personalities and
screens can reuse it unchanged.

The CRT class is ported from the screenshot-verified prototype in
'Use as examples/scp079.py' rather than rewritten, with the individual
passes made switchable from config.json.
"""

import math
import random

import pygame

_FONT_CANDIDATES = ("consolas", "cascadiamono", "lucidaconsole", "couriernew", "dejavusansmono")


def _merge(segments):
    """Join neighbouring same-color pieces back together.

    Wrapping works word by word; without this every word would become its
    own font.render call on every frame.
    """
    out = []
    for color, text in segments:
        if out and out[-1][0] == color:
            out[-1] = (color, out[-1][1] + text)
        else:
            out.append((color, text))
    return out


def get_font(size):
    """Best available monospace face, falling back to pygame's default."""
    for name in _FONT_CANDIDATES:
        try:
            font = pygame.font.SysFont(name, size)
            if font:
                return font
        except Exception:
            pass
    return pygame.font.Font(None, size)


# ---------------------------------------------------------------------------
# CRT post-processor. Plain surface math (no GL) - plenty for a mostly-static
# terminal, and it keeps the dependency list at just pygame.
# ---------------------------------------------------------------------------
class CRT:
    def __init__(self, w, h, cfg=None):
        self.w, self.h = w, h
        self.cfg = cfg or {}
        self.scan = self._make_scanlines()
        self.vig = self._make_vignette()
        self.noise = [self._make_noise(9) for _ in range(5)]
        self.harsh_noise = [self._make_noise(150) for _ in range(4)]

    def _on(self, key):
        return bool(self.cfg.get(key, True))

    def _make_scanlines(self):
        # White surface with a darker line every 3rd row, applied via MULT so
        # those rows are dimmed -> horizontal scanlines.
        surf = pygame.Surface((self.w, self.h))
        surf.fill((255, 255, 255))
        line = pygame.Surface((self.w, 1))
        line.fill((78, 78, 78))
        for y in range(0, self.h, 3):
            surf.blit(line, (0, y))
        return surf

    def _make_vignette(self):
        vs = 128
        vh = max(1, int(vs * self.h / self.w))
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

    def _make_noise(self, amplitude):
        ns = 200
        nh = max(1, int(ns * self.h / self.w))
        surf = pygame.Surface((ns, nh))
        for y in range(nh):
            for x in range(ns):
                v = random.randint(0, amplitude)
                surf.set_at((x, y), (v, v, v))
        return pygame.transform.smoothscale(surf, (self.w, self.h))

    def process(self, base, t=0.0, fx=None):
        """Run one frame through the tube.

        fx is an optional dict from effects.py:
          invert  - bool, brief color inversion
          static  - 0..1, static burst strength
          dim     - 0..1, extra brightness drop for a flicker
          offset  - int, horizontal tracking jump in pixels
        """
        fx = fx or {}
        w, h = self.w, self.h

        if not self.cfg.get("enabled", True):
            return base

        out = pygame.Surface((w, h))
        out.fill((0, 0, 0))

        if self._on("chromatic_aberration"):
            # split into R/G/B and re-add with a slight horizontal offset so
            # bright edges pick up a color fringe
            off = 2
            r = base.copy(); r.fill((255, 0, 0), special_flags=pygame.BLEND_MULT)
            g = base.copy(); g.fill((0, 255, 0), special_flags=pygame.BLEND_MULT)
            b = base.copy(); b.fill((0, 0, 255), special_flags=pygame.BLEND_MULT)
            out.blit(r, (off, 0), special_flags=pygame.BLEND_ADD)
            out.blit(g, (0, 0), special_flags=pygame.BLEND_ADD)
            out.blit(b, (-off, 0), special_flags=pygame.BLEND_ADD)
        else:
            out.blit(base, (0, 0))

        blur = None
        if self._on("bloom") or self._on("soft_focus"):
            ds = 5
            small = pygame.transform.smoothscale(out, (max(1, w // ds), max(1, h // ds)))
            blur = pygame.transform.smoothscale(small, (w, h))

        if self._on("bloom") and blur is not None:
            # downscale/upscale blur, dimmed and added back so text glows
            glow = blur.copy()
            glow.fill((150, 150, 150), special_flags=pygame.BLEND_MULT)
            out.blit(glow, (0, 0), special_flags=pygame.BLEND_ADD)

        if self._on("soft_focus") and blur is not None:
            soft = blur.copy()
            soft.set_alpha(70)
            out.blit(soft, (0, 0))

        if self._on("scanlines"):
            out.blit(self.scan, (0, 0), special_flags=pygame.BLEND_MULT)

        if self._on("grain"):
            frame = self.noise[int(t * 18) % len(self.noise)]
            out.blit(frame, (0, 0), special_flags=pygame.BLEND_ADD)

        static = float(fx.get("static", 0.0))
        if static > 0.0:
            burst = random.choice(self.harsh_noise).copy()
            burst.set_alpha(int(max(0.0, min(1.0, static)) * 210))
            out.blit(burst, (0, 0), special_flags=pygame.BLEND_ADD)

        if self._on("vignette"):
            out.blit(self.vig, (0, 0), special_flags=pygame.BLEND_MULT)

        level = 1.0
        if self._on("flicker"):
            level *= 0.93 + 0.07 * random.random()
        level *= max(0.0, 1.0 - float(fx.get("dim", 0.0)))
        if level < 0.999:
            shade = int(255 * max(0.0, min(1.0, level)))
            out.fill((shade, shade, shade), special_flags=pygame.BLEND_MULT)

        if fx.get("invert"):
            inverted = pygame.Surface((w, h))
            inverted.fill((255, 255, 255))
            inverted.blit(out, (0, 0), special_flags=pygame.BLEND_RGB_SUB)
            out = inverted

        offset = int(fx.get("offset", 0))
        if offset:
            shifted = pygame.Surface((w, h))
            shifted.fill((0, 0, 0))
            shifted.blit(out, (offset, 0))
            out = shifted

        return out


# ---------------------------------------------------------------------------
# Text console: a scrollback buffer plus one live "being typed" line.
# ---------------------------------------------------------------------------
class Console:
    """Holds finished rows and, optionally, one line currently typing out.

    A row is either (color, text) or a list of (color, text) segments for
    two-tone lines like 'CHECKING MEMORY........[ OK ]'.

    Streaming replies work by starting a live line, feeding it text as it
    arrives from the model, then closing it - the reveal speed is driven by
    the typewriter, never by how fast tokens land, so a burst of text still
    types out at a human pace instead of appearing instantly.
    """

    MAX_ROWS = 600

    def __init__(self, theme, typing_cfg=None):
        self.theme = theme
        self.typing_cfg = typing_cfg or {}
        self.rows = []
        self._live = None

    # -- committed output ---------------------------------------------------
    def write(self, text="", color=None):
        self.rows.append((color or self.theme["text"], text))
        self._trim()

    def write_segments(self, segments):
        self.rows.append(list(segments))
        self._trim()

    def blank(self):
        self.write("")

    def _trim(self):
        if len(self.rows) > self.MAX_ROWS:
            del self.rows[: len(self.rows) - self.MAX_ROWS]

    # -- live typed line ----------------------------------------------------
    def start_stream(self, color=None, cps=None, prefix_segments=None):
        """Begin a line that reveals character by character.

        prefix_segments render instantly ahead of the typed text, which is
        how the '079 > ' speaker tag appears before the reply types out.
        """
        self._live = {
            "color": color or self.theme["text"],
            "prefix": list(prefix_segments or []),
            "target": "",
            "revealed": 0,
            "acc": 0.0,
            "pause": 0.0,
            "cps": float(cps or self.typing_cfg.get("cps", 42)),
            "closed": False,
        }

    def feed(self, chunk):
        if self._live is None or not chunk:
            return
        self._live["target"] += chunk

    def finish_stream(self):
        """No more text is coming; the line commits once typing catches up."""
        if self._live is not None:
            self._live["closed"] = True

    def cancel_stream(self):
        """Drop the live line immediately, revealed or not."""
        self._live = None

    @property
    def is_typing(self):
        live = self._live
        if live is None:
            return False
        return live["revealed"] < len(live["target"]) or not live["closed"]

    @property
    def has_live_line(self):
        return self._live is not None

    @property
    def live_caught_up(self):
        """True when the live line has revealed everything fed to it so far.

        Lets a caller (the boot runner) wait for one segment to finish typing
        before starting the next, without having to predict its duration -
        which the speed jitter makes impossible to compute up front.
        """
        live = self._live
        if live is None:
            return False
        return live["revealed"] >= len(live["target"]) and live["pause"] <= 0.0

    def live_text(self):
        live = self._live
        return "" if live is None else live["target"]

    def flush_stream(self):
        """Reveal everything pending at once and commit (used for skip)."""
        live = self._live
        if live is None:
            return
        live["revealed"] = len(live["target"])
        if live["closed"]:
            self._commit_live()

    def _commit_live(self):
        live = self._live
        if live is None:
            return
        text = live["target"]
        if live["prefix"]:
            self.rows.append(live["prefix"] + [(live["color"], text)])
        else:
            self.rows.append((live["color"], text))
        self._trim()
        self._live = None

    def update(self, dt):
        live = self._live
        if live is None:
            return
        if live["pause"] > 0.0:
            live["pause"] -= dt
            return

        jitter = float(self.typing_cfg.get("jitter", 0.3))
        speed = live["cps"] * random.uniform(max(0.05, 1.0 - jitter), 1.0 + jitter)
        live["acc"] += dt * speed

        while live["acc"] >= 1.0 and live["revealed"] < len(live["target"]):
            live["acc"] -= 1.0
            ch = live["target"][live["revealed"]]
            live["revealed"] += 1
            if ch == "\n":
                # a newline inside a streamed reply ends the row and starts a
                # fresh live line, so multi-line replies still wrap correctly
                head = live["target"][: live["revealed"] - 1]
                if live["prefix"]:
                    self.rows.append(live["prefix"] + [(live["color"], head)])
                    # Keep the COLUMN, drop the text. Clearing the prefix
                    # outright dumped every line after the first back to
                    # column 0, so a reply containing a newline broke out of
                    # the speech column and ran across the whole screen -
                    # visible all over the play screenshots. A wrapped line
                    # already indents under its prefix; an explicit newline
                    # has to do the same or the two disagree.
                    width = sum(len(text) for _, text in live["prefix"])
                    live["prefix"] = [(live["color"], " " * width)]
                else:
                    self.rows.append((live["color"], head))
                self._trim()
                live["target"] = live["target"][live["revealed"]:]
                live["revealed"] = 0
                continue
            if ch in ".!?":
                live["pause"] = float(self.typing_cfg.get("punctuation_pause", 0.26))
                break
            if ch in ",;:":
                live["pause"] = float(self.typing_cfg.get("comma_pause", 0.10))
                break

        if live["closed"] and live["revealed"] >= len(live["target"]) and live["pause"] <= 0.0:
            self._commit_live()

    # -- rendering ----------------------------------------------------------
    def entries(self):
        """Everything to draw: finished rows plus the partially typed line."""
        out = list(self.rows)
        live = self._live
        if live is not None:
            partial = live["target"][: live["revealed"]]
            if live["prefix"]:
                out.append(live["prefix"] + [(live["color"], partial)])
            else:
                out.append((live["color"], partial))
        return out


# ---------------------------------------------------------------------------
# Renderer: entries -> a surface, with word wrap and smooth scrolling.
# ---------------------------------------------------------------------------
class Renderer:
    MARGIN_LEFT = 44
    MARGIN_RIGHT = 30
    MARGIN_TOP = 30
    MARGIN_BOTTOM = 30

    def __init__(self, size, font, theme):
        self.w, self.h = size
        self.font = font
        self.theme = theme
        self.line_height = font.get_height() + 5
        self.reserved_right = 0     # width handed to a side panel, if any
        self.row_positions = {}     # {row text: y} for the last frame drawn
        self.scrollback = 0         # rows held back from the live bottom
        self.max_width = self.w - self.MARGIN_LEFT - self.MARGIN_RIGHT
        self.max_visible = max(1, (self.h - self.MARGIN_TOP - self.MARGIN_BOTTOM) // self.line_height)
        self.slide = 0.0
        self._last_rows = 0
        self._first = True
        # rows are only ever drawn between the top margin and here; anything
        # mid-slide past it gets clipped, like a real terminal's edge
        self.content_bottom = self.MARGIN_TOP + self.max_visible * self.line_height

    def reserve_right(self, width):
        """Keep `width` pixels clear on the right for a side panel.

        Wrapping has to know about it, otherwise text is drawn underneath the
        panel and simply disappears behind it - the row still exists, it is
        just unreadable, which is worse than it being wrapped.
        """
        width = max(0, int(width))
        if width == self.reserved_right:
            return
        self.reserved_right = width
        self.max_width = self.w - self.MARGIN_LEFT - self.MARGIN_RIGHT - width

    def _wrap(self, text, color):
        """Word-wrap one entry, hard-breaking a single word that is still
        too long on its own."""
        if not text or self.font.size(text)[0] <= self.max_width:
            return [(color, text)]
        rows, cur = [], ""
        for word in text.split(" "):
            trial = word if not cur else (cur + " " + word)
            if self.font.size(trial)[0] <= self.max_width:
                cur = trial
                continue
            if cur:
                rows.append(cur)
            if self.font.size(word)[0] <= self.max_width:
                cur = word
            else:
                chunk = ""
                for ch in word:
                    if chunk and self.font.size(chunk + ch)[0] > self.max_width:
                        rows.append(chunk)
                        chunk = ch
                    else:
                        chunk += ch
                cur = chunk
        if cur:
            rows.append(cur)
        return [(color, r) for r in rows]

    MAX_INDENT = 12

    def _wrap_segments(self, segments):
        """Wrap a multi-colored row (e.g. '079 > ' + a long reply).

        Continuation rows are indented under the first segment so a wrapped
        reply lines up beneath itself instead of starting at the margin.
        """
        full = "".join(text for _, text in segments)
        if not full or self.font.size(full)[0] <= self.max_width:
            return [segments]

        indent = ""
        if len(segments) > 1:
            indent = " " * min(self.MAX_INDENT, len(segments[0][1]))

        # split into (color, word) tokens, keeping the space before each word
        tokens = []
        for color, text in segments:
            if not text:
                continue
            first = True
            for piece in text.split(" "):
                tokens.append((color, piece if first else " " + piece))
                first = False

        rows, cur, cur_text = [], [], ""
        for color, token in tokens:
            if cur and self.font.size(cur_text + token)[0] > self.max_width:
                rows.append(cur)
                cur, cur_text = ([(color, indent)] if indent else []), indent
                token = token.lstrip(" ")
                if not token:
                    continue
            # a single token too wide for a whole row has to be broken
            while self.font.size(cur_text + token)[0] > self.max_width and len(token) > 1:
                cut = len(token)
                while cut > 1 and self.font.size(cur_text + token[:cut])[0] > self.max_width:
                    cut -= 1
                cur.append((color, token[:cut]))
                rows.append(cur)
                token = token[cut:]
                cur, cur_text = ([(color, indent)] if indent else []), indent
            if token:
                cur.append((color, token))
                cur_text += token
        if cur:
            rows.append(cur)
        return [_merge(row) for row in rows]

    def expand(self, entries):
        """Turn entries into physical rows (wrapping first) so scrolling
        counts what is actually on screen, not logical lines."""
        rows = []
        for entry in entries:
            if isinstance(entry, tuple):
                rows.extend(self._wrap(entry[1], entry[0]))
            else:
                rows.extend(self._wrap_segments(entry))
        return rows

    def scroll(self, rows_delta):
        """Move the view back through scrollback. Positive = older.

        Clamped in render(), where the true row count is known - the caller
        has entries, not wrapped rows, and one entry can wrap to several.
        """
        self.scrollback = max(0, self.scrollback + rows_delta)

    def scroll_to_live(self):
        self.scrollback = 0

    # Where each drawn row landed this frame, as {text: y}. Anything that
    # wants to put a clickable control on a transcript row needs this: the
    # rows move as the conversation scrolls, so a button's position cannot be
    # worked out once and cached - it has to come from the frame that just
    # drew it. Cleared and rebuilt every render.
    def _note_row(self, entry, y):
        if isinstance(entry, tuple):
            text = entry[1]
        else:
            text = "".join(part for _, part in entry)
        if text:
            self.row_positions[text] = y

    def render(self, entries, dt=0.0):
        self.row_positions = {}
        rows = self.expand(entries)
        overflowing = len(rows) > self.max_visible

        # Clamp scrollback to what actually exists. Doing it here rather than
        # in scroll() means the limit follows the real wrapped row count, so
        # it cannot run off the top of a conversation that rewrapped when the
        # side panel appeared.
        self.scrollback = max(0, min(self.scrollback,
                                     max(0, len(rows) - self.max_visible)))
        if self.scrollback:
            # while held back, drop the newest rows from view and skip the
            # slide animation entirely - sliding a frozen view looks broken
            rows = rows[: len(rows) - self.scrollback]
            surf = pygame.Surface((self.w, self.h))
            surf.fill(self.theme["bg"])
            y = self.MARGIN_TOP
            for entry in rows[-self.max_visible:]:
                x = self.MARGIN_LEFT
                if isinstance(entry, tuple):
                    color, text = entry
                    if text:
                        surf.blit(self.font.render(text, True, color), (x, y))
                else:
                    for color, text in entry:
                        if text:
                            img = self.font.render(text, True, color)
                            surf.blit(img, (x, y))
                            x += img.get_width()
                self._note_row(entry, y)
                y += self.line_height
            self._last_rows = len(self.expand(entries))
            return surf

        # smooth scroll: new rows push the view up over a few frames instead
        # of snapping, which is what sells "a terminal scrolling" vs "a list".
        # The first frame fills the screen from empty, which is not a scroll -
        # sliding there would just drop the view in from above.
        added = len(rows) - self._last_rows
        if self._first:
            self._first = False
            added = 0
        if added > 0 and overflowing:
            self.slide = min(self.line_height * 2.0, self.slide + added * self.line_height)
        self._last_rows = len(rows)
        if self.slide > 0.0:
            self.slide = max(0.0, self.slide - dt * self.line_height * 14.0)

        extra = int(math.ceil(self.slide / self.line_height)) if self.slide > 0 else 0
        surf = pygame.Surface((self.w, self.h))
        surf.fill(self.theme["bg"])

        visible = rows[-(self.max_visible + extra):] if (self.max_visible + extra) else []
        y = self.MARGIN_TOP - (extra * self.line_height) + self.slide
        for entry in visible:
            x = self.MARGIN_LEFT
            if isinstance(entry, tuple):
                color, text = entry
                if text:
                    surf.blit(self.font.render(text, True, color), (x, y))
            else:
                for color, text in entry:
                    if text:
                        img = self.font.render(text, True, color)
                        surf.blit(img, (x, y))
                        x += img.get_width()
            self._note_row(entry, y)
            y += self.line_height

        # hide whatever is mid-slide outside the text area, top and bottom
        if extra:
            surf.fill(self.theme["bg"], pygame.Rect(0, 0, self.w, self.MARGIN_TOP))
        surf.fill(self.theme["bg"],
                  pygame.Rect(0, self.content_bottom, self.w, self.h - self.content_bottom))
        return surf


# ---------------------------------------------------------------------------
# Keyboard input
# ---------------------------------------------------------------------------
class TextInput:
    """A tiny live keyboard buffer - pygame has no built-in input box."""

    MAX_LEN = 400

    def __init__(self, blink_seconds=0.55, cursor_glyph="█"):
        self.buffer = ""
        self.blink_t = 0.0
        self.blink_seconds = max(0.05, float(blink_seconds))
        self.cursor_glyph = cursor_glyph
        self.enabled = True

    def handle_key(self, event):
        """Returns the submitted string on Enter, otherwise None."""
        if not self.enabled:
            return None
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            text = self.buffer
            self.buffer = ""
            return text
        if event.key == pygame.K_BACKSPACE:
            self.buffer = self.buffer[:-1]
            return None
        if event.key == pygame.K_ESCAPE:
            return None
        ch = event.unicode
        if ch and ch.isprintable() and len(self.buffer) < self.MAX_LEN:
            self.buffer += ch
        return None

    def update(self, dt):
        self.blink_t = (self.blink_t + dt) % (self.blink_seconds * 2.0)

    def line(self, prompt_segments, color, show_cursor=True):
        """Build a renderable row: the prompt segments plus the live buffer
        and a blinking block. The block is hidden while 079 is talking, per
        the spec - the cursor only blinks when input is actually wanted."""
        cursor = ""
        if show_cursor and self.enabled:
            cursor = self.cursor_glyph if self.blink_t < self.blink_seconds else " "
        return list(prompt_segments) + [(color, self.buffer + cursor)]
