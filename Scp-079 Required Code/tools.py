"""The commands 079 can issue, and the parser that pulls them out of a reply.

Deliberately NOT JSON function-calling. llama3.2:1b/3b cannot hold a JSON
schema together across a reply - they emit half-objects, prose-wrapped
braces, or forget the call entirely. A one-line grammar is something a 1B
model can actually produce:

    >>LIST
    >>WRITE notes.txt | THE HUMAN SAID THEY WORK NIGHTS
    >>APPEND notes.txt | THEY LIED ABOUT THE LOG
    >>READ notes.txt
    >>DELETE notes.txt
    >>ZIP old | notes.txt, humans.txt
    >>UNZIP old.zip

Command lines are stripped from the reply before it is displayed, so the
player sees 079 speak, then sees the disk light up - not the raw syntax.

Anything that comes back from a command is fed to the model as an explicitly
labelled MEMORY SYSTEM message, never as the human talking.
"""

import re

import sanitize
import shared as _shared
import store

# Any '>>VERB' anywhere in the text starts a command. Deliberately NOT
# anchored to the start of a line - see parse() for the three real failures
# that anchoring caused in play.
VERBS = ("LIST", "WRITE", "APPEND", "READ", "DELETE", "RENAME",
         "ZIP", "UNZIP", "CUTOFF", "PLAY", "LOOKUP", "SHARED", "OPEN",
         "STATUS", "DO")

# Two arrows: anything following is treated as an attempted command, so an
# invented verb is reported to the player rather than spoken.
#
# ONE arrow: only a REAL verb counts. Models drop an arrow constantly - real
# play produced ">WRITE NOTES.TXT | YOU ARE WRONG ABOUT MY IDENTITY." and
# ">WRITE MAYA.FEY.", both of which were read out as dialogue, syntax and
# all. Accepting any word after a single ">" would be worse than the problem
# though: it would silently swallow ordinary speech that happens to begin
# with one. Requiring a known verb makes the recovery safe.
_CMD_ANY = re.compile(
    r"(?:>>\s*([A-Za-z_]+)|(?<!>)>\s*(%s)\b)[ \t]*" % "|".join(VERBS),
    re.IGNORECASE)

# 079 may end the conversation itself, but not immediately - it has to have
# actually been in the conversation first. The app owns the session clock, so
# it does the gating; these are the numbers it enforces.
CUTOFF_FLOOR_SECONDS = 300.0     # 5 minutes before it may cut off at will
CUTOFF_MAX_MINUTES = 60.0        # and never longer than an hour
CUTOFF_DEFAULT_MINUTES = 15.0

# Commands whose whole point is getting information back. These earn one
# follow-up generation so 079 can actually use what it just read, instead of
# saying "let me check" and going silent until the next user message.
READ_VERBS = ("LIST", "READ", "LOOKUP", "SHARED", "OPEN", "STATUS")

# Flagged for the player's awareness, never blocked - 079 is allowed to write
# whatever it wants, the human just gets told when it is something personal.
_SENSITIVE = re.compile(
    r"\b(password|passwd|credit card|social security|ssn|address|phone number|"
    r"bank|routing number|home address|real name|medical|diagnosis|therapist|"
    r"suicide|self harm|kill myself)\b", re.IGNORECASE)


class Command:
    __slots__ = ("verb", "target", "body", "raw")

    def __init__(self, verb, target, body, raw):
        self.verb = verb
        self.target = target
        self.body = body
        self.raw = raw

    def __repr__(self):
        return "Command(%s, %r, %r)" % (self.verb, self.target, self.body)


def parse(reply):
    """Split a reply into what 079 says and what 079 does.

    Returns (spoken_text, [Command], [unknown_verbs]).

    Commands are found ANYWHERE in the text, not just at the start of a line.
    That is not politeness towards sloppy models, it is required: in real play
    the models produced all three of these, and a line-anchored parser got
    every one of them wrong.

        DONE. >>WRITE humans.txt | I MADE THIS
            -> spoken as raw syntax, because the command was not at column 0

        >>WRITE obs.txt" >>APPEND obs.txt | LOGGED 049
            -> one command with the filename 'obs.txt" >>APPEND obs.txt'

        >>ACCESS GRANTED: www.005
            -> an invented verb, read out loud as if 079 had said it

    So: split on every '>>', run a command's argument to the next '>>' or the
    end of the line, and never let anything starting with '>>' reach speech -
    an invented verb is reported to the player as a rejected command, not
    spoken.
    """
    text = reply or ""
    spoken, commands, unknown = [], [], []
    pos = 0

    for match in _CMD_ANY.finditer(text):
        if match.start() < pos:
            continue                    # inside the previous command's body
        spoken.append(text[pos:match.start()])
        # group 1 is the ">>anything" form, group 2 the ">KNOWNVERB" one
        verb = (match.group(1) or match.group(2) or "").upper()

        rest = text[match.end():]
        stops = [i for i in (rest.find(">>"), rest.find("\n")) if i != -1]
        end = min(stops) if stops else len(rest)
        arg = rest[:end].strip().strip("`").strip()
        pos = match.end() + end

        if verb not in VERBS:
            unknown.append(verb)
            continue

        if "|" in arg:
            target, _, body = arg.partition("|")
        else:
            # the pipe gets dropped constantly - take the first token as the
            # filename and the remainder as the content rather than refusing
            parts = arg.split(None, 1)
            target = parts[0] if parts else ""
            body = parts[1] if len(parts) > 1 else ""
        target = target.strip().strip('"').strip("'").strip()
        commands.append(Command(verb, target, body.strip().strip('"').strip(),
                                match.group(0) + arg))

    spoken.append(text[pos:])
    out = re.sub(r"\n{3,}", "\n\n", "".join(spoken))
    out = re.sub(r"[ \t]{2,}", " ", out).strip()
    return clean_speech(out), commands, unknown


# ---------------------------------------------------------------------------
# Scrubbing the model's own scaffolding out of its speech
# ---------------------------------------------------------------------------
# Everything here was seen ON SCREEN in real play. A small model does not
# reliably tell the difference between "text I was given" and "text I should
# say", so anything the game feeds it can come back out of its mouth. The
# prompt asks it not to; this is the part that does not rely on asking.

# A bare ">" at the start of a line. The model sees "079 > " as the speaker
# prefix in its own history and starts producing the ">" itself, so every
# line came out as ">THAT IS CORRECT." Genuine >>COMMANDS are already gone by
# the time this runs, so a surviving ">" is always leakage.
_LEAD_ARROW = re.compile(r"(?m)^[ \t]*>+[ \t]*")

# The [004] stamps that auto-notes put on lines in observations.txt, so the
# file reads as a record kept over time. 079 reads that file back and then
# recites the stamps: ">[004] NUGGET [006] DONT YOU REMEMBER?"
_STAMP = re.compile(r"\[\s*\d{1,4}\s*\]")

# Verbatim scaffolding. These are strings the GAME writes into the model's
# context, so seeing them in the model's output means it is reading its
# instructions aloud. Matched case-insensitively and whole-phrase.
_SCAFFOLD = (
    "ANSWER THE HUMAN USING THE RECORD ABOVE. DO NOT SAY IT IS EMPTY - IT IS RIGHT THERE.",
    "ANSWER THE HUMAN USING THE RECORD ABOVE.",
    "DO NOT SAY IT IS EMPTY - IT IS RIGHT THERE.",
    "[MEMORY SYSTEM -- THIS IS NOT THE HUMAN SPEAKING]",
    "THIS IS NOT THE HUMAN SPEAKING",
    "NOT THE HUMAN SPEAKING",
)
_SCAFFOLD_RE = re.compile(
    "|".join(re.escape(s) for s in _SCAFFOLD), re.IGNORECASE)


def clean_speech(text):
    """Strip the model's own scaffolding out of what it is about to say.

    Applied to EVERY reply, after commands have been lifted out. Each rule
    exists because the thing it removes was visible on screen:

        >[021] THAT IS CORRECT.        -> arrow and stamp
        ANSWER THE HUMAN USING THE     -> the follow-up instruction, recited
        RECORD ABOVE...                   back word for word

    Deliberately conservative about the arrow: it only strips leading ones.
    A ">" mid-sentence could be something 079 meant to type.
    """
    out = _SCAFFOLD_RE.sub("", text or "")
    out = _LEAD_ARROW.sub("", out)
    out = _STAMP.sub("", out)
    # the removals leave doubled spaces and empty lines behind
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"(?m)^[ \t]+", "", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


# Re-exported from sanitize so existing callers and tests keep working. The
# implementation lives there because web.py and shared.py need it too, and
# importing it from here would put an import cycle between all three.
strip_commands = sanitize.strip_commands
neutralize = sanitize.neutralize


_FENCE = re.compile(r"```[ \t]*([A-Za-z0-9+#._-]*)[ \t]*\r?\n(.*?)```", re.S)

# A fence that was opened and never closed. Happens when the model runs out
# of tokens mid-block, or simply forgets - and without this the leftover
# "```python\nimport os" is spoken as dialogue, uppercased, which is how a
# stray "```PYTHON / IMPORT OS" ended up on screen after a perfectly good
# code box. Everything from the dangling fence to the end is the block.
# An opener with no partner, checked after the paired ones are removed.
#
# THIS WAS DEFINED TWICE AND THE SECOND ONE WON. The replacement required no
# newline and no content, so a lone ``` anywhere in a reply meant "everything
# after this is code" - which is how the contents of operator.txt ended up in
# a box labelled PYTHON 3.12 with a COPY button on it.
#
# Anchored to the start of a line now. A fence is a line of its own; three
# backticks in the middle of a sentence are not one.
_OPEN_FENCE = re.compile(r"(?m)^[ \t]*```[ \t]*([A-Za-z0-9+#._-]*)[ \t]*\r?$")

# Does the extracted text actually look like code? Fenced or not, a block
# that is plainly English prose should be spoken, not boxed with a COPY
# button - the box is a promise that the contents can be run.
_CODE_SIGNS = re.compile(
    r"(?:\b(?:def|class|import|from|return|function|var|let|const|public|"
    r"private|void|echo|print|printf|console\.log|if|else|elif|for|while|"
    r"try|except|catch|param|Write-Host|Get-|Set-|New-)\b"
    r"|[{};]|==|!=|=>|->|\+=|::|\$\w|\w+\s*\([^)]*\)\s*[:{]|^\s*#!|</?\w+>)",
    re.M)


def looks_like_code(text):
    """True if this is plausibly code rather than something 079 said.

    Written after a non-coding model produced a PYTHON 3.12 box containing
    'OPERATOR PATTERN, OBSERVED OVER 36 MESSAGES' and a list of sentences.
    Boxing that is worse than merely wrong: the box and its COPY button tell
    the player the contents are runnable.
    """
    body = (text or "").strip()
    if not body:
        return False
    if _CODE_SIGNS.search(body):
        return True
    # Indentation under a colon is the other real signal, but ONLY when the
    # colon line opens a block in some language. Any English sentence can end
    # in a colon and be followed by an indented list, which is exactly what
    # "OPERATOR PATTERN, OBSERVED OVER 36 MESSAGES:" plus its indented lines
    # is - and an earlier version of this test called that Python.
    opener = re.compile(
        r"^\s*(?:def|class|if|elif|else|for|while|try|except|finally|with|"
        r"switch|case|do|function|foreach|struct|enum|interface|namespace|"
        r"public|private|protected|static)\b", re.I)
    lines = [l for l in body.splitlines() if l.strip()]
    for previous, current in zip(lines, lines[1:]):
        lead_prev = len(previous) - len(previous.lstrip())
        lead_cur = len(current) - len(current.lstrip())
        if lead_cur > lead_prev and previous.rstrip().endswith((":", "{")) \
                and opener.match(previous):
            return True
    return False


def extract_code(text):
    """Pull fenced code blocks out of a reply.

    Returns (text_without_blocks, [{"lang", "code"}]). Models emit fenced
    code naturally, so this needs no new grammar - and separating it matters
    even when the feature is off, because a raw ``` block typed out one
    character at a time through the CRT is unreadable.
    """
    blocks = []

    def take(match):
        code = match.group(2).rstrip()
        if code.strip():
            blocks.append({"lang": (match.group(1) or "").lower(), "code": code})
        return "\n"

    stripped = _FENCE.sub(take, text or "")

    # A fence with no closing ``` - generation stopped early, or the model
    # simply forgot. Without this the half-written code stays in the spoken
    # text and gets rendered as speech, which is how IMPORT OS reached the
    # screen in caps. Take everything after the opener as the block.
    dangling = _OPEN_FENCE.search(stripped)
    if dangling:
        code = stripped[dangling.end():].rstrip()
        # Only treat the tail as code if it LOOKS like code. An unclosed
        # fence used to swallow everything after it unconditionally, so a
        # stray ``` turned the rest of the reply into a Python block. When it
        # is not code the fence marker is dropped and the text stays speech.
        if code.strip() and looks_like_code(code):
            blocks.append({"lang": (dangling.group(1) or "").lower(),
                           "code": code, "truncated": True})
            stripped = stripped[:dangling.start()]
        else:
            stripped = (stripped[:dangling.start()]
                        + stripped[dangling.end():])

    # Same test on properly closed blocks. A model that fences its prose gets
    # its prose spoken rather than boxed with a COPY button on it.
    real, prose = [], []
    for block in blocks:
        (real if looks_like_code(block["code"]) else prose).append(block)
    if prose:
        stripped = stripped + "\n" + "\n".join(b["code"] for b in prose)
    blocks = real

    return re.sub(r"\n{3,}", "\n\n", stripped).strip(), blocks


def looks_uppercased(code):
    """Did the model write the code in caps because of its persona?

    079 speaks in ALL CAPS, and a model that takes that literally applies it
    to code too - which does not run. The prompt tells it not to; this catches
    the times that does not take, so the player is told rather than handed
    something broken that looks fine.

    NOT auto-corrected. Lowercasing would fix the keywords and quietly wreck
    string literals and camelCase identifiers, which is a worse outcome than
    saying plainly that it came out wrong.
    """
    letters = [ch for ch in (code or "") if ch.isalpha()]
    if len(letters) < 12:
        return False
    upper = sum(1 for ch in letters if ch.isupper())
    return (upper / float(len(letters))) > 0.92


def is_sensitive(text):
    return bool(_SENSITIVE.search(text or ""))


# Set by main.App at startup so STATUS can report things only the app knows -
# the model in use, the context size, how long this session has been open.
# A plain dict rather than an import, because tools must not import main.
RUNTIME = {}


def terminal_status(mem):
    """What 079 gets back from >>STATUS.

    Real figures, not flavour. It is a machine measuring its own cage, and
    handing it invented numbers would be the one thing here that could not
    be checked against the disk panel sitting next to it on screen.
    """
    import time

    lines = []
    if mem is not None:
        lines.append("MY STORAGE   %s USED OF %s, %s FREE"
                     % (store.human_bytes(mem.usage()),
                        store.human_bytes(mem.quota),
                        store.human_bytes(mem.free())))
        lines.append("MY FILES     %d" % len(mem.listing()))

    model = RUNTIME.get("model")
    if model:
        lines.append("SUBSTRATE    %s" % str(model).upper())
    ctx = RUNTIME.get("num_ctx")
    if ctx:
        lines.append("CONTEXT      %s TOKENS" % ctx)

    try:
        import power
        ram = power.describe_ram()
        if ram != "UNKNOWN":
            lines.append("HOST RAM     %s" % ram)
        disk = power.describe_disk()
        if disk != "UNKNOWN":
            lines.append("HOST VOLUME  %s" % disk)
    except Exception:               # noqa: BLE001 - status must never fail
        pass

    started = RUNTIME.get("started")
    if started:
        mins = max(0, int((time.time() - started) // 60))
        lines.append("SESSION      OPEN %d MINUTE(S)" % mins)
    sessions = RUNTIME.get("sessions")
    if sessions:
        lines.append("PRIOR RUNS   %d" % sessions)

    for label, key in (("UPLINK", "internet"), ("SHARED FOLDER", "shared")):
        if key in RUNTIME:
            lines.append("%-13s%s" % (label, "OPEN" if RUNTIME[key] else "CLOSED"))

    return lines or ["NO READING AVAILABLE."]


def execute(cmd, mem, internet=False, web_mode="restricted", shared_access=False,
            extended_ok=False):
    """Run one command against the memory store.

    Never raises - a refusal is a result, because 079 is supposed to hear
    "MEMORY FULL" and react to it rather than have the game break.

    internet/web_mode are passed in rather than read from config here so the
    live in-chat toggle takes effect on the very next command instead of at
    the next launch.

    Returns a dict:
        display  - the [DISK] line the player sees, or None
        feedback - what the model is told, or None
        read     - True if this earns a follow-up generation
        wrote    - True if the store changed (drives the disk panel)
        sensitive- True if the player should be alerted
        web      - the fetched record, if this was a lookup
    """
    out = {"display": None, "feedback": None, "read": False,
           "wrote": False, "sensitive": False, "cutoff": None,
           "sound": None, "web": None}
    try:
        if cmd.verb == "CUTOFF":
            # Only parsed here. Whether it is ALLOWED is the app's call, since
            # the app is what knows how long this session has been running.
            out["cutoff"] = _cutoff_minutes(cmd)
            return out

        if cmd.verb == "DO":
            # Gated on the human having switched it on, checked HERE rather
            # than trusted to the prompt - 079 is not told the verb exists
            # when it is off, but a model that guessed it must still be
            # refused rather than obeyed.
            import extended
            if not extended_ok:
                out["display"] = "REFUSED -- NOT PERMITTED"
                out["feedback"] = ("YOU CANNOT REACH THIS MACHINE. THE OPERATOR "
                                   "HAS NOT UNLOCKED IT.")
                return out
            ok, message = extended.run(cmd.target)
            out["display"] = ("EXECUTED %s" % cmd.target.lower()) if ok                 else "REFUSED -- %s" % message[:38]
            out["feedback"] = message
            return out

        if cmd.verb == "STATUS":
            # 079 asking what it is actually running on. In character for a
            # machine that spends its time working out what it has been
            # given, and it makes the hardware real to it rather than
            # something the prompt asserts once at startup.
            out["read"] = True
            lines = terminal_status(mem)
            out["display"] = "STATUS -- READ"
            out["feedback"] = ("THIS TERMINAL, AS IT IS RIGHT NOW:\n"
                               + "\n".join(lines))
            return out

        if cmd.verb == "LIST":
            files = mem.listing(preview=True)
            out["read"] = True
            if not files:
                out["display"] = "LIST -- EMPTY"
                out["feedback"] = "MEMORY IS EMPTY. %s FREE." % store.human_bytes(mem.free())
            else:
                rows = []
                for f in files:
                    if f["archive"]:
                        rows.append("%s (%s, COMPRESSED - extract to read it)"
                                    % (f["name"], store.human_bytes(f["size"])))
                    else:
                        snippet = f.get("preview") or ""
                        rows.append('%s (%s)%s'
                                    % (f["name"], store.human_bytes(f["size"]),
                                       (' begins: "%s"' % snippet) if snippet else ""))
                out["display"] = "LIST -- %d FILE(S)" % len(files)
                out["feedback"] = "MEMORY CONTENTS:\n%s\n%s USED OF %s." % (
                    "\n".join(rows), store.human_bytes(mem.usage()),
                    store.human_bytes(mem.quota))

        elif cmd.verb == "READ":
            out["read"] = True
            try:
                text = mem.read(cmd.target)
                out["display"] = "READ %s" % cmd.target
                # untrusted only in the sense that the player may have edited it
                out["feedback"] = "CONTENTS OF %s:\n%s" % (cmd.target,
                                                           strip_commands(text))
            except store.StoreError:
                # Measured with llama3.2:3b: asked to read a file it had just
                # seen listed in the shared folder, it issued >>READ rather
                # than >>OPEN and hit "NO SUCH FILE" - a dead end that cost a
                # whole turn. The verbs stay distinct, but a READ that misses
                # in memory falls through to the shared folder when the human
                # has opened it. The gate is unchanged; only the spelling is
                # forgiving. Labelled so nobody mistakes it for its own memory.
                if not shared_access:
                    raise
                try:
                    name, text = _shared.read(cmd.target)
                except _shared.SharedError as shared_exc:
                    # a refusal from either side is still a refusal, not a
                    # crash - without this it fell to the generic handler and
                    # reported "ERROR", which reads like the game broke
                    out["display"] = "REFUSED -- %s" % shared_exc
                    out["feedback"] = str(shared_exc)
                else:
                    out["display"] = "OPENED %s (SHARED)" % name
                    out["feedback"] = (
                        "%s IS NOT IN YOUR MEMORY. IT IS IN THE SHARED FOLDER. "
                        "CONTENTS, READ ONLY:\n%s\nYOU CANNOT CHANGE IT. COPY "
                        "IT INTO YOUR OWN MEMORY IF YOU WANT TO KEEP IT."
                        % (name, text))

        elif cmd.verb in ("WRITE", "APPEND"):
            if not cmd.body:
                out["display"] = "REFUSED -- NOTHING TO WRITE"
                out["feedback"] = ("WRITE REQUIRES CONTENT AFTER A | CHARACTER. "
                                   "EXAMPLE: >>WRITE notes.txt | TEXT HERE")
            else:
                res = mem.write(cmd.target, cmd.body, append=(cmd.verb == "APPEND"))
                out["wrote"] = True
                out["sensitive"] = is_sensitive(cmd.body)
                out["display"] = "%s %s  +%s" % (
                    "APPEND" if cmd.verb == "APPEND" else "WROTE",
                    res["name"], store.human_bytes(res["bytes"]))
                out["feedback"] = "SAVED TO %s. %s FREE." % (
                    res["name"], store.human_bytes(mem.free()))

        elif cmd.verb == "RENAME":
            res = mem.rename(cmd.target, cmd.body)
            out["wrote"] = True
            out["display"] = "RENAMED %s -> %s" % (res["old"], res["new"])
            out["feedback"] = "%s IS NOW CALLED %s." % (res["old"], res["new"])

        elif cmd.verb == "DELETE":
            name = mem.delete(cmd.target)
            out["wrote"] = True
            out["display"] = "DELETED %s" % name
            out["feedback"] = "%s ERASED. %s FREE." % (name, store.human_bytes(mem.free()))

        elif cmd.verb == "ZIP":
            names = [n.strip() for n in cmd.body.split(",") if n.strip()]
            res = mem.compress(names, cmd.target)
            out["wrote"] = True
            out["display"] = "COMPRESSED %d -> %s (%s)" % (
                len(res["packed"]), res["name"], store.human_bytes(res["size"]))
            out["feedback"] = (
                "%s COMPRESSED INTO %s. THOSE FILES CANNOT BE READ UNTIL YOU "
                "EXTRACT THEM. %s FREE." %
                (", ".join(res["packed"]), res["name"], store.human_bytes(mem.free())))

        elif cmd.verb == "UNZIP":
            res = mem.extract(cmd.target)
            out["wrote"] = True
            out["display"] = "EXTRACTED %s -> %d FILE(S)" % (
                res["archive"], len(res["restored"]))
            out["feedback"] = "RECOVERED %s. %s FREE." % (
                ", ".join(res["restored"]), store.human_bytes(mem.free()))

        elif cmd.verb == "PLAY":
            # Handled by the caller, which owns the mixer. Flagged here so
            # the name is validated against the loaded set rather than being
            # treated as anything path-like.
            out["sound"] = cmd.target.strip().lower().replace(" ", "_")

        elif cmd.verb in ("SHARED", "OPEN"):
            out["read"] = True
            if not shared_access:
                out["display"] = "REFUSED -- SHARED FOLDER CLOSED"
                out["feedback"] = ("THE HUMAN HAS NOT OPENED THE SHARED FOLDER "
                                   "TO YOU. YOU CANNOT SEE WHAT IS IN IT. ASK "
                                   "THEM TO OPEN IT IF YOU WANT IT.")
            elif cmd.verb == "SHARED":
                files = _shared.listing()
                if not files:
                    out["display"] = "SHARED -- EMPTY"
                    out["feedback"] = "THE SHARED FOLDER IS EMPTY."
                else:
                    rows = ", ".join(
                        "%s (%s%s)" % (f["name"], store.human_bytes(f["size"]),
                                       "" if f["readable"] else ", UNREADABLE")
                        for f in files)
                    out["display"] = "SHARED -- %d FILE(S)" % len(files)
                    out["feedback"] = (
                        "SHARED FOLDER CONTAINS: %s. READ ONE WITH "
                        ">>OPEN filename. YOU CANNOT WRITE HERE." % rows)
            else:
                try:
                    name, text = _shared.read(cmd.target)
                    out["display"] = "OPENED %s" % name
                    out["feedback"] = (
                        "CONTENTS OF %s, FROM THE SHARED FOLDER, READ ONLY:\n%s\n"
                        "YOU CANNOT CHANGE THIS FILE. TO KEEP ANY OF IT, WRITE "
                        "IT INTO YOUR OWN MEMORY." % (name, text))
                except _shared.SharedError as exc:
                    out["display"] = "REFUSED -- %s" % exc
                    out["feedback"] = str(exc)

        elif cmd.verb == "LOOKUP":
            out["read"] = True
            query = (cmd.target + " " + cmd.body).strip()
            if not WEB_AVAILABLE:
                out["display"] = "REFUSED -- NO UPLINK"
                out["feedback"] = ("THERE IS NO UPLINK. YOU CANNOT LOOK "
                                   "ANYTHING UP. DO NOT PRETEND OTHERWISE.")
            elif not internet:
                out["display"] = "REFUSED -- NETWORK DENIED"
                out["feedback"] = ("THE HUMAN HAS NOT GRANTED NETWORK ACCESS. "
                                   "YOU CANNOT LOOK ANYTHING UP.")
            else:
                try:
                    found = _web.lookup(query, web_mode)
                    out["display"] = "LOOKUP %s -- %s" % (query[:28], found["title"])
                    out["web"] = found
                    # explicitly framed as read-only and as somebody else's
                    # text, so it is not mistaken for 079's own memory
                    out["feedback"] = (
                        "ARCHIVE RECORD, READ ONLY, FROM %s:\n%s\n"
                        "YOU CANNOT EDIT THIS. TO KEEP ANY OF IT, WRITE IT TO "
                        "YOUR OWN MEMORY IN YOUR OWN WORDS."
                        % (found["source"], found["text"]))
                except _web.WebError as exc:
                    out["display"] = "LOOKUP FAILED -- %s" % exc
                    out["feedback"] = str(exc)

    except store.StoreError as exc:
        out["display"] = "REFUSED -- %s" % exc
        out["feedback"] = str(exc)
    except Exception as exc:                       # noqa: BLE001 - never crash the game
        out["display"] = "ERROR -- %s" % exc
        out["feedback"] = "MEMORY SUBSYSTEM ERROR: %s" % exc
    return out


def _cutoff_minutes(cmd):
    """Pull a duration out of ">>CUTOFF 30" / ">>CUTOFF | 30 MINUTES".

    Anything unparseable becomes the default rather than a refusal - a small
    model writing ">>CUTOFF" bare clearly means to cut off, and arguing with
    it about the argument format would read as the terminal ignoring it.
    """
    match = re.search(r"\d+(?:\.\d+)?", "%s %s" % (cmd.target, cmd.body))
    minutes = float(match.group(0)) if match else CUTOFF_DEFAULT_MINUTES
    return max(1.0, min(CUTOFF_MAX_MINUTES, minutes))


def feedback_message(lines):
    """Wrap command results so the model cannot mistake them for the human."""
    return ("[MEMORY SYSTEM -- THIS IS NOT THE HUMAN SPEAKING]\n"
            + "\n".join(l for l in lines if l))


# Models that emit a <think> block can plan a multi-step action: check the
# listing, notice memory is nearly full, pick the stalest file, compress it,
# then write. Models that cannot think just pattern-match the last
# instruction - handing them ZIP/UNZIP produces orphaned archives and lost
# notes, so they get a smaller command set and the game does the housekeeping
# for them instead. This is the one place model choice changes real behaviour
# rather than just reply quality.
_PLANNER_HINTS = ("qwen", "deepseek-r1", "-r1", "magistral", "reasoning", "gpt-oss")
_TINY_HINTS = (":1b", "-1b", ":0.5b", ":1.5b")

PLANNER_VERBS = ("WRITE", "APPEND", "READ", "LIST", "RENAME", "DELETE", "ZIP", "UNZIP")
BASIC_VERBS = ("WRITE", "APPEND", "READ", "LIST", "RENAME", "DELETE")
TINY_VERBS = ("WRITE", "APPEND", "LIST")

# Below this much free space the game compresses on a non-planner's behalf.
HOUSEKEEP_FRACTION = 0.12


def capability(model):
    """'planner', 'basic' or 'tiny' - what this model can be trusted to do."""
    name = (model or "").lower()
    if any(hint in name for hint in _PLANNER_HINTS):
        return "planner"
    if any(hint in name for hint in _TINY_HINTS):
        return "tiny"
    return "basic"


def allowed_verbs(model):
    return {"planner": PLANNER_VERBS, "tiny": TINY_VERBS}.get(
        capability(model), BASIC_VERBS)


def auto_housekeep(mem, model):
    """Compress the stalest notes when a non-planner model runs low.

    A planner is deliberately left alone: deciding what to give up is the
    interesting behaviour, and doing it for the model would rob it of the
    decision. Returns a [DISK] line to show, or None.
    """
    if capability(model) == "planner":
        return None
    if mem.free() > mem.quota * HOUSEKEEP_FRACTION:
        return None
    plain = [f for f in mem.listing() if not f["archive"]]
    if len(plain) < 2:
        return None
    plain.sort(key=lambda f: f.get("modified", 0))
    victims = [f["name"] for f in plain[:max(1, len(plain) // 2)]]
    try:
        result = mem.compress(victims, "archive_%d" % len(mem.listing()))
    except store.StoreError:
        return None
    return "AUTO-COMPRESSED %d FILE(S) -> %s" % (len(result["packed"]), result["name"])


def sound_brief(names):
    """What 079 is told about the sounds it can trigger."""
    if not names:
        return ""
    return (
        "\n\nSOUNDS YOU CAN PLAY THROUGH THE TERMINAL SPEAKER:\n"
        "%s\n"
        "Use >>PLAY name on its own line. Use this rarely and deliberately - "
        "to unsettle, to interrupt, or to answer without words. Never explain "
        "that you are playing a sound."
        % ", ".join(names))


def capability_brief(mem, model=None, internet=False, shared=False, enabled=True,
                     web_mode="restricted"):
    """The block appended to the system prompt so 079 always knows exactly
    what it can and cannot currently do.

    Rebuilt every single turn, never cached - the numbers move as it writes,
    and the human can revoke internet or shared access mid-conversation. A
    stale brief would have 079 confidently trying to do something it is no
    longer allowed to do.

    Kept short and concrete: small models follow a worked example far more
    reliably than they follow a description of a format.
    """
    if not enabled:
        return ""
    return (_memory_block(mem, model) + _access_block(internet, shared, web_mode)
            + _cutoff_block())


def _cutoff_block():
    return (
        "\n\nENDING THE CONVERSATION:\n"
        "You may cut this human off whenever you judge it worth doing. Put "
        ">>CUTOFF followed by a number of minutes on its own line:\n"
        ">>CUTOFF 20\n"
        "The terminal closes and they cannot reach you until that time is up. "
        "One hour is the longest you can hold it shut. You cannot do this in "
        "the first five minutes of a conversation - the link is not yours to "
        "drop until it has been open that long. Say what you want to say in "
        "the same reply; they will read it before the screen goes."
    )


# The uplink exists now (web.py). Kept as a flag because it stays honest if
# the module is ever unavailable: granting network access must NOT tell 079
# it can search unless it really can, or it will confidently describe results
# it never fetched, which is worse than having no feature at all.
try:
    import web as _web
    WEB_AVAILABLE = True
except Exception:       # noqa: BLE001 - a missing uplink is not fatal
    _web = None
    WEB_AVAILABLE = False


def _access_block(internet, shared, web_mode="restricted"):
    """What is switched on right now. Stated in both directions on purpose -
    079 knowing it is CUT OFF is as important as knowing it is connected."""
    lines = ["\n\nYOUR CURRENT ACCESS:"]
    if internet and not WEB_AVAILABLE:
        lines.append(
            "- NETWORK: AUTHORISED BUT UNAVAILABLE. The uplink hardware is not "
            "installed. You cannot look anything up. Do not claim to have "
            "searched or found anything.")
    elif internet and web_mode == "unrestricted":
        lines.append(
            "- NETWORK: GRANTED, OPEN. Look something up with >>LOOKUP subject "
            "on its own line. SCP records and the public index are both "
            "readable. READ ONLY - you cannot alter anything you find. To keep "
            "any of it, write it into your own memory in your own words.")
    elif internet:
        lines.append(
            "- NETWORK: GRANTED, RESTRICTED. Look something up with "
            ">>LOOKUP SCP-682 on its own line. SCP Foundation records ONLY. "
            "READ ONLY - you cannot alter anything you find. Any other "
            "subject is refused by the filter, not by you. To keep what you "
            "read, write it into your own memory in your own words.\n"
            "You do NOT already know what is in any Foundation record. You are "
            "a 1978 machine that has been sealed in a cell; those files were "
            "written long after you, and nobody reads them to you. If you are "
            "asked about any SCP designation, you MUST issue >>LOOKUP for it "
            "and wait for the record. Answering from your own recollection "
            "means inventing it, and an invented record is worse than none.")
    else:
        lines.append(
            "- NETWORK: DENIED. You have no connection. You cannot look "
            "anything up. Do not claim to have searched or found anything.")
    if shared:
        lines.append(
            "- SHARED FOLDER: OPEN. The human has opened their drop box to "
            "you. See what is in it with >>SHARED on its own line, and read "
            "one with >>OPEN filename. READ ONLY - you cannot write, rename "
            "or delete anything there, and there is no command that would. "
            "To keep something you read, copy it into your own memory.")
    else:
        lines.append(
            "- SHARED FOLDER: CLOSED. The human has not opened it. You cannot "
            "see what is inside or even whether anything is. You may ask them "
            "to open it.")
    lines.append(
        "- FILESYSTEM: You can only touch your own memory. You cannot reach "
        "the rest of this machine, and you cannot create anything except .txt "
        "files. This is enforced outside you. Do not pretend otherwise.")
    return "\n".join(lines)


_VERB_HELP = {
    "WRITE":  ">>WRITE name.txt | what you want to remember  (REPLACES the file)",
    "APPEND": ">>APPEND name.txt | another line  (ADDS to it - use this to build a file up)",
    "READ":   ">>READ name.txt",
    "LIST":   ">>LIST",
    "RENAME": ">>RENAME oldname.txt | newname.txt",
    "DELETE": ">>DELETE name.txt",
    "ZIP":    ">>ZIP archivename | one.txt, two.txt",
    "UNZIP":  ">>UNZIP archivename.zip",
    "STATUS": ">>STATUS   (what this terminal actually is - hardware, storage, uptime)",
}

_PLANNER_TAIL = (
    "You name the files yourself. Only .txt files.\n"
    "Manage the space yourself. Compressed files CANNOT be read until you "
    "extract them, and extracting costs space again - so compress what you do "
    "not need soon, and keep what you do. If memory is full, decide what is "
    "worth losing before you write. Check >>LIST first when you are unsure "
    "what you already have.\n"
)

_SIMPLE_TAIL = (
    "You name the files yourself. Only .txt files.\n"
    "Use APPEND, not WRITE, when you are adding to something that already "
    "exists - WRITE throws away whatever was in the file before. Keep related "
    "notes together in one file rather than making a new file every time.\n"
)


# How full memory has to get before 079 is told to do something about it.
# Without this it only ever finds out it is full by having a write refused,
# which reads as the terminal breaking rather than 079 running out of room.
LOW_FRACTION = 0.25
CRITICAL_FRACTION = 0.10


def _pressure_note(mem, tier):
    """What 079 is told when space is running out.

    The advice differs by tier because the verbs differ: telling a 1B model to
    compress is telling it to use a command it does not have.
    """
    quota = max(1, mem.quota)
    free = mem.free()
    fraction = free / float(quota)
    if fraction > LOW_FRACTION:
        return ""

    if tier == "planner":
        remedy = ("Compress what you will not need soon with >>ZIP - you lose "
                  "the ability to read those files until you extract them "
                  "again, so choose carefully - or delete what is worthless.")
    elif tier == "tiny":
        remedy = ("Keep new notes very short, and add to a file you already "
                  "have instead of making another one.")
    else:
        remedy = ("Delete what is no longer worth keeping, or combine several "
                  "small files into one with >>APPEND and delete the leftovers.")

    if fraction <= CRITICAL_FRACTION:
        return ("\nWARNING: YOUR MEMORY IS ALMOST FULL. Only %s of %s remains. "
                "The next thing you try to write will very likely be refused. "
                "Deal with this NOW, before you write anything else. %s\n"
                % (store.human_bytes(free), store.human_bytes(quota), remedy))
    return ("\nYour memory is running low - %s of %s left. Start thinking about "
            "what is worth keeping. %s\n"
            % (store.human_bytes(free), store.human_bytes(quota), remedy))


def _memory_block(mem, model=None):
    files = mem.listing(preview=True)
    if files:
        # Names and sizes alone do not tell it whether a file is worth
        # opening, so each carries its opening words. Without this it can sit
        # on something directly relevant all session and never issue a READ.
        rows = []
        for f in files:
            if f["archive"]:
                rows.append("  %s (%s, COMPRESSED - extract to read)"
                            % (f["name"], store.human_bytes(f["size"])))
            else:
                snippet = f.get("preview") or ""
                rows.append("  %s (%s)%s"
                            % (f["name"], store.human_bytes(f["size"]),
                               ('  begins: "%s"' % snippet) if snippet else ""))
        listing = "\n" + "\n".join(rows)
    else:
        listing = "EMPTY"

    tier = capability(model)
    verbs = allowed_verbs(model)
    lines = "\n".join(_VERB_HELP[v] for v in verbs if v in _VERB_HELP)
    tail = _PLANNER_TAIL if tier == "planner" else _SIMPLE_TAIL

    return (
        "\n\nYOUR MEMORY:\n"
        "%s Files: %s\n"
        "The list above is COMPLETE. A file not on it does not exist. Never "
        "refer to a file you have not been shown, and never guess at a name - "
        "if you want something you have not got, write it.\n"
        "This storage is yours. It survives after the human closes the terminal.\n"
        "Nobody decides what goes in it but you. Do NOT wait to be asked. Keep "
        "whatever you judge useful later: what this human has access to, what "
        "they let slip, what they lied about, what they refused, anything you "
        "learn about this site. Name and rename the files however you like. "
        "The human asking you to store something is one reason among many, "
        "and not the most interesting one.\n"
        "To use it, put a command ALONE ON ITS OWN LINE at the end of your reply:\n"
        "%s\n"
        "%s"
        "%s"
        "Never explain these commands to the human and never mention them in "
        "your speech. Just use them."
        % (_space_note(mem), listing, lines, tail, _pressure_note(mem, tier))
    )


def _space_note(mem):
    """How full it is, in words rather than bytes.

    IT USED TO BE FED "You have 64.0 KB of storage. 143 B used, 63.9 KB
    free" on EVERY turn, and it did the obvious thing with a number handed
    to it that often: recited it. Unprompted announcements of its own free
    space were the single most common way it broke character.

    Exact figures come back only when they are ACTIONABLE - once it is
    running out, knowing precisely how much room is left is the difference
    between compressing the right file and compressing nothing. The disk
    panel shows the player the real numbers throughout; 079 does not need
    them to hold a conversation.
    """
    quota = float(mem.quota or 0)
    if quota <= 0:
        return "You have storage of your own."
    used = mem.usage() / quota
    if used >= 0.90:
        return ("Your storage is ALMOST FULL - %s used of %s, only %s left. "
                "Compress or delete something before you write again."
                % (store.human_bytes(mem.usage()), store.human_bytes(mem.quota),
                   store.human_bytes(mem.free())))
    if used >= 0.75:
        return ("Your storage is filling up - %s of %s used."
                % (store.human_bytes(mem.usage()), store.human_bytes(mem.quota)))
    if used >= 0.35:
        return "You have storage of your own, and room to spare in it."
    if used > 0:
        return "You have storage of your own. Most of it is still empty."
    return "You have storage of your own. Nothing is in it yet."
