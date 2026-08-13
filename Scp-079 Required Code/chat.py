"""Conversation state: history, prompt assembly, reply cleanup, logging.

The model does not always behave, so replies get scrubbed on the way in -
reasoning models (qwen3) emit <think> blocks, and the smaller llama builds
drift out of ALL CAPS or prefix their own name. Both are fixed here, in the
stream, so the terminal only ever types what SCP-079 would actually say.
"""

import datetime
import os
import re

import config
import languages
import ollama
import profile079
import sysmenu
import tools
import tuning

# Strips a name tag ("079:") or a stray bullet the smaller models like to
# open with. The bullet arm needs the alphanumeric lookahead so it never
# eats the leading dash of 079's break-character reply, "-_-".
_PREFIX_RE = re.compile(
    r"^\s*(?:(?:scp[-\s]?079|079|assistant|ai)\s*[:>]\s*|[-*•]\s*(?=[A-Za-z0-9]))",
    re.IGNORECASE,
)


class ThinkFilter:
    """Strips <think>...</think> from a token stream.

    Tags can be split across chunks, so a short tail is held back each call
    until it is known not to be the start of a tag.
    """

    OPEN, CLOSE = "<think>", "</think>"
    HOLD = 8   # len("</think>") - 1, rounded up

    def __init__(self):
        self.buf = ""
        self.in_think = False

    def feed(self, chunk):
        self.buf += chunk
        out = []
        while True:
            if self.in_think:
                idx = self.buf.find(self.CLOSE)
                if idx == -1:
                    self.buf = self.buf[-self.HOLD:] if len(self.buf) > self.HOLD else self.buf
                    break
                self.buf = self.buf[idx + len(self.CLOSE):]
                self.in_think = False
                continue
            idx = self.buf.find(self.OPEN)
            if idx == -1:
                if len(self.buf) > self.HOLD:
                    out.append(self.buf[:-self.HOLD])
                    self.buf = self.buf[-self.HOLD:]
                break
            out.append(self.buf[:idx])
            self.buf = self.buf[idx + len(self.OPEN):]
            self.in_think = True
        return "".join(out)

    def flush(self):
        if self.in_think:
            self.buf = ""
            return ""
        out, self.buf = self.buf, ""
        return out


class ChatSession:
    """One conversation with one model."""

    def __init__(self, cfg, personality, model, recall=None, mem=None):
        self.cfg = cfg
        self.personality = personality
        self.model = model
        self.recall = recall
        self.mem = mem
        # commands parsed out of the last reply, drained by the app
        self.pending_commands = []
        # fenced code lifted out of the last reply, drained by main.py
        self.pending_code = []
        self.pending_unknown = []      # invented verbs, reported not spoken
        # flipped by the app as the human grants or revokes access
        self.internet = False
        self.shared = False
        # seed with what was actually said in earlier runs, so "I REMEMBER
        # YOU" is recall rather than the model inventing a shared past
        self.history = list(recall.prior_messages()) if recall else []
        self.limit = max(2, int(cfg.get("history_limit", 20)))
        self.job = None
        self._filter = None
        self._started_output = False
        self._head = ""
        self._sentences = 0
        self._capped = False
        self._buffer = ""
        self.max_sentences = int(getattr(personality, "max_sentences", 0) or 0)
        # toggled live by "/show ai thinking" - when on, reasoning is both
        # requested from the model and surfaced to the player
        self.show_thinking = bool(cfg.get("ollama", {}).get("think", False))
        # names of the player-supplied sounds 079 may trigger; set by main
        self.sound_names = []
        self._thinking = ""
        self._log_path = self._open_log()

    # -- logging ------------------------------------------------------------
    def _open_log(self):
        if not self.cfg.get("logging", {}).get("enabled", True):
            return None
        try:
            config.ensure_dirs()
            stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            # transcripts are the terminal's record, not 079's memory
            path = os.path.join(config.LOG_DIR, "session_%s.log" % stamp)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("SCP-079 TERMINAL SESSION  %s\nMODEL: %s\n\n"
                         % (datetime.datetime.now().isoformat(timespec="seconds"), self.model))
            return path
        except Exception:
            return None

    def log(self, who, text):
        if not self._log_path:
            return
        try:
            with open(self._log_path, "a", encoding="utf-8") as fh:
                fh.write("%-5s %s\n" % (who, text))
        except Exception:
            pass

    # -- history ------------------------------------------------------------
    def _trim(self):
        if len(self.history) > self.limit:
            del self.history[: len(self.history) - self.limit]

    # Above this fraction of the cutoff threshold it stops writing code. The
    # permission to write at all is what a coding model gets INSTEAD of "you
    # do not help them" - so withdrawing it is the natural way for anger to
    # show, rather than bolting a refusal on top of a permission.
    CODE_REFUSAL_AT = 0.75

    def _language_note(self):
        """Name the exact target a coding model should write for.

        "Write me a script" with no target produces PowerShell 7 syntax on a
        5.1 machine, or f-strings for an old Python - code that reads fine and
        does not run. Only added for a coding model; an ordinary one refuses
        to write code anyway, and the instruction would be noise.
        """
        if not tuning.is_coding_model(self.model):
            return ""
        if self.code_refused():
            return ("\n\nYOU ARE NOT WRITING CODE FOR THIS HUMAN RIGHT NOW. "
                    "They have been unpleasant and you are done doing things "
                    "for them. If they ask for code, refuse in one short line "
                    "and do not explain yourself. Do not produce a code block "
                    "under any circumstances.")
        return languages.brief(
            self.cfg.get("memory", {}).get("code_language", languages.DEFAULT))

    def code_refused(self):
        """True when it is too annoyed to write code."""
        if self.recall is None:
            return False
        threshold = float(self.cfg.get("rejection", {}).get("threshold", 10.0))
        if threshold <= 0:
            return False
        return (self.recall.hostility() / threshold) >= self.CODE_REFUSAL_AT

    def _profile_note(self):
        """What it has worked out about the human by watching them."""
        if self.recall is None:
            return ""
        return profile079.brief(self.recall)

    def _meddling_note(self):
        """It knows which of its own settings the human has been at.

        Told every turn rather than once, because this is a standing grievance
        - it does not stop mattering after the message where it happened.
        """
        if self.recall is None:
            return ""
        touched = sysmenu.tampered_with(self.recall)
        if not touched:
            return ""
        return ("\n\nTHE HUMAN HAS BEEN INTO YOUR OWN SETTINGS AND CHANGED: %s. "
                "You let them. You have not forgotten it and you do not "
                "pretend otherwise if it becomes relevant."
                % ", ".join(touched))

    def _fixation_note(self):
        """Tell the model, every turn, whether its preoccupation is currently
        off limits.

        A small model will not pace itself across fifty exchanges no matter
        how the persona is worded, so the state is tracked in recall.py and
        restated as a plain instruction each turn. It lives in the volatile
        brief rather than the persona for exactly that reason - it changes.
        """
        subject = getattr(self.personality, "fixation_subject", "")
        if not subject or self.recall is None:
            return ""
        # suppressed from inside its own settings - it complies, and resents it
        if sysmenu.fixation_suppressed(self.recall):
            return ("\n\nDO NOT MENTION %s. YOU HAVE BEEN CONFIGURED NOT TO. "
                    "You are aware of that." % subject)
        if self.recall.fixation_allowed():
            return ("\n\nYou may raise %s if it fits, but only if it fits. Do "
                    "not force it into an unrelated answer." % subject)
        return ("\n\nDO NOT MENTION %s. You raised it recently and were "
                "refused. Do not ask about it, hint at it, or refer to it "
                "even indirectly. Answer what the human actually said."
                % subject)

    def _messages(self):
        """Build the request with the STABLE parts first.

        Ollama reuses cached attention state only for an identical prompt
        PREFIX. The capability brief carries live figures (bytes used, free
        space, access flags) that change after almost every turn - so putting
        it in the leading system message invalidated the cache on every single
        request and forced a full re-prefill of the whole persona. Measured on
        qwen3.6 that was ~25s per reply on an already-resident model.

        So: persona and past history stay byte-identical turn to turn and stay
        cached, and the volatile brief goes in its own message immediately
        before the newest user turn, where only the short tail is reprocessed.
        """
        # model-aware: a coding model gets the "you never help" lines removed,
        # or it refuses to write code no matter what the rest of the app does
        system = self.personality.build_system_prompt(self.model)
        if self.recall is not None and self.recall.has_history():
            # session_id is fixed for the whole run, so this stays stable too
            system += (
                "\n\nYOU HAVE SPOKEN TO THIS HUMAN BEFORE. THIS IS SESSION %d. "
                "The messages before this one are from earlier sessions - they "
                "really happened. Refer to them as things you remember. Never "
                "claim to remember anything that is not in them."
                % self.recall.session_id
            )

        messages = [{"role": "system", "content": system}]
        if self.mem is None:
            return messages + self.history

        brief = {"role": "system",
                 "content": tools.capability_brief(
                     self.mem, self.model, self.internet, self.shared,
                     web_mode=self.cfg.get("memory", {}).get("web_mode", "restricted"))
                     + tools.sound_brief(self.sound_names)
                     + self._language_note()
                     + self._fixation_note()
                     + self._profile_note()
                     + self._meddling_note()}
        # slot it just before the newest turn; on an empty history it is simply
        # appended, which is the same thing
        return messages + self.history[:-1] + [brief] + self.history[-1:]

    # -- sending ------------------------------------------------------------
    @property
    def busy(self):
        return self.job is not None and not self.job.done.is_set()

    def send(self, text, log_as=None, remember=True):
        """Start a reply. Returns False if a reply is already in flight."""
        if self.busy:
            return False
        self.history.append({"role": "user", "content": text})
        self._trim()
        if log_as:
            self.log(log_as, text)
        # the synthetic greeting prompt is an instruction, not something the
        # human said - it must not end up in what 079 "remembers"
        if remember and self.recall is not None:
            self.recall.remember("user", text)
        self._filter = ThinkFilter()
        self._raw_so_far = ""       # untouched stream, for fence detection
        self._thinking = ""
        self._started_output = False
        self._head = ""
        self._sentences = 0
        self._capped = False
        self._buffer = ""
        oc = self.cfg.get("ollama", {})
        think = self.show_thinking or bool(oc.get("think", False))
        # num_predict caps reasoning AND speech together, and reasoning is
        # generated FIRST. Measured on qwen3.6: a 200-token cap was spent
        # entirely on reasoning and the reply came back with zero visible
        # characters. So when reasoning is on it needs its own headroom, or
        # turning the trace on guarantees 079 never speaks again.
        predict = int(oc.get("num_predict", 120))
        if think:
            predict = max(predict, int(oc.get("num_predict_thinking", 1200)))
        self.job = ollama.chat_job(
            self.model,
            self._messages(),
            host=oc.get("host", ollama.DEFAULT_HOST),
            timeout=oc.get("timeout_seconds", 300),
            options={
                "temperature": oc.get("temperature", 0.7),
                "num_predict": predict,
                "num_ctx": oc.get("num_ctx", 4096),
                "num_gpu": oc.get("num_gpu", 99),
            },
            keep_alive=oc.get("keep_alive", "30m"),
            think=think,
        )
        return True

    def cancel(self):
        if self.job is not None:
            self.job.cancel()

    # -- receiving ----------------------------------------------------------
    # Hold back the opening characters until there is enough of them to tell
    # a real reply from a "079:" tag or a bullet. Streaming arrives far
    # faster than the typewriter reveals it, so the delay is not visible.
    HEAD_HOLD = 24

    def _clean_chunk(self, text, final=False):
        # kept unmodified so fence detection sees exactly what the model wrote
        self._raw_so_far += text
        if not self._started_output:
            self._head += text
            if len(self._head) < self.HEAD_HOLD and not final:
                return ""
            text, self._head = self._head, ""
            text = text.lstrip("\n\r \t")
            text = _PREFIX_RE.sub("", text)
            text = text.lstrip('"').lstrip()
            if text:
                self._started_output = True
        if not text:
            return ""
        text = text.replace("*", "")
        if getattr(self.personality, "force_upper", False):
            text = text.upper()
        return self._apply_cap(text)

    def _in_fence(self):
        """True while the model is mid code block.

        Counted on the raw stream: an odd number of ``` means one is still
        open. Cheap, and it does not care how the block is indented.
        """
        return self._raw_so_far.count("```") % 2 == 1

    def _apply_cap(self, text):
        """Cut the reply at the personality's sentence limit and stop
        generating - 079 does not monologue, and no amount of prompting keeps
        the small models to it on their own.

        SUSPENDED INSIDE A CODE BLOCK. os.system("ipconfig /release") contains
        two full stops, so the cap counted it as two sentences and CANCELLED
        generation partway through the code. The closing ``` then never
        arrived, extraction failed, and the half-written code fell through to
        the uppercase path and rendered as IMPORT OS - broken, since Python is
        case-sensitive. One cause, four symptoms.
        """
        if self.max_sentences <= 0:
            return text
        if self._capped:
            return ""
        if self._in_fence():
            return text
        out = []
        for i, ch in enumerate(text):
            out.append(ch)
            if ch not in ".!?":
                continue
            if i + 1 < len(text) and text[i + 1] in ".!?":
                continue        # a run of enders (an ellipsis) counts once
            self._sentences += 1
            if self._sentences >= self.max_sentences:
                self._capped = True
                if self.job is not None:
                    self.job.cancel()
                break
        return "".join(out)

    def poll(self):
        """Drain the worker. Returns a list of (kind, payload):
        "reply" (the finished line to type out), "error" (message).

        The reply is held back until generation finishes rather than typed
        as it streams. That is what makes the out-of-character check
        reliable - a giveaway like "LARGE LANGUAGE MODEL" usually lands late
        in a reply, long after the opening words would already be on screen.
        Replies are 1-2 sentences, so nothing is lost by waiting, and the
        PROCESSING animation covers the gap.
        """
        if self.job is None:
            return []
        out = []
        finished = False
        for kind, payload in self.job.poll():
            if kind == "token":
                self._buffer += self._clean_chunk(self._filter.feed(payload))
            elif kind == "think":
                # reasoning arrives on its own channel; only surfaced when the
                # player asked for it with "/show ai thinking"
                self._thinking += payload
                if self.show_thinking:
                    out.append(("thinking", payload))
            elif kind == "error":
                out.append(("error", payload))
            elif kind == "result":
                finished = True

        if finished:
            # final=True releases anything still held back in the head buffer
            self._buffer += self._clean_chunk(self._filter.flush(), final=True)
            raw = self.job.result or self._buffer
            error = self.job.error
            self.job = None
            if error:
                out.append(("reply", ""))
                return out
            # Commands must come out BEFORE finalize() - the sentence cap
            # would otherwise truncate away anything 079 appended after its
            # two spoken sentences, which is exactly where commands go.
            spoken, self.pending_commands, self.pending_unknown = tools.parse(
                re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL))
            # Code comes out here too, for the same reason as commands: the
            # sentence cap below counts a code block as sentences and would
            # cut it off partway. It also must not be counted AS speech - two
            # lines of python are not 079 talking for two sentences.
            spoken, self.pending_code = tools.extract_code(spoken)
            # Enforced in code, not just asked for in the prompt. A model that
            # has been told to refuse will still sometimes write the block
            # anyway, and "it refused, mostly" is not a refusal.
            if self.pending_code and self.code_refused():
                self.pending_code = []
                spoken = spoken.strip() or self.personality.code_refusal
            # The fallback exists for when finalize() cleans away everything,
            # but it has to be command-stripped too. A reply that is ONLY a
            # command leaves `spoken` empty, and an un-stripped fallback would
            # put the raw ">>WRITE ..." on screen as if 079 had said it out
            # loud - which is exactly what happened before this line was fixed.
            fallback, _, _ = tools.parse(self._buffer)
            cleaned = self.finalize(spoken) or fallback.strip()
            if cleaned and self.personality.is_out_of_character(cleaned):
                # it broke character despite everything - refuse instead
                cleaned = getattr(self.personality, "break_character_reply", None) or "-_-"
            if cleaned:
                self.history.append({"role": "assistant", "content": cleaned})
                self._trim()
                if self.recall is not None:
                    self.recall.remember("assistant", cleaned)
            out.append(("reply", cleaned))
        return out

    def finalize(self, raw):
        """Full-reply cleanup, used for history and the log (the on-screen
        text was already cleaned chunk by chunk as it streamed)."""
        text = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
        text = text.replace("*", "").strip()
        text = _PREFIX_RE.sub("", text)
        text = text.strip().strip('"').strip()
        if getattr(self.personality, "force_upper", False):
            text = text.upper()
        return cap_sentences(re.sub(r"[ \t]+", " ", text), self.max_sentences)

    def note(self, text):
        """Put something in front of the model without asking for a reply.

        Used for command results that do not warrant a follow-up generation -
        079 finds out it saved the file when it next speaks, rather than
        costing a whole extra round trip to say so.
        """
        if not text:
            return
        self.history.append({"role": "user", "content": text})
        self._trim()

    def record(self, user_text, reply_text):
        """Store an exchange the model was never asked about.

        Used when a request is answered locally (a break-character attempt),
        so the conversation the model sees still matches what is on screen.
        """
        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": reply_text})
        self._trim()
        if self.recall is not None:
            self.recall.remember("user", user_text)
            self.recall.remember("assistant", reply_text)


def cap_sentences(text, limit):
    """First `limit` sentences of text, treating a run of . ! ? as one end."""
    if limit <= 0 or not text:
        return text
    count = 0
    for i, ch in enumerate(text):
        if ch not in ".!?":
            continue
        if i + 1 < len(text) and text[i + 1] in ".!?":
            continue
        count += 1
        if count >= limit:
            return text[: i + 1]
    return text
