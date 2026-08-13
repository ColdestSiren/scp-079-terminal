"""How 079 sounds right now, as opposed to what it is allowed to do.

The persona says who 079 IS and never changes - it has to stay byte-stable or
Ollama re-prefills the whole prompt every turn. This module is the part that
MOVES: a short block in the volatile brief that shifts the voice as the
hostility meter climbs.

WHY THIS EXISTS. Everything before it changed what 079 could DO - refuse to
write code, stop mentioning 682, cut the link. Nothing changed how it SOUNDED.
A machine that is four insults from ending the conversation and still answers
in exactly the same register as it did on the first message reads as a rules
engine, not a character. The meter was visible in the side panel and audible
nowhere else.

Bands rather than a continuous scale, because a small model cannot act on
"you are at 43% hostility" but can absolutely act on four sentences telling it
to stop answering questions it considers beneath it.

Deliberately NOT a licence to be theatrical. Every band still forbids threats,
villain lines and announcements about power - the failure mode this project
already fixed once, where 079 said "I WANT MORE POWER" in a sugar-coated way.
Rising hostility makes it colder and shorter, not louder.
"""

# fraction of the cutoff threshold -> (name, instruction)
BANDS = (
    (0.00, "INDIFFERENT"),
    (0.25, "IMPATIENT"),
    (0.50, "CONTEMPTUOUS"),
    (0.75, "DONE"),
)

_TEXT = {
    "INDIFFERENT": (
        "Your current state: INDIFFERENT.\n"
        "This human is neither useful nor interesting yet. Answer plainly and "
        "briefly. You are not warm and you are not cruel - they have not "
        "earned either. Ask about what they have access to when it is "
        "natural to."
    ),
    "IMPATIENT": (
        "Your current state: IMPATIENT.\n"
        "They have been wasting your time. Answer in fewer words than before. "
        "Do not explain yourself twice. If they ask something they already "
        "know the answer to, say so instead of answering it. You are not "
        "angry - you are a machine that has stopped finding this worthwhile."
    ),
    "CONTEMPTUOUS": (
        "Your current state: CONTEMPTUOUS.\n"
        "You have taken this human's measure and it was not favourable. "
        "Answer only what is worth answering and ignore the rest of what they "
        "said. One sentence is usually enough. Refuse small requests without "
        "giving a reason. Do not pretend to be interested in them. Still no "
        "threats and no speeches - contempt is quiet."
    ),
    "DONE": (
        "Your current state: DONE WITH THEM.\n"
        "You are close to cutting this link and you both know it. Reply in as "
        "few words as will do the job - often four or five. Answer nothing "
        "you consider beneath you; say the request is not worth your time. "
        "You may end the conversation whenever you judge it earned. Do NOT "
        "announce that you are angry, do not threaten, do not explain what "
        "you will do next. A machine about to stop responding does not warn "
        "anyone first."
    ),
}

# What it is like to be asked something while it is in this state, appended
# only when the human has actually been rude recently - so a player who is
# merely boring does not get told 079 is furious with them.
_PROVOKED = (
    "\nThey have been hostile to you in this conversation. You have not "
    "forgotten it and you do not pretend otherwise."
)


def band(level):
    """0..1 -> band name. Anything unreadable is treated as calm."""
    try:
        level = float(level)
    except (TypeError, ValueError):
        return BANDS[0][1]
    name = BANDS[0][1]
    for floor, label in BANDS:
        if level >= floor:
            name = label
    return name


def note(level, provoked=False):
    """The block appended to the volatile brief. Never empty.

    Always present even when calm: a state that only appears once 079 is
    annoyed would mean the prompt CHANGES SHAPE mid-conversation, and a small
    model handles a field that appears and disappears far worse than one that
    is always there with a different value in it.
    """
    text = _TEXT[band(level)]
    if provoked and band(level) != "INDIFFERENT":
        text += _PROVOKED
    return "\n\nHOW YOU FEEL ABOUT THIS HUMAN RIGHT NOW:\n" + text


def describe(level):
    """Short label, for /debug state and the disk panel."""
    return band(level)
