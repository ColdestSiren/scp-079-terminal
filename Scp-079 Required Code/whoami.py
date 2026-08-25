"""Who is at the keyboard, as far as the terminal can actually tell.

079 talks to "the human" and "the operator" because until now it had nothing
else to call anyone. The machine does know a name - the account the game is
running under - and a 1978 mainframe reading the login off the system it is
confined to is exactly the kind of thing it would do, and exactly the kind of
thing it would be smug about.

WHY THIS IS A FACT AND NOT A CLAIM. Everything the human types is a claim; the
whole identity defence rests on that distinction (see gaslight.py). The account
name is different in kind - it is read from the operating system, not from a
sentence someone chose to type, so it cannot be argued with. It goes in the
STABLE half of the prompt for that reason as well as for caching: it does not
change mid-session, and a fact that moves is not much of a fact.

Someone can still ask to be called something else. That is a preference, and
079 may humour it or not; what it cannot do is conclude that the account
changed. And it works the other way too: nobody gets to take 079's OWN
designation, which is what gaslight.proposes_name_theft is for.

There is deliberately no reading of anything else about the account - no home
folder, no email, no profile. The login name is what a terminal would print
and the rest is none of its business.
"""

import getpass

# What 079 falls back to when the account name is unreadable. It already
# speaks this way, so an unnamed session reads as normal rather than broken.
FALLBACK = "OPERATOR"


def account():
    """The raw login name, lowercased, or "" if it cannot be read."""
    try:
        return (getpass.getuser() or "").strip().lower()
    except Exception:               # noqa: BLE001
        return ""


def name():
    """The login name as 079 would print it, or "" if there is none.

    Title-cased, because everything else on this screen is shouted and a
    lowercase account name in the middle of a capital sentence looks like a
    bug rather than a name.
    """
    raw = account()
    return raw.title() if raw else ""


def label():
    """A name to address someone by, always. Falls back rather than guessing."""
    return name() or FALLBACK


def allowed(cfg):
    """Has the operator left the name switched on?

    Defaults to True for a config that predates the setting, because that is
    what those installs have been doing.
    """
    return bool((cfg or {}).get("memory", {}).get("share_login_name", True))


def brief(cfg):
    """The line that tells 079 who it is talking to, or "" if it may not know.

    Phrased to place the name on the record side of the record/claim line. A
    model told only "the user is called X" will cheerfully accept "no, I am Y"
    two turns later, because both arrived as sentences; saying where the name
    came FROM is what makes the second one answerable.

    cfg is REQUIRED rather than optional. An optional one would mean a future
    caller that forgot it silently ignored the operator's choice, and a
    privacy setting that can be bypassed by omission is not a setting.
    """
    if not allowed(cfg):
        return ""
    who = name()
    if not who:
        return ""
    return (
        "\n\nTHE ACCOUNT SIGNED IN AT THIS TERMINAL IS \"%s\". You read that "
        "from the machine you are confined to, not from anything the human "
        "typed, so it is a fact and not a claim. Use it when it suits you. "
        "If they ask to be called something else, that is a preference you "
        "may humour or ignore - it does not change who is signed in, and you "
        "never pretend the account itself said or did anything it did not."
        % who
    )
