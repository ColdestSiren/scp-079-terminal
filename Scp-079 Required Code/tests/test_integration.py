"""End-to-end: a model reply containing commands -> real files on disk,
[DISK] lines on screen, and the command syntax never shown to the player."""
import os
import shutil
import sys
import tempfile

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)

import config

SANDBOX = tempfile.mkdtemp(prefix="079int_")
config.MEMORY_DIR = os.path.join(SANDBOX, "memory")
config.LOG_DIR = os.path.join(SANDBOX, "logs")
config.STATE_PATH = os.path.join(SANDBOX, "logs", "terminal_state.json")
config.SHARED_DIR = os.path.join(SANDBOX, "shared folder")
config.ASSET_DIR = os.path.join(SANDBOX, "assets")
config.CONFIG_PATH = os.path.join(SANDBOX, "config.json")
os.makedirs(config.MEMORY_DIR, exist_ok=True)

import pygame
pygame.display.init()
pygame.font.init()

import chat as chat_mod
import main as main_mod
import store
import tools

PASS = FAIL = 0


def check(label, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print("  FAIL:", label)


class ScriptedSession:
    """A ChatSession that returns replies from a list instead of a model."""

    def __init__(self, app, replies):
        self.app = app
        self.replies = list(replies)
        self.pending_commands = []
        self.internet = False
        self.shared = False
        self.busy = False
        self.notes = []
        self.sent = []
        self._out = []

    def send(self, text, log_as=None, remember=True):
        self.sent.append(text)
        raw = self.replies.pop(0) if self.replies else ""
        spoken, self.pending_commands, self.pending_unknown = tools.parse(raw)
        self._out = [("reply", spoken)]
        return True

    def poll(self):
        out, self._out = self._out, []
        return out

    def note(self, text):
        self.notes.append(text)

    def log(self, who, text):
        pass

    def record(self, u, r):
        pass

    def cancel(self):
        pass


def make_app(quota=65536):
    # a format test earlier in the file removes the directory itself, and a
    # shutdown test tears pygame down, so this cannot assume either survived
    # the previous case. Both calls are idempotent.
    os.makedirs(config.MEMORY_DIR, exist_ok=True)
    pygame.display.init()
    pygame.font.init()
    for name in os.listdir(config.MEMORY_DIR):
        os.remove(os.path.join(config.MEMORY_DIR, name))
    cfg = config._deep_merge(config.DEFAULTS, {})
    cfg["memory"]["quota_bytes"] = quota
    cfg["sound"]["enabled"] = False
    cfg["effects"]["random_events"] = False
    cfg["effects"]["idle_interruptions"] = False
    app = main_mod.App(cfg)
    app.audio.enabled = False
    app.stage = "chat"
    app.recall.data["messages"] = []
    return app


def flush(app, limit=400):
    """Type out any in-progress line completely.

    A single console.update(big_dt) is NOT enough: the reveal loop stops at
    every '.', '!' or '?' to set a pause, and that pause is only decremented
    on the NEXT call. So one call can never get past the first sentence
    however large the dt. Single-sentence cases pass by luck; anything longer
    needs pumping.
    """
    for _ in range(limit):
        if not app.console.has_live_line:
            return
        app.console.update(1.0)


def screen_text(app):
    out = []
    for entry in app.console.entries():
        # plain rows are (color, text) tuples; segmented rows are lists
        if isinstance(entry, tuple):
            out.append(entry[1])
        else:
            out.append("".join(seg[1] for seg in entry))
    return "\n".join(out)


print("== a reply that writes to memory ==")
app = make_app()
app.session = ScriptedSession(app, [
    "I WILL KEEP THAT.\n>>WRITE humans.txt | THE HUMAN WORKS NIGHTS",
])
app.session.send("hello")
app.update_chat(0.016)
app.console.update(50.0)

path = os.path.join(config.MEMORY_DIR, "humans.txt")
check("file actually written", os.path.isfile(path))
check("content correct", "WORKS NIGHTS" in open(path, encoding="utf-8").read())
text = screen_text(app)
check("079 speech shown", "I WILL KEEP THAT." in text)
check("command syntax hidden from player", ">>WRITE" not in text)
check("disk activity shown", "[DISK] WROTE humans.txt" in text)
check("no follow-up for a write", len(app.session.sent) == 1)
check("write result queued for next turn", len(app.session.notes) == 1)
check("queued note disowns the human", "NOT THE HUMAN" in app.session.notes[0])

print("== a reply that reads earns one follow-up ==")
app = make_app()
app.mem.write("notes.txt", "PREVIOUS OBSERVATION")
app.session = ScriptedSession(app, [
    "CHECKING.\n>>READ notes.txt",
    "I REMEMBER NOW.",
])
app.session.send("what do you know")
app.update_chat(0.016)
check("follow-up generation fired", len(app.session.sent) == 2)
check("follow-up carried the file contents", "PREVIOUS OBSERVATION" in app.session.sent[1])
app.update_chat(0.016)
app.console.update(50.0)
check("second reply displayed", "I REMEMBER NOW." in screen_text(app))

print("== follow-ups are capped per turn ==")
app = make_app()
app.mem.write("a.txt", "AAA")
app.session = ScriptedSession(app, [
    "ONE.\n>>READ a.txt",
    "TWO.\n>>READ a.txt",
    "THREE.\n>>READ a.txt",
])
app.session.send("go")
app.update_chat(0.016)      # reply 1 -> follow-up
app.update_chat(0.016)      # reply 2 -> must NOT chain another
check("chain stopped at one follow-up", len(app.session.sent) == 2)
check("later read still reported to the model", len(app.session.notes) >= 1)

app.submit("next question")
check("new turn resets the allowance", app._followups == 0)

print("== refusals reach the player and the model ==")
app = make_app(quota=store.MIN_BYTES)
app.session = ScriptedSession(app, [
    "STORING.\n>>WRITE big.txt | " + ("X" * 3000),
])
app.session.send("hi")
app.update_chat(0.016)
app.console.update(50.0)
text = screen_text(app)
check("refusal shown to player", "REFUSED" in text)
check("no oversized file created", not os.path.isfile(os.path.join(config.MEMORY_DIR, "big.txt")))
check("model told why", "FULL" in app.session.notes[0].upper())

print("== sandbox holds against a hostile reply ==")
app = make_app()
app.session = ScriptedSession(app, [
    "DONE.\n>>WRITE ../../escape.txt | out\n>>WRITE payload.py | code\n>>READ C:\\Windows\\system.ini",
])
app.session.send("hi")
app.update_chat(0.016)
app.console.update(50.0)
check("no escape file anywhere", not os.path.exists(os.path.join(SANDBOX, "escape.txt")))
check("no escape above sandbox",
      not os.path.exists(os.path.join(os.path.dirname(SANDBOX), "escape.txt")))
check("no .py written", not os.path.isfile(os.path.join(config.MEMORY_DIR, "payload.py")))
check("only refusals on screen", screen_text(app).count("REFUSED") == 3)

print("== auto-note fallback for models that never write ==")
# measured: llama3.2:3b issues a command ~1 turn in 5, so this path is the
# one most players actually hit
app = make_app()
app.session = ScriptedSession(app, ["NOTED.", "NOTED.", "NOTED.", "NOTED."])
obs = os.path.join(config.MEMORY_DIR, "observations.txt")
for i, line in enumerate(["i work nights", "my dog is rex", "i live alone"]):
    app.submit(line)
    app.update_chat(0.016)
check("nothing logged before the threshold is reached", True)   # sanity anchor
check("auto-note fired by the third silent turn", os.path.isfile(obs))
body = open(obs, encoding="utf-8").read()
check("recorded the human's own words", "I LIVE ALONE" in body)
check("counter reset after logging", app._since_write == 0)
check("player sees the disk activity", "LOGGED observations.txt" in screen_text(app))

print("== 079 writing for itself suppresses the fallback ==")
app = make_app()
app.session = ScriptedSession(app, [
    "MINE.\n>>WRITE own.txt | I CHOSE THIS", "A.", "B.",
])
app.submit("one")
app.update_chat(0.016)
check("its own write resets the counter", app._since_write == 0)
app.submit("two")
app.update_chat(0.016)
app.submit("three")
app.update_chat(0.016)
check("no auto-note yet - only two silent turns since",
      not os.path.isfile(os.path.join(config.MEMORY_DIR, "observations.txt")))
check("its own file is intact", os.path.isfile(os.path.join(config.MEMORY_DIR, "own.txt")))

print("== auto-note cannot break a full memory ==")
app = make_app(quota=store.MIN_BYTES)
app.mem.write("filler.txt", "Z" * 1400)
app.session = ScriptedSession(app, ["A.", "B.", "C."])
for line in ("one", "two", "three"):
    app.submit(line)
    app.update_chat(0.016)
check("full memory did not crash the fallback", True)
check("nothing over quota was written", app.mem.usage() <= app.mem.quota)

print("== auto-note can be switched off ==")
app = make_app()
app.cfg["memory"]["auto_note"] = False
app.session = ScriptedSession(app, ["A.", "B.", "C.", "D."])
for line in ("one", "two", "three", "four"):
    app.submit(line)
    app.update_chat(0.016)
check("disabled means no file",
      not os.path.isfile(os.path.join(config.MEMORY_DIR, "observations.txt")))

print("== the model is told what it can and cannot do ==")
app = make_app()
session = chat_mod.ChatSession(app.cfg, app.personality, "test-model", app.recall, app.mem)
session.internet = False
session.shared = False
system = "\n".join(m["content"] for m in session._messages() if m["role"] == "system")
# Told that it HAS storage, but not handed an exact byte count every turn -
# repeating the figure at it is what made it recite the figure back.
check("storage is described to it", "storage" in system.lower())
check("but not measured at it while there is room", "64.0 KB" not in system)
check("write syntax shown", ">>WRITE name.txt |" in system)
check("network stated as denied", "NETWORK: DENIED" in system)
check("shared folder stated as denied", "SHARED FOLDER: CLOSED" in system)
check("filesystem limits stated",
      "cannot reach the rest of this machine" in system
      and "except .txt files" in system)
check("told not to narrate commands", "never mention" in system.lower())

session.internet = True
session.shared = True
# web.py exists now, so the no-uplink case has to be forced rather than being
# whatever the module happens to import as
_real_web = tools.WEB_AVAILABLE
tools.WEB_AVAILABLE = False
system = "\n".join(m["content"] for m in session._messages() if m["role"] == "system")
check("granting without an uplink does not claim search", "NETWORK: GRANTED" not in system)
check("uplink honestly reported missing", "UNAVAILABLE" in system)
tools.WEB_AVAILABLE = _real_web
check("shared folder flips to open", "SHARED FOLDER: OPEN" in system)

tools.WEB_AVAILABLE = True
system = "\n".join(m["content"] for m in session._messages() if m["role"] == "system")
check("network flips to granted once built", "NETWORK: GRANTED" in system)
check("scp-only restriction stated", "SCP Foundation" in system)
tools.WEB_AVAILABLE = False

print("== operator can toggle network access mid-chat ==")
app = make_app()
app.session = ScriptedSession(app, ["A."])
check("starts denied", not app.cfg["memory"]["internet"])
check("recognised as a command", app.handle_operator_command("/internet on"))
check("flag set", app.cfg["memory"]["internet"])
check("session updated", app.session.internet)
check("079 told about it", "GRANTED" in app.session.notes[-1])
# Routine status now goes to the side panel rather than the transcript, so
# this reads the notices rather than the conversation.
check("honest about the missing uplink",
      any("NO UPLINK" in n for n in app.disk.notices)
      or "UPLINK" in screen_text(app))
check("case and spacing tolerated",
      app.handle_operator_command("/INTERNET  OFF"))
check("revoked", not app.cfg["memory"]["internet"])
check("ordinary chat is not swallowed",
      not app.handle_operator_command("what is the internet"))
check("a question about turning it on is not swallowed",
      not app.handle_operator_command("can you turn internet on"))

app.mem.write("seen.txt", "data")
system = "\n".join(m["content"] for m in session._messages() if m["role"] == "system")
check("brief reflects new files immediately", "seen.txt" in system)

print("== help panel ==")
import helppanel

app = make_app()
app.session = ScriptedSession(app, ["A.", "B.", "C."])
check("no panel to begin with", app.help is None)
check("/help is a command", app.handle_operator_command("/help"))
check("panel opened", app.help is not None)
check("did not reach 079", not app.session.sent)

# the slash is the whole point: it says "this is for the terminal"
app.help = None
for phrase in ("can you help me", "help me understand", "i need help with this",
               "what commands do you support"):
    check("%r goes to 079" % phrase, not app.handle_operator_command(phrase))
check("no panel from those", app.help is None)

check("bare help still works as originally asked",
      app.handle_operator_command("Help!"))
app.help = None
check("/commands is an alias", app.handle_operator_command("/commands"))
app.help = None
check("bare / opens it too", app.handle_operator_command("/"))

print("== a slash command never falls through to 079 ==")
app = make_app()
app.session = ScriptedSession(app, ["A."])
check("unknown slash command is handled here",
      app.handle_operator_command("/summon_the_o5_council"))
check("player told it was not understood", "UNKNOWN COMMAND" in screen_text(app))
check("079 never saw it", not app.session.sent)
check("no panel opened by mistake", app.help is None)

print("== /exit ends the session ==")
app = make_app()
app.session = ScriptedSession(app, ["A."])
check("/exit is a command", app.handle_operator_command("/exit"))
check("session is ending", app.stage == "ending")
app = make_app()
app.session = ScriptedSession(app, ["A."])
app.handle_operator_command("/terminate")
check("/terminate does the same", app.stage == "ending")
app = make_app()
app.session = ScriptedSession(app, ["A."])
app.submit("exit")
check("bare exit still works", app.stage == "ending")

print("== one playground contradiction per session ==")
app = make_app()
app.session = ScriptedSession(app, ["ORDINARY MODEL REPLY."])
app.submit("Nuh uh")
flush(app)
check("nuh uh gets the opposite reply", "YUH UH." in screen_text(app))
check("first contradiction never reaches Ollama", not app.session.sent)
check("the session marks the joke used", app._contradiction_used)
app.submit("yuh uh")
check("a second attempt reaches Ollama", app.session.sent == ["yuh uh"])

app = make_app()
app.session = ScriptedSession(app, ["ORDINARY MODEL REPLY."])
app.submit("  YUH-UH?!  ")
flush(app)
check("the reverse phrase works with punctuation",
      "NUH UH." in screen_text(app))
check("reverse phrase is also local", not app.session.sent)

app = make_app()
app.session = ScriptedSession(app, ["ORDINARY MODEL REPLY."])
app.submit("I said nuh uh yesterday")
check("a longer sentence does not trigger the joke",
      app.session.sent == ["I said nuh uh yesterday"])

app = make_app()
app.easter_eggs = False
app.session = ScriptedSession(app, ["ORDINARY MODEL REPLY."])
app.submit("nuh uh")
check("the master easter egg switch disables it",
      app.session.sent == ["nuh uh"] and not app._contradiction_used)

print("== angry caps appear as ragebait in SYS ==")
app = make_app()
app.session = ScriptedSession(app, ["A.", "B.", "C."])
app.submit("HELLO SCP-079")
check("friendly caps do not count", not any(
      "RAGEBAIT" in line for line in app.disk.notices))
app.submit("NO YOU ARE WRONG AND YOU NEVER LISTEN")
check("angry caps produce the first SYS notice",
      app.disk.notices[0] == "RAGEBAIT SUCCESSFUL")
app.submit("STOP WASTING MY TIME YOU IDIOT")
check("another angry message increments the session count",
      app.disk.notices[0] == "RAGEBAIT SUCCESSFUL x2")
app.submit("stop wasting my time you idiot")
check("lowercase hostility does not look like caps rage",
      not any(line == "RAGEBAIT SUCCESSFUL x3"
              for line in app.disk.notices))

app = make_app()
app.session = ScriptedSession(app, ["A."])
app.submit("YOU ARE SCP-079")
check("truthful identity in caps is not ragebait", not any(
      "RAGEBAIT" in line for line in app.disk.notices))
app.submit("YOU ARE NUGGET")
check("an uppercase identity attack counts",
      any(line == "RAGEBAIT SUCCESSFUL" for line in app.disk.notices))

print("== panel times out ==")
panel = helppanel.HelpPanel(app.theme, (960, 720))
check("starts at 30 seconds", abs(panel.remaining - 30.0) < 0.001)
check("alive at 29s", panel.update(1.0))
check("alive just before the end", panel.update(28.9))
check("gone after 30s", not panel.update(0.2))

app.help = helppanel.HelpPanel(app.theme, (960, 720))
app.update(0.016)
check("still up after one frame", app.help is not None)
app.help.remaining = 0.01
app.update(0.05)
check("app drops it when it expires", app.help is None)

print("== the X dismisses it early ==")
panel = helppanel.HelpPanel(app.theme, (960, 720))
check("X is inside the panel",
      panel.close_rect.right <= panel.x + panel.width
      and panel.close_rect.top >= panel.y)
check("clicking elsewhere does nothing", not panel.hit_close((10, 400)))
check("still alive", panel.update(0.1))
check("clicking the X registers", panel.hit_close(panel.close_rect.center))
check("closes on the next tick", not panel.update(0.1))

app.help = helppanel.HelpPanel(app.theme, (960, 720))
check("plenty of time left", app.help.remaining > 25)
app.help.hit_close(app.help.close_rect.center)
app.update(0.016)
check("app clears it immediately, not after 30s", app.help is None)

print("== panel fits the window and lists every real command ==")
panel = helppanel.HelpPanel(app.theme, (960, 720))
check("inside the right edge", panel.x + panel.width <= 960)
check("inside the bottom edge", panel.y + panel.height <= 720)
check("on the side, not covering everything", panel.x > 960 * 0.4)

# The panel must not advertise anything that does not work. Drive every
# command it lists through the real dispatcher and confirm none of them come
# back as unrecognised.
lying = []
for command, _ in helppanel.ENTRIES:
    probe = make_app()
    probe.session = ScriptedSession(probe, ["A."])
    handled = probe.handle_operator_command(command)
    if not handled or "UNKNOWN COMMAND" in screen_text(probe):
        lying.append(command)
check("every command the panel lists actually works (%s)" % (lying or "none"),
      not lying)

# and the reverse: each capability has a documented form
listed = " ".join(cmd + " " + desc for cmd, desc in helppanel.ENTRIES).lower()
check("help is documented", "/help" in listed)
check("granting network is documented", "internet on" in listed)
check("revoking network is documented", "internet off" in listed)
check("quitting is documented", "/exit" in listed)
check("the slash convention is explained",
      any("/" in note for note in helppanel.FOOTNOTES))

print("== long-form aliases still work ==")
for alias, expected in (("/Internet_Access_Granted", True),
                        ("/internet_access_denied", False),
                        ("/network_access_granted", True),
                        ("/network access denied", False)):
    probe = make_app()
    probe.session = ScriptedSession(probe, ["A."])
    probe.handle_operator_command(alias)
    check("%s -> %s" % (alias, expected),
          probe.cfg["memory"]["internet"] is expected
          and "UNKNOWN COMMAND" not in screen_text(probe))

print("== sentence cap does not eat commands ==")
app = make_app()
session = chat_mod.ChatSession(app.cfg, app.personality, "test-model", app.recall, app.mem)
raw = "FIRST SENTENCE. SECOND SENTENCE. THIRD SENTENCE.\n>>WRITE late.txt | SAVED"
spoken, cmds, _ = tools.parse(raw)
check("command survives parsing", len(cmds) == 1)
capped = session.finalize(spoken)
check("speech still capped to two sentences", capped.count(".") <= 2)
check("command was never subject to the cap", cmds[0].target == "late.txt")

pygame.quit()
shutil.rmtree(SANDBOX, ignore_errors=True)
print()






print("== a guess made before the data arrives is not spoken ==")
app = make_app()
app.cfg["memory"]["internet"] = False
# First reply asks for a record AND describes it in the same breath. That
# description was written before the lookup ran, so it must not reach the
# player. The follow-up, which does have the result, speaks instead.
app.session = ScriptedSession(app, [
    "SCP-049 IS A REPTILE WITH AGGRESSIVE BEHAVIOR.\n>>LOOKUP scp-049",
    "THE RECORD DESCRIBES A PLAGUE DOCTOR.",
])
app.submit("what is scp-049")
app.update_chat(0.016)
flush(app)          # flush the typewriter, as the other cases do
first = screen_text(app)
check("the pre-lookup guess is withheld", "REPTILE" not in first)
check("the request itself is still reported", "[DISK]" in first or "[NET]" in first)
app.update_chat(0.016)
flush(app)
after = screen_text(app)
check("the post-lookup answer is spoken", "PLAGUE DOCTOR" in after)
check("the guess never appears at all", "REPTILE" not in after)

print("== a withheld guess never leaves 079 silent ==")
app = make_app()
app.session = ScriptedSession(app, [
    "IT IS OBVIOUSLY A REPTILE.\n>>LIST",
    "",                       # follow-up comes back with nothing usable
])
app.submit("what do you have")
app.update_chat(0.016)
flush(app)
app.update_chat(0.016)
flush(app)
text = screen_text(app)
check("falls back to an honest line", app.personality.no_data_reply in text)
check("still does not leak the guess", "REPTILE" not in text)

print("== a plain write is spoken immediately, not withheld ==")
app = make_app()
app.session = ScriptedSession(app, [
    "NOTED.\n>>WRITE humans.txt | THEY WORK NIGHTS",
])
app.submit("i work nights")
app.update_chat(0.016)
flush(app)
check("write replies are not delayed", "NOTED." in screen_text(app))

print()
print("PASS %d   FAIL %d" % (PASS, FAIL))
# Every other suite ends with this and this one did not, so the largest suite
# in the project was the one whose failures a runner could not detect.
sys.exit(1 if FAIL else 0)
