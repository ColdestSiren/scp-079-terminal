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

import devtrap
import terminal as term

SECONDS = 30.0

# How long each page of the reference is held before the next one comes up.
# Slow enough to finish reading a page, fast enough that a 30 second panel
# gets through all of them.
PAGE_SECONDS = 7.5

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
    # {bypass} is filled in from the real key binding at layout time. The
    # lockout screen names this shortcut the first time you hit a timeout and
    # then never again, so this is where it lives permanently.
    ("/unlock", "Skip a lockout wait. {bypass} does the same, and works "
                "on the refusal screen where there is nothing to type into."),
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

        # On the DEFAULT 960x720 window this panel wanted 839px and had 688,
        # so draw() hit its limit and simply stopped - eight rows short. The
        # footnotes explaining that a leading slash talks to the terminal, and
        # that 079 manages its own memory, were never on screen for anyone who
        # had not enlarged the window. Nothing said so; the list just ended.
        #
        # So it pages instead of stopping. Everything gets its turn, and a
        # panel that visibly has a page 2 is honest about there being more,
        # which a silently truncated list is not.
        self.pages = self._paginate()
        self.page = 0
        self._page_timer = 0.0

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
            described = description.replace("{bypass}", devtrap.bypass_label())
            for line in _wrap(self.font, described, inner - 14):
                rows.append((14, "dim", line))
        rows.append((0, None, ""))
        for note in FOOTNOTES:
            for i, line in enumerate(_wrap(self.font, note, inner - 10)):
                rows.append((10 if i else 0, "system", ("- " if i == 0 else "") + line))
        return rows

    def rows_per_page(self):
        usable = (self.height - self.PAD * 2 - self.title_font.get_linesize()
                  - 6 - 6 - self.GAP - self.line_h)
        return max(1, int(usable // self.line_h))

    def _paginate(self):
        """Chunk the body, without stranding a command from its description."""
        per = self.rows_per_page()
        pages, index = [], 0
        while index < len(self.body):
            page = self.body[index:index + per]
            if index + per < len(self.body):
                # A command heading alone at the foot of a page reads as a
                # command with no explanation, so it goes over with its
                # description rather than being separated from it.
                while page and page[-1][1] == "bright":
                    page.pop()
                if not page:                     # every row is a heading
                    page = self.body[index:index + per]
            pages.append(page)
            index += len(page)
        return pages or [[]]

    def update(self, dt):
        """Returns False once it should disappear."""
        if self.closed:
            return False
        self.remaining -= dt
        if len(self.pages) > 1:
            self._page_timer += dt
            while self._page_timer >= PAGE_SECONDS:
                self._page_timer -= PAGE_SECONDS
                self.page = (self.page + 1) % len(self.pages)
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
        for indent, color_key, text in self.pages[self.page]:
            if y + self.line_h > body_limit:
                break
            if text:
                surface.blit(self.font.render(text, True, c.get(color_key, c["text"])),
                             (self.x + self.PAD + indent, y))
            y += self.line_h

        countdown = "CLOSES IN %ds    [X] TO DISMISS" % max(0, int(self.remaining + 0.5))
        if len(self.pages) > 1:
            countdown = "PAGE %d/%d    %s" % (self.page + 1, len(self.pages),
                                              countdown)
        surface.blit(self.font.render(countdown, True, c["dim"]),
                     (self.x + self.PAD, bottom))
