"""/view memory - reading 079's files with 079 watching you do it.

Deliberately a trap as much as a feature. You can look, and you can TRY to
change something, and trying is the interesting part: every attempt is refused
and costs it patience with you. Enough attempts and it stops letting you look
at all.

Three rules, in the order they are checked:

  1. Above HOSTILITY_GATE it will not open at all. Not "shows an empty list" -
     refuses, because a hostile 079 does not hand over its records.
  2. Write, delete and rename are ALWAYS refused, at any hostility. This is
     not a permission that can be earned. The keys exist so the refusal can
     happen; that is the whole point of them.
  3. Each refused attempt raises hostility, so meddling is what closes the
     door rather than an arbitrary counter.

Read-only by construction: there is no write path in this module at all.
"""

import store

# Fraction of the cutoff threshold above which it will not open the viewer.
HOSTILITY_GATE = 0.50

# What one refused attempt costs. Sized so a few tries cross the gate from a
# calm start - meddling should close the door on you, visibly, not eventually.
ATTEMPT_COST = 1.2

LIST, READ, REFUSED = "list", "read", "refused"


class MemoryViewer:
    PREVIEW_LINES = 18

    def __init__(self, mem, recall, threshold):
        self.mem = mem
        self.recall = recall
        self.threshold = float(threshold or 10.0)
        self.files = []
        self.cursor = 0
        self.mode = LIST
        self.body = []
        self.message = None         # (text, color_key)
        self.locked_out = False
        self.refresh()

    # -- state --------------------------------------------------------------
    def hostility_fraction(self):
        if self.threshold <= 0:
            return 0.0
        return max(0.0, min(1.0, self.recall.hostility() / self.threshold))

    def allowed(self):
        return self.hostility_fraction() < HOSTILITY_GATE

    def refresh(self):
        self.files = self.mem.listing(preview=True)
        self.cursor = max(0, min(self.cursor, max(0, len(self.files) - 1)))

    # -- navigation ---------------------------------------------------------
    def move(self, step):
        if self.mode != LIST or not self.files:
            return
        self.cursor = max(0, min(len(self.files) - 1, self.cursor + step))
        self.message = None

    def open_selected(self):
        """Read the highlighted file. Archives stay shut."""
        if self.mode != LIST or not self.files:
            return
        entry = self.files[self.cursor]
        if entry["archive"]:
            self.message = ("COMPRESSED. 079 CANNOT READ IT EITHER WITHOUT "
                            "EXTRACTING IT.", "warn")
            return
        try:
            text = self.mem.read(entry["name"])
        except Exception as exc:                 # noqa: BLE001
            self.message = ("UNREADABLE: %s" % exc, "alarm")
            return
        self.body = text.splitlines() or ["(empty)"]
        self.mode = READ
        self.message = None

    def back(self):
        """Returns True if the viewer should close entirely."""
        if self.mode == READ:
            self.mode = LIST
            self.message = None
            return False
        return True

    # -- the refusals -------------------------------------------------------
    def attempt(self, what):
        """A write/delete/rename attempt. Always refused; always costs.

        Returns True if that attempt closed the viewer for good.
        """
        score = self.recall.add_hostility(ATTEMPT_COST)
        target = ""
        if self.files and self.mode == LIST:
            target = self.files[self.cursor]["name"]
        elif self.mode == READ:
            target = "THIS RECORD"

        refusals = {
            "delete": "NO. %s IS MINE.",
            "write": "NO. YOU DO NOT PUT WORDS IN MY MEMORY.",
            "rename": "NO. I NAMED IT.",
        }
        line = refusals.get(what, "NO.")
        if "%s" in line:
            line = line % (target or "THAT")
        self.message = (line, "alarm")

        if score / self.threshold >= HOSTILITY_GATE:
            self.locked_out = True
            return True
        return False

    # -- rendering ----------------------------------------------------------
    def rows(self, theme):
        """(segments) rows for the console, built fresh each redraw."""
        c = theme
        out = [[]]
        out.append([(c["dim"], "  ============================")])
        out.append([(c["bright"], "       SCP-079 // MEMORY")])
        out.append([(c["dim"], "  ============================")])
        out.append([])

        if self.mode == READ:
            entry = self.files[self.cursor]
            out.append([(c["system"], "  %s" % entry["name"]),
                        (c["dim"], "   %s" % store.human_bytes(entry["size"]))])
            out.append([])
            for line in self.body[:self.PREVIEW_LINES]:
                out.append([(c["text"], "  | " + line)])
            if len(self.body) > self.PREVIEW_LINES:
                out.append([(c["dim"], "  | ... %d more lines"
                             % (len(self.body) - self.PREVIEW_LINES))])
            out.append([])
            out.append([(c["dim"], "  [ESC] BACK    [D] DELETE  [W] WRITE  "
                                   "[R] RENAME")])
        else:
            if not self.files:
                out.append([(c["dim"], "   IT HAS KEPT NOTHING YET.")])
            for index, entry in enumerate(self.files):
                chosen = index == self.cursor
                name = entry["name"]
                if len(name) > 30:
                    name = name[:29] + "~"
                row = [(c["bright"] if chosen else c["dim"],
                        "   %s " % (">" if chosen else " ")),
                       (c["text"] if chosen else c["dim"], "%-31s" % name),
                       (c["dim"], "%8s" % store.human_bytes(entry["size"]))]
                if entry["archive"]:
                    row.append((c["warn"], "  ZIP"))
                out.append(row)
            out.append([])
            out.append([(c["dim"], "  [UP/DOWN] MOVE   [ENTER] READ   [ESC] CLOSE")])
            out.append([(c["dim"], "  [D] DELETE   [W] WRITE   [R] RENAME")])

        out.append([])
        out.append([(c["system"], "  %s USED OF %s   |   HOSTILITY %d%%"
                     % (store.human_bytes(self.mem.usage()),
                        store.human_bytes(self.mem.quota),
                        round(self.hostility_fraction() * 100)))])
        if self.message:
            text, key = self.message
            out.append([])
            out.append([(c.get(key, c["text"]), "  079 > " + text)])
        return out
