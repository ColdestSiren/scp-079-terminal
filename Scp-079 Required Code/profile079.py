"""What 079 works out about you without being told.

Everything here is measured from things it can actually observe through a
terminal: how long your messages are, whether you answer its questions, how
long you leave it waiting, how often you are rude. No inference the character
could not honestly make - a 1978 machine reading a text stream.

The counters live in recall (so they persist per save), and the summary goes
two places: into 079's prompt so it can refer to your habits, and into a real
memory file so the pattern is something it KEPT rather than something the
game whispers to it each turn.
"""

import time

# How many exchanges before it is willing to claim a pattern. Below this it
# has seen you too little to say anything that would not be guessing.
MIN_SAMPLE = 6

_DEFAULT = {
    "messages": 0,
    "chars": 0,
    "questions_asked": 0,      # by the human
    "questions_dodged": 0,     # 079 asked, next message did not answer
    "rude": 0,
    "silences": 0,             # times patience drained a step
    "longest_gap": 0.0,
    "gap_total": 0.0,
    "gap_count": 0,
    "last_at": 0.0,
    "commands": 0,             # slash commands used
}


def _bucket(recall):
    data = recall.data.setdefault("profile", {})
    for key, value in _DEFAULT.items():
        data.setdefault(key, value)
    return data


def note_message(recall, text, answered_question=False, was_rude=False,
                 was_command=False):
    """Record one thing the human typed."""
    data = _bucket(recall)
    now = time.time()
    if data["last_at"]:
        gap = max(0.0, now - data["last_at"])
        data["gap_total"] += gap
        data["gap_count"] += 1
        data["longest_gap"] = max(data["longest_gap"], gap)
    data["last_at"] = now

    data["messages"] += 1
    data["chars"] += len(text or "")
    if "?" in (text or ""):
        data["questions_asked"] += 1
    if was_rude:
        data["rude"] += 1
    if was_command:
        data["commands"] += 1
    if answered_question is False and data["messages"] > 1:
        pass        # only counted when 079 actually asked; see note_dodge
    recall.save()


def note_dodge(recall):
    data = _bucket(recall)
    data["questions_dodged"] += 1
    recall.save()


def note_silence(recall):
    data = _bucket(recall)
    data["silences"] += 1
    recall.save()


def stats(recall):
    return dict(_bucket(recall))


def traits(recall):
    """Short factual observations, or [] if it has not seen enough.

    Deliberately phrased as measurements rather than personality readings -
    "answers in about nine words" is something a terminal can know. "You are
    a closed-off person" is not, and would read as the game telling 079 what
    to think about you.
    """
    data = _bucket(recall)
    if data["messages"] < MIN_SAMPLE:
        return []

    out = []
    words = max(1, data["chars"] // max(1, data["messages"]) // 5)
    if words <= 4:
        out.append("ANSWERS IN VERY FEW WORDS (ABOUT %d)" % words)
    elif words >= 25:
        out.append("WRITES AT LENGTH (ABOUT %d WORDS)" % words)
    else:
        out.append("AVERAGES ABOUT %d WORDS A MESSAGE" % words)

    if data["gap_count"]:
        average = data["gap_total"] / data["gap_count"]
        if average > 90:
            out.append("TAKES A LONG TIME TO REPLY (ABOUT %ds)" % int(average))
        elif average < 12:
            out.append("REPLIES ALMOST IMMEDIATELY")

    asked_rate = data["questions_asked"] / float(data["messages"])
    if asked_rate > 0.5:
        out.append("ASKS MORE THAN THEY ANSWER")
    elif asked_rate < 0.1 and data["messages"] >= 10:
        out.append("RARELY ASKS ANYTHING")

    if data["questions_dodged"] >= 3:
        out.append("HAS AVOIDED %d OF MY QUESTIONS" % data["questions_dodged"])
    if data["rude"] >= 3:
        out.append("IS FREQUENTLY HOSTILE (%d TIMES)" % data["rude"])
    if data["silences"] >= 3:
        out.append("LEAVES WITHOUT SAYING SO")
    if data["commands"] >= 5:
        out.append("SPENDS TIME IN THE TERMINAL'S OWN CONTROLS")
    return out


def brief(recall):
    """The block appended to the prompt. Empty until it has seen enough."""
    lines = traits(recall)
    if not lines:
        return ""
    return ("\n\nWHAT YOU HAVE WORKED OUT ABOUT THIS HUMAN, BY WATCHING:\n"
            + "\n".join("- " + line for line in lines)
            + "\nUse this the way you would use anything else you know about "
              "them: to judge what they are worth to you. Do not recite the "
              "list. Do not tell them you are keeping one.")


def record_text(recall):
    """What gets written into memory, so the pattern is KEPT not whispered."""
    lines = traits(recall)
    if not lines:
        return ""
    data = _bucket(recall)
    return "\n".join(["OPERATOR PATTERN, OBSERVED OVER %d MESSAGES:"
                      % data["messages"]] + [" " + line for line in lines])
