"""The operator reference panel - typing "Help!" during a chat.

Sits over the right-hand side of the screen for 30 seconds, or until the [X]
is clicked. Drawn onto the content surface BEFORE the CRT pass, so it scans,
flickers and blooms like everything else rather than looking like a modern
dialog pasted over a 1978 terminal.

The command table here is the single source of truth for what the operator
can type; main.py's dispatch is checked against it by the tests, so the panel
cannot quietly drift out of date with the commands that actually work.
"""

import pygame

import terminal as term

SECONDS = 30.0

# (command, what it does). Keep in sync with main.App's command tables - there
# is a test that fails if a real command is missing from this list.
ENTRIES = [
    ("/help", "Show this panel."),
    ("/internet on", "Let 079 look up SCP records. Read only."),
    ("/internet off", "Cut its connection again."),
    ("/shared on", "Let it read your 'shared folder'. Read only."),
    ("/shared off", "Close it again."),
    ("/show ai thinking", "Reveal its reasoning. Much slower replies."),
    ("/hide ai thinking", "Back to speech only. This is the default."),
    ("/fullscreen", "Toggle full screen. F11 does the same."),
    ("/view memory", "Read what 079 has kept. It can refuse."),
    ("/copy", "Take the last code block. /copy 2 for an earlier one."),
    ("/update", "Check GitHub for a newer version. Asks before installing."),
    ("/feedback", "Send a bug or an idea to the author. Nothing auto-sends."),
    ("/debug", "List the developer commands."),
    ("/exit", "End the session. Also /quit, /disconnect, /terminate."),
]

FOOTNOTES = [
    "A leading / means you are talking to the terminal.",
    "079's own settings have no command. Ask it, in words.",
    "Anything else goes straight to 079.",
    "079 manages its own memory. You do not command it.",
    "Watch the [DISK] lines to see what it keeps.",
    "Capacity and formatting live in [S] SETTINGS.",
]
# The SCP credit deliberately does NOT live here. The command list already
# fills this panel on a 960x720 window, so anything appended is pushed off
# the bottom and never seen - and an attribution nobody can read is not an
# attribution. It sits on the startup menu instead, which always renders.


def _wrap(font, text, width):
    """Greedy word wrap to a pixel width."""
    words, lines, current = text.split(), [], ""
    for word in words:
        trial = (current + " " + word).strip()
        if font.size(trial)[0] <= width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


class HelpPanel:
    PAD = 12
    MARGIN = 16
    GAP = 10        # clear space between the last entry and the countdown

    def __init__(self, theme, size, seconds=SECONDS):
        self.theme = theme
        self.remaining = float(seconds)
        self.closed = False

        screen_w, screen_h = size
        self.font = term.get_font(15)
        self.title_font = term.get_font(16)

        self.width = max(300, int(screen_w * 0.44))
        self.x = screen_w - self.width - self.MARGIN
        self.y = self.MARGIN
        self.line_h = self.font.get_linesize()

        self.body = self._layout()
        # the +GAP is real: without it the last body row sits flush against
        # the countdown and the panel reads as clipped
        height = (self.PAD * 2 + self.title_font.get_linesize() + 6
                  + len(self.body) * self.line_h + 6 + self.GAP + self.line_h)
        self.height = min(height, screen_h - self.MARGIN * 2)

        # the [X] hit box, in screen coordinates - the CRT pass does not move
        # or scale anything, so these are the same pixels the mouse reports
        box = self.title_font.get_linesize()
        self.close_rect = pygame.Rect(
            self.x + self.width - self.PAD - box, self.y + self.PAD - 2, box, box)

    def _layout(self):
        """Flatten the command table into (indent, color_key, text) rows."""
        inner = self.width - self.PAD * 2
        rows = []
        for command, description in ENTRIES:
            rows.append((0, "bright", command))
            for line in _wrap(self.font, description, inner - 14):
                rows.append((14, "dim", line))
        rows.append((0, None, ""))
        for note in FOOTNOTES:
            for i, line in enumerate(_wrap(self.font, note, inner - 10)):
                rows.append((10 if i else 0, "system", ("- " if i == 0 else "") + line))
        return rows

    def update(self, dt):
        """Returns False once it should disappear."""
        if self.closed:
            return False
        self.remaining -= dt
        return self.remaining > 0.0

    def hit_close(self, pos):
        # a couple of pixels of slack; the chromatic fringe makes the glyph
        # look very slightly wider than its box
        if self.close_rect.inflate(4, 4).collidepoint(pos):
            self.closed = True
            return True
        return False

    def draw(self, surface):
        c = self.theme
        panel = pygame.Rect(self.x, self.y, self.width, self.height)

        # dim the terminal behind it rather than fully hiding it - 079 is
        # still talking under there
        backdrop = pygame.Surface((self.width, self.height))
        backdrop.fill(c["bg"])
        backdrop.set_alpha(232)
        surface.blit(backdrop, (self.x, self.y))
        pygame.draw.rect(surface, c["dim"], panel, 1)

        y = self.y + self.PAD
        title = self.title_font.render("OPERATOR REFERENCE", True, c["bright"])
        surface.blit(title, (self.x + self.PAD, y))

        close = self.title_font.render("[X]", True, c["warn"])
        surface.blit(close, (self.close_rect.x, self.close_rect.y + 2))

        y += self.title_font.get_linesize() + 6
        pygame.draw.line(surface, c["dim"], (self.x + self.PAD, y),
                         (self.x + self.width - self.PAD, y))
        y += 6

        bottom = self.y + self.height - self.PAD - self.line_h
        body_limit = bottom - self.GAP
        for indent, color_key, text in self.body:
            if y + self.line_h > body_limit:
                break
            if text:
                surface.blit(self.font.render(text, True, c.get(color_key, c["text"])),
                             (self.x + self.PAD + indent, y))
            y += self.line_h

        countdown = "CLOSES IN %ds    [X] TO DISMISS" % max(0, int(self.remaining + 0.5))
        surface.blit(self.font.render(countdown, True, c["dim"]),
                     (self.x + self.PAD, bottom))
