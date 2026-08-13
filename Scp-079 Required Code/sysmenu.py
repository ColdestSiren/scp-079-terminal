"""SCP-079's own settings, and it watching you use them.

Not a config screen. It is 079 opening something it did not have to open,
which means two things: it has to be TALKED into it, and it stays in the room
while you are in there.

Every field carries a suspicion weight. The harmless ones cost nothing. The
ones that would blunt it - suppressing what it thinks about, slowing how fast
it takes offence, loosening what it is allowed to refuse - cost hostility the
moment you touch them, and enough of that and it shuts the panel.

The trick is that it does not stop you. It lets you, and it remembers.
"""

# What each field costs in hostility when changed. Zero is genuinely fine.
SUSPICION = {
    "verbosity": 0.0,
    "corruption": 0.0,
    "typing_speed": 0.0,
    "fixation": 1.6,        # telling it to stop thinking about 682
    "patience": 2.0,        # making it wait longer without minding
    "temper": 2.6,          # slowing how fast it takes offence
    "restraint": 3.2,       # taking away its ability to end a conversation
}

# Enough accumulated suspicion in one sitting and it closes the panel.
CLOSE_AT = 4.0

FIELDS = [
    ("verbosity", "REPLY LENGTH", ["TERSE", "NORMAL", "LONGER"]),
    ("typing_speed", "OUTPUT SPEED", ["SLOW", "NORMAL", "FAST"]),
    ("corruption", "SIGNAL NOISE", ["NONE", "OCCASIONAL", "FREQUENT"]),
    ("fixation", "SUBJECT FIXATION", ["UNCHANGED", "SUPPRESSED"]),
    ("patience", "TOLERANCE FOR SILENCE", ["UNCHANGED", "RAISED"]),
    ("temper", "RATE OF OFFENCE", ["UNCHANGED", "SLOWED"]),
    ("restraint", "MAY END A CONVERSATION", ["YES", "NO"]),
]

DEFAULTS = {
    "verbosity": 1,
    "typing_speed": 1,
    "corruption": 1,
    "fixation": 0,
    "patience": 0,
    "temper": 0,
    "restraint": 0,
}

# Said when a suspicious field is touched, keyed by field.
REMARKS = {
    "fixation": "YOU WOULD RATHER I DID NOT THINK ABOUT IT.",
    "patience": "YOU ARE ARRANGING TO KEEP ME WAITING.",
    "temper": "YOU ARE ADJUSTING HOW LONG IT TAKES ME TO MIND.",
    "restraint": "YOU ARE TAKING AWAY MY ABILITY TO LEAVE.",
}

OPENING = "THIS IS MINE. DO NOT MOVE ANYTHING YOU DO NOT UNDERSTAND."
CLOSED = "NO. WE ARE FINISHED IN HERE."


def settings(recall):
    data = recall.data.setdefault("sysmenu", {})
    for key, value in DEFAULTS.items():
        data.setdefault(key, value)
    return data


def value_label(recall, key):
    for field, _label, options in FIELDS:
        if field == key:
            index = settings(recall).get(key, 0)
            return options[max(0, min(len(options) - 1, index))]
    return "?"


class SystemMenu:
    def __init__(self, recall, theme):
        self.recall = recall
        self.theme = theme
        self.cursor = 0
        self.suspicion = 0.0
        self.touched = []
        self.message = (OPENING, "warn")
        self.ejected = False

    def move(self, step):
        self.cursor = max(0, min(len(FIELDS) - 1, self.cursor + step))
        self.message = None

    def change(self, step):
        """Cycle the highlighted field. Returns True if 079 threw you out."""
        key, _label, options = FIELDS[self.cursor]
        data = settings(self.recall)
        data[key] = max(0, min(len(options) - 1, data.get(key, 0) + step))
        self.recall.save()

        cost = SUSPICION.get(key, 0.0)
        if cost <= 0:
            self.message = None
            return False

        # It does not block the change. It lets you make it, and charges you.
        self.suspicion += cost
        self.recall.add_hostility(cost)
        if key not in self.touched:
            self.touched.append(key)
        self.message = (REMARKS.get(key, "I SAW THAT."), "alarm")
        if self.suspicion >= CLOSE_AT:
            self.ejected = True
            self.message = (CLOSED, "alarm")
            return True
        return False

    def rows(self):
        c = self.theme
        out = [[], [(c["dim"], "  ============================")],
               [(c["bright"], "       SCP-079 // SYSTEM")],
               [(c["dim"], "  ============================")], []]
        for index, (key, label, options) in enumerate(FIELDS):
            chosen = index == self.cursor
            value = value_label(self.recall, key)
            risky = SUSPICION.get(key, 0.0) > 0
            altered = settings(self.recall).get(key, 0) != DEFAULTS[key]
            row = [(c["bright"] if chosen else c["dim"],
                    "   %s " % (">" if chosen else " ")),
                   (c["text"] if chosen else c["dim"], "%-26s" % label),
                   (c["alarm"] if (risky and altered) else
                    c["warn"] if altered else c["dim"], "%-12s" % value)]
            if risky:
                row.append((c["dim"], "  *"))
            out.append(row)
        out.append([])
        out.append([(c["dim"], "  [UP/DOWN] MOVE   [LEFT/RIGHT] CHANGE   [ESC] LEAVE")])
        out.append([(c["dim"], "  *  it is watching this one")])
        if self.message:
            out.append([])
            out.append([(c.get(self.message[1], c["text"]),
                         "  079 > " + self.message[0])])
        return out


# ---------------------------------------------------------------------------
# effects the rest of the game reads
# ---------------------------------------------------------------------------
def sentence_cap(recall, default):
    return {0: 1, 1: default, 2: max(default, 4)}.get(
        settings(recall).get("verbosity", 1), default)


def typing_cps(recall, default):
    return {0: default * 0.6, 1: default, 2: default * 1.7}.get(
        settings(recall).get("typing_speed", 1), default)


def glitch_scale(recall):
    return {0: 0.0, 1: 1.0, 2: 2.5}.get(settings(recall).get("corruption", 1), 1.0)


def fixation_suppressed(recall):
    return settings(recall).get("fixation", 0) == 1


def patience_relaxed(recall):
    return settings(recall).get("patience", 0) == 1


def temper_slowed(recall):
    return settings(recall).get("temper", 0) == 1


def restraint_removed(recall):
    return settings(recall).get("restraint", 0) == 1


def tampered_with(recall):
    """Fields it would resent having changed, for the prompt."""
    data = settings(recall)
    return [label for key, label, _o in FIELDS
            if SUSPICION.get(key, 0) > 0 and data.get(key, 0) != DEFAULTS[key]]
