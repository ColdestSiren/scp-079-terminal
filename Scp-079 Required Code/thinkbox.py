"""The reasoning trace, in a box you can shut.

A thinking model writes its deliberation before it writes a word of speech,
and on a long question that is far more text than the answer. Printed straight
into the transcript it buries the conversation: you scroll past a page of the
model talking to itself to find the one line 079 actually said.

So it goes in a frame of its own, like a code block, with an arrow at the top
right. Open, you watch it reason. Shut, it collapses to a single row saying how
much is behind it. Either way the answer stays where you can find it.

WHY THE ROWS ARE MOVED RATHER THAN HIDDEN. The renderer draws whatever the
console holds; there is no per-row visibility flag, and adding one would mean
every other caller had to care about it. Collapsing therefore lifts the body
out of the console and keeps it here, and expanding puts it back between the
same two markers. The trace itself is never lost - it lives on this object for
as long as the box does, whichever way the arrow is pointing.

The markers are the same trick the code frames use: rows drawn in the
background colour, invisible, present only so the renderer can report a Y
position for the top and bottom of something that is otherwise just text.
"""

# The gutter that marks a line as the model thinking rather than speaking.
# Kept here rather than in main so the collapse arithmetic and the printing
# agree on what a body row looks like.
GUTTER = "  | "

# Collapsed summary and the code-block style indent it sits at.
INDENT = "     "

LABEL = "REASONING"

# ASCII, deliberately. The face is whatever monospace font the machine
# happens to have, and pygame falls back to its own when none of the
# candidates exist - a box-drawing triangle is not a safe bet on a face
# nobody chose. "v" and ">" point the right way in any font there is.
OPEN_ARROW = "[ v ]"
SHUT_ARROW = "[ > ]"


def top_marker(index):
    return "─THINK-TOP-%d" % index


def end_marker(index):
    return "─THINK-END-%d" % index


def find_span(rows, top_text, end_text):
    """Where the body of a box sits inside a console row list.

    Returns (first_body_index, stop_index), or None when the top marker has
    been trimmed away by the console's row cap - at which point the box is
    scrolled far into history and there is nothing left to rewrite.

    A MISSING END MARKER IS NORMAL: while the model is still reasoning the
    box has no bottom yet, and the body runs to the end of the transcript.
    """
    top = None
    for i, row in enumerate(rows):
        if row_text(row) == top_text:
            top = i
            break
    if top is None:
        return None
    for j in range(top + 1, len(rows)):
        if row_text(rows[j]) == end_text:
            return top + 1, j
    return top + 1, len(rows)


def splice(rows, top_text, end_text, body):
    """Replace a box's body in place. True if the box was found."""
    span = find_span(rows, top_text, end_text)
    if span is None:
        return False
    start, stop = span
    rows[start:stop] = list(body)
    return True


def row_text(row):
    if isinstance(row, tuple):
        return row[1]
    return "".join(part for _, part in row)


class ThinkBox:
    """One reasoning trace and whether you are currently looking at it."""

    def __init__(self, index, open_now=True):
        self.index = index
        self.lines = []
        self.open = bool(open_now)
        # Set when generation finishes. An unfinished box has no end marker
        # in the console, which is what tells the frame to run to the bottom
        # of the screen rather than close early.
        self.done = False

    # -- the trace ----------------------------------------------------------
    def add(self, line):
        line = (line or "").strip()
        if line:
            self.lines.append(line)
        return bool(line)

    def __len__(self):
        return len(self.lines)

    # -- what the console should hold ---------------------------------------
    def body(self, color_line, color_note):
        """The rows that belong between this box's markers, as it stands."""
        if self.open:
            return [(color_line, GUTTER + line) for line in self.lines]
        if not self.lines:
            return []
        return [(color_note, self.summary())]

    def summary(self):
        count = len(self.lines)
        return "%s[ %d LINE%s HIDDEN ]" % (INDENT, count,
                                           "" if count == 1 else "S")

    def arrow(self):
        return OPEN_ARROW if self.open else SHUT_ARROW

    def toggle(self):
        self.open = not self.open
        return self.open
