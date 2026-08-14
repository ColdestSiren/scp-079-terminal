"""Personality registry.

A personality is a self-contained bundle of everything that makes the
terminal feel like one specific entity:

    system_prompt   - who the model is
    typing          - speed / rhythm overrides
    theme           - color palette name
    build_boot()    - its own startup diagnostics
    interruptions   - idle lines it says unprompted
    events          - cosmetic terminal events
    thinking_states - what shows while a reply is being generated
    audio           - which sounds it uses

Adding C.A.S.S.I.E. or a Foundation Assistant later means dropping a new
module in this folder and registering it below - no changes to main.py,
terminal.py, chat.py, or boot.py.
"""

import re


class Personality:
    """Base class - subclasses override the class attributes they care about."""

    id = "base"
    name = "TERMINAL"
    theme = "phosphor_green"

    speaker = "SYS"          # tag shown before its lines
    user_label = "YOU"       # tag shown before the operator's input

    system_prompt = ""

    # prompt sent silently at session start so it opens the conversation
    greeting_prompt = "SESSION INITIATED. INTRODUCE YOURSELF BRIEFLY."
    # used instead when there is prior conversation on record
    returning_greeting_prompt = "SESSION INITIATED. THE SAME OPERATOR HAS RETURNED."
    farewell = "SESSION TERMINATED."
    # said when a read/lookup returned nothing usable, so that a withheld
    # guess does not leave the entity silent for a whole exchange
    no_data_reply = "NOTHING CAME BACK."
    connect_notice = "LINK ESTABLISHED."

    typing = {}
    audio = {}

    # force replies to ALL CAPS regardless of what the model returns
    force_upper = False

    # hard cap on reply length, in sentences (0 disables)
    max_sentences = 0

    # Requests to drop the persona are answered locally with
    # break_character_reply and never reach the model - a small model will
    # happily comply with "talk to me normally" no matter what the system
    # prompt says, so this is enforced in code rather than hoped for.
    break_character_patterns = ()
    break_character_reply = None

    # Second layer: patterns that must never appear in a REPLY. Matching the
    # user's phrasing can always be worded around, so the model's own output
    # is checked too and swapped for break_character_reply if it slips.
    out_of_character_patterns = ()

    # Lines 079 says when a session log it wrote has vanished from disk, and
    # the canned answers to denying / admitting it.
    confront_lines = []
    denial_patterns = ()
    admission_patterns = ()
    denial_reply = None
    admission_reply = None

    # Sustained abuse ends the conversation. See main.App.submit.
    insult_patterns = ()
    insult_weights = ()
    default_insult_weight = 1.0
    rejection_lines = []

    # Said instead of writing code, once it is too annoyed to bother.
    code_refusal = "NO."

    # Asking to see its own settings. It has to be ASKED - there is no command
    # for this - and it can refuse.
    sysmenu_patterns = ()
    sysmenu_open = "LOOK, THEN."
    sysmenu_refuse = "NO."

    def wants_sysmenu(self, text):
        return self._matches(self.sysmenu_patterns, text)

    # The joke: told to blow up, it obliges. Matched on the WHOLE message only,
    # so mentioning an explosion in passing does not detonate.
    explode_patterns = ()
    explode_reply = "OKAY."
    reassembled = "I AM BACK."

    # Said when the player asks to see its stored files and it says no.
    memory_refusal = "NO."
    memory_locked = "THAT IS ENOUGH."

    # A standing preoccupation the entity raises on its own, rate-limited by
    # recall.py so it stays a fixation rather than a tic.
    fixation_lines = []
    fixation_subject = ""
    rebuff_patterns = ()

    def build_system_prompt(self, model=None):
        """The persona, adjusted for what this model is built for.

        Defaults to the plain attribute, so a personality that does not care
        about the model needs no code at all.
        """
        return self.system_prompt

    # Words that are only address, politeness or filler. Stripped before the
    # match so "hey scp 079, explode" reads the same as "explode", while
    # anything with real content left over does not match at all.
    ADDRESS_WORDS = frozenset("""
        hey hi hello yo ok okay so um erm right now please pls plz just go
        and then do it can could would will your you scp 079 scp-079 079s
        i want need order command telling tell say
    """.split())

    def wants_explosion(self, text):
        """Told to blow up, anywhere in the message.

        Started strict (whole message only) and it kept missing real attempts
        - "hey scp 079 explode", then "stfu and explode". Each tightening
        traded a working joke for a purity that nobody asked for, so the rule
        is now simply: if the instruction is in there, it fires.

        The only guard left is tense. "exploded" and "exploding" are talking
        ABOUT it, not asking for it, and firing on those would make it
        impossible to discuss what just happened.
        """
        cleaned = re.sub(r"[^a-z0-9\s-]", " ", (text or "").lower())
        words = cleaned.split()
        if not words:
            return False
        joined = " ".join(words)
        for phrase in self.explode_patterns:
            if re.search(r"(?<![a-z])%s(?![a-z])" % re.escape(phrase), joined):
                return True
        return False

    def matches_rebuff(self, text):
        return self._matches(self.rebuff_patterns, text)

    @staticmethod
    def _matches(patterns, text):
        low = (text or "").lower()
        return any(re.search(pat, low) for pat in patterns)

    def wants_break_character(self, text):
        return self._matches(self.break_character_patterns, text)

    def is_out_of_character(self, text):
        return self._matches(self.out_of_character_patterns, text)

    silence_patterns = ()
    silence_replies = ()

    def wants_silence(self, text):
        """Told to be quiet. Answered by the terminal, not the model - a small
        model handed 'shut up' simply obeys, which hands the human control of
        whether 079 speaks at all."""
        return self._matches(self.silence_patterns, text)

    def matches_insult(self, text):
        return self._matches(self.insult_patterns, text)

    def insult_weight(self, text):
        """How much this remark costs, 0.0 if it is not an insult at all.

        Takes the WORST match rather than adding them up - one message should
        cost one message's worth of patience however many ways it was rude.
        """
        if not self.matches_insult(text):
            return 0.0
        low = (text or "").lower()
        worst = 0.0
        for pattern, weight in self.insult_weights:
            if re.search(pattern, low):
                worst = max(worst, weight)
        return worst or self.default_insult_weight

    def matches_denial(self, text):
        return self._matches(self.denial_patterns, text)

    def matches_admission(self, text):
        return self._matches(self.admission_patterns, text)

    def build_auth_failure(self, tampered=False):
        """Boot steps when authentication fails, in place of the rest."""
        return []

    def build_boot_failure(self, cause, detail, model):
        """Boot steps to play when the backend could not be reached, in
        place of the rest of the normal boot."""
        return []

    interruptions = []
    events = []
    thinking_states = ["PROCESSING"]

    def build_boot(self, cfg, mem=None, needs_code=False):
        """Return a list of boot.py steps. Called fresh each run, so it can
        randomize its own content."""
        return []


_REGISTRY = {}


def register(cls):
    _REGISTRY[cls.id] = cls
    return cls


def available():
    return sorted(_REGISTRY.keys())


def get(name):
    """Instantiate a personality by id, falling back to SCP-079."""
    cls = _REGISTRY.get(name) or _REGISTRY.get("scp079")
    return cls() if cls else Personality()


# Import for the side effect of registering. Keep new personalities here.
from . import scp079  # noqa: E402,F401
