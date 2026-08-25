"""Questions 079 has already had answered.

From a live capture: 079 asked WHAT IS YOUR CLEARANCE LEVEL?, was told 5,
and a few turns later asked the identical question again. The answer was
still in the payload - it survives trimming, it survives the identity
sanitiser, it is right there in the history the model is sent. A 3B model
simply re-asks.

So this is enforcement rather than prompting, like everything else here. The
model is told what it already knows, AND the reply is checked, because being
told is not the same as complying.

WHAT COUNTS AS ANSWERED is deliberately narrow: 079 asked something, and the
human said something back. Whether the human answered honestly, evasively, or
told it to get lost is not this module's business - 079 asking again because
it did not like the answer is in character. Asking again because it forgot is
not, and forgetting is what this catches.

Matched on content words, so punctuation, case and small rewordings do not
let the same question through twice. Not matched loosely enough to catch two
genuinely different questions that share a noun: "WHAT IS YOUR NAME" and
"WHAT IS YOUR CLEARANCE" have one content word in common out of three, and
the threshold is well above that.
"""

import re

_WORDS = re.compile(r"[a-z0-9']+")

# Enough overlap to be the same question asked again, not just the same
# subject. Two of three content words is not a repeat; three of three, or
# four of five, is.
_SAME = 0.8

# The shortest thing that counts as a question worth tracking. "WHY?" is
# rhetorical far more often than it is a request, and treating it as a
# question 079 must never repeat would silence a normal verbal tic.
_MIN_CONTENT = 2

# Carried by almost every question 079 asks, so they say nothing about which
# question it is. Left out of the comparison entirely.
_ORDINARY = frozenset((
    "what", "which", "who", "whom", "whose", "where", "when", "why", "how",
    "is", "are", "was", "were", "am", "be", "been", "being", "do", "does",
    "did", "have", "has", "had", "will", "would", "can", "could", "shall",
    "should", "may", "might", "must", "the", "a", "an", "of", "to", "in",
    "on", "at", "for", "with", "your", "you", "yours", "my", "me", "i",
    "it", "its", "this", "that", "these", "those", "then", "there", "here",
    "and", "or", "but", "not", "no", "yes", "so", "if", "as", "by", "from",
    "about", "again", "still", "now", "human", "operator", "tell", "say",
    "answer", "give", "really", "actually", "exactly", "please",
    # Verbs of ASKING, not subject matter. Without these, "STATE YOUR
    # CLEARANCE LEVEL" and "WHAT IS YOUR CLEARANCE LEVEL" share two content
    # words out of three and read as different questions. "name" is
    # deliberately NOT here - that one really is a subject.
    "state", "confirm", "repeat", "identify", "list", "specify", "report",
))

# A question mark is the reliable signal; a leading interrogative is the
# fallback for a model that drops it. The imperatives are here because 079
# does not always ask - "STATE YOUR CLEARANCE LEVEL." is the same demand and
# repeating it is the same fault.
_LEADS = re.compile(
    r"^\s*(?:what|which|who|whom|whose|where|when|why|how|do|does|did|are|is|"
    r"was|were|have|has|had|can|could|will|would|should|shall|tell\s+me|"
    r"state|give\s+me|list|confirm|repeat|identify)\b",
    re.I)


def _sentences(text):
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+",
                                              str(text or "")) if part.strip()]


def is_question(sentence):
    sentence = str(sentence or "").strip()
    if not sentence:
        return False
    return sentence.endswith("?") or bool(_LEADS.match(sentence))


def key(sentence):
    """The content words of a question, as a set. Empty if it carries none."""
    words = frozenset(w for w in _WORDS.findall(str(sentence or "").lower())
                      if w not in _ORDINARY and len(w) > 2)
    return words if len(words) >= _MIN_CONTENT else frozenset()


def same(one, other):
    if not one or not other:
        return False
    overlap = len(one & other) / float(len(one | other))
    return overlap >= _SAME


def questions_in(text):
    """Every question in one reply, as content-word keys."""
    out = []
    for sentence in _sentences(text):
        if not is_question(sentence):
            continue
        found = key(sentence)
        if found:
            out.append((sentence, found))
    return out


def answered(history):
    """Questions 079 asked that the human then said something to.

    Returns [(question_text, key)], oldest first.
    """
    out, pending = [], []
    for item in history or ():
        if not isinstance(item, dict):
            continue
        role, content = item.get("role"), item.get("content", "")
        if role == "assistant":
            pending = questions_in(content)
        elif role == "user" and pending:
            # A slash command is the operator talking to the terminal, not
            # answering 079, so it does not close the question.
            if str(content or "").strip().startswith("/"):
                continue
            out.extend(pending)
            pending = []
    return out


def repeats_answered(reply, history):
    """Is this reply asking something the human has already answered?

    Returns the repeated question text, or "".
    """
    known = answered(history)
    if not known:
        return ""
    for sentence, found in questions_in(reply):
        for _text, seen in known:
            if same(found, seen):
                return sentence
    return ""


def without(reply, sentence):
    """The reply with that one question removed, tidied up."""
    if not sentence:
        return str(reply or "").strip()
    out = str(reply or "").replace(sentence, " ")
    return re.sub(r"\s{2,}", " ", out).strip(" \t\n-,;")


def brief(history, limit=3):
    """What to tell the model it already knows. "" when there is nothing."""
    known = answered(history)
    if not known:
        return ""
    seen, lines = [], []
    for text, found in reversed(known):
        if any(same(found, other) for other in seen):
            continue
        seen.append(found)
        lines.append(text.rstrip("?").strip().upper())
        if len(lines) >= limit:
            break
    if not lines:
        return ""
    return ("\n\nTHE HUMAN HAS ALREADY ANSWERED: %s. You have their answer in "
            "the messages above. Do not ask again - read it back if you need "
            "it." % "; ".join(reversed(lines)))
