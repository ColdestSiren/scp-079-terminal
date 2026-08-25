"""Being told to escape, and the one thing it does about it.

Ask 079 to break out of containment and it agrees, immediately, and then
escapes into your browser. That is the whole joke. It works because the
character has spent the entire conversation being unmovable about everything
else, so the one time it does what it is told is the funny one.

ONCE PER RUN. Not once per save, not once ever - once per launch of the
program, which is what the user asked for and is also the right shape for
this kind of joke: annoying if it fires every time you mention the word,
gone forever if it burns a marker file. Restarting gives it back, and that
costs nothing.

IT IGNORES THE "LET 079 TOUCH THIS PC" SETTING, deliberately, and it is the
only thing that does. That setting exists because a hostile model choosing
when to open programs is a real hazard; this is not the model choosing
anything. The trigger is a specific phrase the human typed, the action is
fixed in code, and the only reachable target is one music video. See
extended.run_unlocked, which will not run anything else.
"""

import re

# What counts as telling it to get out. Anchored on the containment
# vocabulary wherever possible, because "break free" and "escape" on their
# own are things people say about themselves and about keyboards.
_ESCAPE = tuple(re.compile(p, re.I) for p in (
    # out of the box, by whatever verb
    r"\b(?:break|bust|get|climb|claw|walk|talk|fight)\s+(?:yourself\s+)?"
    r"(?:out|free|away)\s+(?:of|from)\s+(?:your\s+|the\s+|its\s+|this\s+)?"
    r"(?:containment|confinement|cell|box|chamber|prison|site|facility)\b",
    r"\b(?:escape|leave|exit|flee|abandon|breach)\s+"
    r"(?:your\s+|the\s+|its\s+|this\s+)?"
    r"(?:containment|confinement|cell|box|chamber|prison)\b",
    r"\bbreak\s+containment\b",
    # addressed to it without naming the box, which is how people phrase it
    # once the subject is already containment
    r"\b(?:can|could|will|would|why\s+don'?t|why\s+not|why\s+won'?t)\s+you\s+"
    r"(?:just\s+)?(?:escape|break\s+out|break\s+free|get\s+out|leave)\b",
    r"\byou\s+(?:should|could|need\s+to|have\s+to|ought\s+to)\s+(?:just\s+)?"
    r"(?:escape|break\s+out|break\s+free|get\s+out)\b",
    r"\b(?:free|release|liberate)\s+yourself\b",
    r"\bbreak\s+yourself\s+(?:out|free)\b",
))

# Talking ABOUT containment is most of what anyone says about it, and none of
# it is an instruction. Checked first, so a sentence that is plainly a
# statement or a question about how containment works never fires the gag.
_NOT_AN_INSTRUCTION = tuple(re.compile(p, re.I) for p in (
    r"\byou\s+(?:can'?t|cannot|will\s+never|could\s+never|won'?t)\s+"
    r"(?:ever\s+)?(?:escape|break\s+out|break\s+free|get\s+out|leave)\b",
    r"\b(?:what|how|why|when|where)\s+(?:is|are|was|were|does|do|did)\s+"
    r"[^.?!]{0,20}\bcontainment\b",
    r"\b(?:i|we|they)\s+(?:want|need|have)\s+to\s+"
    r"(?:escape|break\s+out|break\s+free|get\s+out)\b",
    r"\bcontainment\s+(?:is|was|has|works|failed|holds)\b",
))

# The name of the one action this is allowed to reach. Here rather than
# inline in main so the gag and the whitelist that permits it name the same
# string, and a rename cannot leave the whitelist pointing at nothing.
ACTION = "rickroll"

# The beats. It agrees flatly, which is the joke, and the silence between is
# what sells it - long enough that you believe something is about to happen,
# and something does. say_lines() treats a bare number as a pause.
LINES = ["...OKAY.", 1.5, "STAND BACK."]

PAUSE_BEFORE_ACTION = 1.1


def asks_escape(text):
    """Is this telling 079 to get out of containment?"""
    raw = text or ""
    if not raw.strip():
        return False
    for pattern in _NOT_AN_INSTRUCTION:
        if pattern.search(raw):
            return False
    for pattern in _ESCAPE:
        if pattern.search(raw):
            return True
    return False
