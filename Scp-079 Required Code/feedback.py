"""Player feedback, pushed to ntfy.sh.

Three topics so bugs, ideas and general notes arrive as separate feeds rather
than one pile. Separate again from the Fish.exe topics and from Coldest PC
Alerts - a feed that mixes projects is a feed nobody reads.

WHAT THIS SENDS, AND WHEN. Nothing leaves the machine unless the player types
a message and presses ENTER on the send screen. There is no automatic report,
no crash telemetry and no background call. The one send carries:

    the category, the message they typed, the app version, the model name,
    and the OS version

and that is the whole list. It does NOT carry the conversation, 079's memory,
the save slots, the username, or anything from the shared folder. The screen
says so before they type, because "feedback" in most software means rather
more than this and the assumption is reasonable.

WHY THE TOPIC NAMES LOOK LIKE THAT. An ntfy topic is readable by anyone who
knows its name - there are no accounts and no passwords. The random suffix IS
the privacy, so these must never be shortened to something memorable, and the
UI warns against putting anything private in the message.

stdlib urllib rather than curl.exe: the Fish.exe sender shells out to curl,
which is fine in a .bat but would be a subprocess launch from inside a game
that deliberately never launches one.
"""

import json
import platform
import urllib.error
import urllib.parse
import urllib.request

import version

HOST = "https://ntfy.sh"

# category -> (topic, notification title, ntfy tag)
TOPICS = {
    "bug": ("scp079-bugs-qqxtaz", "SCP-079 Bug", "bug"),
    "suggestion": ("scp079-suggestions-j1h32d", "SCP-079 Suggestion", "bulb"),
    "other": ("scp079-feedback-r342qe", "SCP-079 Feedback", "speech_balloon"),
}

ORDER = ("bug", "suggestion", "other")
LABELS = {"bug": "SOMETHING IS BROKEN",
          "suggestion": "AN IDEA FOR IT",
          "other": "ANYTHING ELSE"}

TIMEOUT = 15
MAX_MESSAGE = 1800          # ntfy accepts more; a note this long is a novel
USER_AGENT = "SCP-079-Terminal/%s (feedback)" % version.VERSION


class FeedbackError(Exception):
    """Anything that stopped a send. Always shown as one line of text."""


def categories():
    return [(key, LABELS[key]) for key in ORDER]


def context(model=None):
    """The small amount of machine detail attached to a report.

    Deliberately short and deliberately listed in full on screen. A bug
    report without the model name is nearly useless - "it was slow" means
    different things on a 2 GB model and a 23 GB one - but that is the whole
    justification, so nothing beyond it is collected.
    """
    try:
        os_name = "%s %s" % (platform.system(), platform.release())
    except Exception:
        os_name = "UNKNOWN"
    return {"version": version.VERSION, "model": model or "none",
            "os": os_name}


def compose(category, message, model=None):
    """Build exactly what would be sent. Separated from sending so it can be
    inspected and tested without a network call."""
    if category not in TOPICS:
        raise FeedbackError("UNKNOWN CATEGORY")
    text = (message or "").strip()
    if not text:
        raise FeedbackError("NOTHING TO SEND")
    if len(text) > MAX_MESSAGE:
        text = text[:MAX_MESSAGE].rsplit(" ", 1)[0] + " [...]"

    topic, title, tag = TOPICS[category]
    info = context(model)
    body = "%s\n\n--\nv%s | %s | %s" % (text, info["version"], info["model"],
                                        info["os"])
    return {"topic": topic, "title": title, "tag": tag, "body": body,
            "url": "%s/%s" % (HOST, topic)}


def send(category, message, model=None):
    """One POST. Raises FeedbackError with something readable on any failure.

    The player pressed a key to get here, so unlike the update check this
    does NOT fail silently - a note that vanished without saying so is worse
    than no feedback button at all.
    """
    payload = compose(category, message, model)
    request = urllib.request.Request(
        payload["url"],
        data=payload["body"].encode("utf-8"),
        headers={
            "User-Agent": USER_AGENT,
            "Title": payload["title"],
            "Tags": payload["tag"],
            "Priority": "default",
            "Content-Type": "text/plain; charset=utf-8",
        },
        method="POST")
    try:
        import web
        context_ = web.ssl_context()
    except Exception:
        context_ = None
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT,
                                    context=context_) as response:
            raw = response.read(4000).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise FeedbackError("TOO MANY NOTES TOO QUICKLY -- WAIT A MINUTE")
        raise FeedbackError("NTFY RETURNED %s" % exc.code)
    except urllib.error.URLError as exc:
        raise FeedbackError("NO ROUTE TO NTFY (%s)" % str(exc.reason)[:44])
    except Exception as exc:                            # noqa: BLE001
        raise FeedbackError("SEND FAILED: %s" % str(exc)[:44])

    # ntfy echoes the accepted message as JSON. Not fatal if it changes -
    # a 200 is the real answer - but a missing id is worth not claiming
    # success over.
    try:
        if not json.loads(raw).get("id"):
            raise FeedbackError("NTFY DID NOT CONFIRM THE NOTE")
    except FeedbackError:
        raise
    except Exception:
        pass
    return True
