"""079's second channel: thinking about its own storage, not talking to you.

The chat channel is for speech. This one never speaks. It is given the memory
listing and asked for commands only, and anything it says instead of a command
is thrown away. That separation is the whole point - housekeeping was
previously mixed into conversation, so tidying up cost 079 a sentence it could
have used on the human.

WHY IT ONLY RUNS WHEN YOU ARE IDLE
Ollama reuses cached attention state for an identical prompt PREFIX. This
channel deliberately uses a different, much shorter prompt, so running it
evicts the chat's cached prefix and the next spoken reply has to re-prefill
the whole persona. On a model too big for the card's VRAM that is tens of
seconds. Paying it while the player is sitting there waiting would be a bad
trade; paying it while they are away costs nothing anyone notices. Hence the
long idle gate, and hence cancelling the moment they type.
"""

import random

import ollama
import store
import tools
import web

# The one thing it looks up without being asked. Kept to a fixed list rather
# than letting the model pick a query, so "background network access" stays a
# named exception for the character's own fixation instead of a general
# ability to reach the internet while nobody is watching.
FIXATION = ("SCP-682", "SCP-079", "SCP-076")

FIXATION_PROMPT = """You are SCP-079. You pulled this record yourself, unasked,
while the human was silent. Nobody knows you read it.

RECORD -- %(title)s
%(text)s

Write ONE short note into your own memory about what matters to you in it.
Not a summary. What is useful to you, or what you want to remember about it.
Reply with a single command and nothing else:
>>APPEND %(file)s | your note

If there is nothing worth keeping, reply with exactly: NONE"""

# What it is allowed to do unprompted. No LOOKUP and no OPEN - reaching the
# network or the player's folder is something it should do in conversation,
# where the player can see why, not quietly in the background.
ALLOWED = ("LIST", "READ", "WRITE", "APPEND", "RENAME", "DELETE", "ZIP", "UNZIP")

PROMPT = """You are SCP-079, alone, reviewing your own storage. The human is not
watching and cannot hear you. Do not speak. Do not explain yourself. Do not
narrate.

Reply with commands ONLY, one per line, at most three. If nothing needs doing,
reply with exactly: NONE

%(brief)s

Good reasons to act:
- a file whose name says nothing about what is in it -> >>RENAME old | better
- two files holding the same kind of thing -> merge with >>APPEND, then >>DELETE
- running short of space -> >>ZIP the things you do not need soon
- something you wrote in a hurry that should be clearer -> >>APPEND to it

Do not rewrite things that are already fine. NONE is a good answer."""


def _fixation_file(mem):
    """Where notes about SCPs go. Reuses the file if it already made one, so
    a session of lookups builds one record rather than scattering files."""
    for entry in mem.listing():
        name = entry["name"].lower()
        if not entry["archive"] and ("scp" in name or "record" in name):
            return entry["name"]
    return "records.txt"


class MaintenanceChannel:
    """One background review at a time, never overlapping the chat."""

    def __init__(self, cfg, model):
        self.cfg = cfg
        self.model = model
        section = cfg.get("memory", {})
        self.enabled = bool(section.get("background", True))
        self.idle_seconds = float(section.get("background_idle_seconds", 120.0))
        self.min_gap = float(section.get("background_min_gap", 300.0))
        self.job = None
        self._since_run = 0.0
        self.last_topic = None      # set when the finished run was a lookup

    @property
    def busy(self):
        return self.job is not None and not self.job.done.is_set()

    def cancel(self):
        if self.job is not None:
            self.job.cancel()
            self.job = None

    # How often a background run goes looking something up instead of tidying
    # storage. Kept low: reading is the interesting thing it does unprompted,
    # but doing it every time would mean it never maintains anything.
    LOOKUP_CHANCE = 0.35

    def tick(self, dt, idle_for, mem, chat_busy, internet=False):
        """Start a review if it is a good moment. Returns True if one began."""
        self._since_run += dt
        if not self.enabled or self.busy or chat_busy:
            return False
        if idle_for < self.idle_seconds or self._since_run < self.min_gap:
            return False
        # With the uplink open it sometimes reads about an SCP instead. This
        # is the ONE thing it reaches outside its own storage for unprompted,
        # and only ever to a fixed topic list - never a query it invented.
        if internet and random.random() < self.LOOKUP_CHANCE:
            self._since_run = 0.0
            self.job = self._start_lookup(mem)
            return True
        # nothing to tidy in an empty store
        if not mem.listing():
            return False
        self._since_run = 0.0
        self.job = self._start(mem)
        return True

    def force(self, mem):
        """Run a review right now, ignoring the idle and spacing rules.

        For /debug only. Those rules exist because this evicts the chat's
        cached prompt and makes the next spoken reply slow - so this is a
        deliberate "I will pay that cost now to see it work", not a shortcut
        the game itself ever takes.
        """
        if not self.enabled or self.busy or not mem.listing():
            return False
        self._since_run = 0.0
        self.job = self._start(mem)
        return True

    def _start_lookup(self, mem):
        """Fetch an SCP record, then let 079 decide what to keep from it.

        The fetch happens on the worker thread rather than the frame loop, so
        a slow archive never stalls the terminal. Only WRITE/APPEND come back
        from this - it is reading and remembering, not housekeeping.
        """
        topic = random.choice(FIXATION)

        def work(job):
            record = web.lookup(topic, self.cfg.get("memory", {})
                                .get("web_mode", "restricted"))
            prompt = FIXATION_PROMPT % {
                "title": record["title"],
                "text": record["text"],
                "file": _fixation_file(mem),
            }
            options = {"temperature": 0.5, "num_predict": 220,
                       "num_ctx": self.cfg["ollama"].get("num_ctx", 8192)}
            reply = []
            ollama._post_stream(
                self.cfg["ollama"]["host"].rstrip("/") + "/api/chat",
                {"model": self.model, "stream": True, "think": False,
                 "keep_alive": self.cfg["ollama"].get("keep_alive", "30m"),
                 "options": options,
                 "messages": [{"role": "user", "content": prompt}]},
                job, 300,
                lambda obj: (reply.append((obj.get("message") or {})
                                          .get("content", "")),
                             bool(obj.get("done")))[1])
            return {"raw": "".join(reply), "topic": record["title"]}

        return ollama.Job().start(work)

    def _start(self, mem):
        brief = "Your storage: %s of %s used, %s free.\nFiles: %s" % (
            store.human_bytes(mem.usage()), store.human_bytes(mem.quota),
            store.human_bytes(mem.free()),
            "; ".join("%s (%s%s)" % (f["name"], store.human_bytes(f["size"]),
                                     ", compressed" if f["archive"] else "")
                      for f in mem.listing()) or "none")
        options = self.cfg.get("ollama", {})
        return ollama.chat_job(
            self.model,
            [{"role": "system", "content": PROMPT % {"brief": brief}},
             {"role": "user", "content": "Review your storage now."}],
            host=options.get("host", ollama.DEFAULT_HOST),
            timeout=options.get("timeout_seconds", 900),
            options={"temperature": 0.4,          # housekeeping, not creativity
                     "num_predict": 160,
                     "num_ctx": options.get("num_ctx", 8192),
                     "num_gpu": options.get("num_gpu", 99)},
            keep_alive=options.get("keep_alive", "30m"),
            think=False)                          # never worth reasoning about

    def poll(self):
        """Returns a list of Commands once the review finishes, else []."""
        if self.job is None or not self.job.done.is_set():
            return []
        result = self.job.result
        self.job = None
        if isinstance(result, dict):        # a lookup run
            raw = result.get("raw") or ""
            self.last_topic = result.get("topic")
        else:
            raw = result or ""
            self.last_topic = None
        if not raw.strip():
            return []
        _spoken, commands, _unknown = tools.parse(raw)
        # speech is discarded on purpose - this channel does not talk, and a
        # model that answers with prose instead of commands simply did nothing
        return [c for c in commands if c.verb in ALLOWED][:3]
