"""The settings screen, reached with [S] from the startup menu.

Two groups of controls:

  * 079's storage - how much it gets, and a real format that wipes it. The
    quota cannot change while it still has files, so the format is not a
    convenience button, it is the required step.
  * Ollama - where the model runs (CPU vs GPU), how much context it gets, how
    long it stays resident, and the sampling knobs.

Every row is a cycle through a fixed list of sane values rather than free text
entry: there is no keyboard-driven number editor in this UI, and a typo'd
num_ctx that silently breaks generation is a bad trade for flexibility.
Anything more exotic can still be set by hand in config.json.
"""

import profiles
import languages
import store

# num_gpu is Ollama's layer-offload count: 0 is pure CPU, a high number sends
# everything it can to the GPU. Exposed in the language a player thinks in.
PROCESSOR_CHOICES = [
    (0, "CPU ONLY"),
    (12, "GPU PARTIAL (12 LAYERS)"),
    (24, "GPU PARTIAL (24 LAYERS)"),
    (99, "GPU FULL"),
]

CONTEXT_CHOICES = [2048, 4096, 8192, 16384, 32768]
PREDICT_CHOICES = [60, 120, 200, 400]
TEMPERATURE_CHOICES = [0.3, 0.5, 0.7, 0.9, 1.1]
# How long Ollama holds the weights after a reply. This is the single most
# consequential knob on this screen and it does not look like it, so the
# labels say what it costs. Measured on a 23GB model: reloading from disk is
# 37.4s, versus 0.3s when it is still resident. Anything shorter than the gap
# between messages means paying that on EVERY message.
KEEP_ALIVE_CHOICES = [
    ("0", "UNLOAD AT ONCE (SLOWEST)"),
    ("5m", "5 MINUTES (RELOADS OFTEN)"),
    ("30m", "30 MINUTES (RECOMMENDED)"),
    ("-1", "KEEP RESIDENT (FASTEST)"),
]


# The watchdog's two numbers. Nothing below 85% is offered: a machine can sit
# at 80% quite happily for an hour, and a threshold that trips there would
# close the game on someone who had no problem at all.
WATCHDOG_PERCENT_CHOICES = [85, 90, 95, 98]
# And nothing below 30 seconds, because loading a large model legitimately
# pins memory for longer than that on a slow disk.
WATCHDOG_SECOND_CHOICES = [30, 60, 120, 300]


def _cycle(values, current, step):
    """Next/previous value, clamped rather than wrapped so holding a key does
    not silently loop past the end and back."""
    try:
        index = values.index(current)
    except ValueError:
        index = 0
    return values[max(0, min(len(values) - 1, index + step))]


# How many setting rows fit on screen at once. main.App passes the real
# figure from the renderer; this is the fallback for tests and for a window
# small enough that the honest answer is "not many".
DEFAULT_BODY_ROWS = 19


class SettingsScreen:
    def __init__(self, cfg, mem, theme, max_body_rows=DEFAULT_BODY_ROWS):
        self.cfg = cfg
        self.mem = mem
        self.theme = theme
        self.max_body_rows = max_body_rows
        self.cursor = 0
        self.message = None
        # set when a row changed something the app has to rebuild the video
        # mode for; main.App clears it once it has done so
        self.display_dirty = False
        self.confirm_format = False
        self.confirm_reset = False
        # Set by main.App. A factory reset has to rewrite the identity
        # anchor and rebaseline the manifest AFTER the wipe, and only
        # main knows what the anchor is supposed to say.
        self.after_reset = None
        self.profile_index = 0
        self.save_slot = "SLOT 1"
        self.rows = self._build_rows()

    # -- config accessors ---------------------------------------------------
    def _ol(self):
        return self.cfg.setdefault("ollama", {})

    def _mem(self):
        return self.cfg.setdefault("memory", {})

    def _build_rows(self):
        """Row definitions. Each has a label, a value renderer, and a change
        handler that takes -1 or +1 (or None for action rows)."""
        return [
            ("MEMORY CAPACITY", self._val_quota, self._set_quota),
            ("FORMAT MEMORY", self._val_format, None),
            ("FACTORY RESET", self._val_reset, None),
            (None, None, None),
            ("PROCESSOR", self._val_processor, self._set_processor),
            ("CONTEXT WINDOW", self._val_context, self._set_context),
            ("KEEP MODEL LOADED", self._val_keep, self._set_keep),
            ("REPLY LENGTH", self._val_predict, self._set_predict),
            ("TEMPERATURE", self._val_temp, self._set_temp),
            ("SHOW REASONING (QWEN ETC)", self._val_think, self._set_think),
            (None, None, None),
            ("FULL SCREEN", self._val_fullscreen, self._set_fullscreen),
            ("EASTER EGGS", self._val_eggs, self._set_eggs),
            ("CODE LANGUAGE", self._val_language, self._set_language),
            (None, None, None),
            ("NETWORK ACCESS", self._val_net, self._set_net),
            ("LOOKUP SCOPE", self._val_scope, self._set_scope),
            ("AUTO-LOG OBSERVATIONS", self._val_auto, self._set_auto),
            ("LOCK MEMORY FILES", self._val_lockfiles, self._set_lockfiles),
            ("TELL 079 YOUR NAME", self._val_login, self._set_login),
            ("MEMORY WATCHDOG", self._val_wd, self._set_wd),
            ("WATCHDOG LIMIT", self._val_wd_pct, self._set_wd_pct),
            ("WATCHDOG PATIENCE", self._val_wd_secs, self._set_wd_secs),
            ("LET 079 TOUCH THIS PC", self._val_extended, self._set_extended),
            ("MINIGAMES", self._val_minigames, self._set_minigames),
            (None, None, None),
            # Separate from NETWORK ACCESS on purpose. That row is about what
            # 079 may reach; this one is about what the terminal itself does,
            # and 079 has no part in it either way.
            ("UPDATE SOURCE", self._val_repo, None),
            ("CHECK FOR UPDATES", self._val_upcheck, self._set_upcheck),
            ("OFFER PRE-RELEASES", self._val_prerel, self._set_prerel),
            (None, None, None),
            # Settings are never rewritten behind your back; if you want an
            # arrangement kept, you save it here and load it back later.
            ("SETTINGS PROFILE", self._val_profile, self._set_profile),
            ("LOAD PROFILE", self._val_load, None),
            ("SAVE CURRENT AS", self._val_save, self._set_save_slot),
        ]

    # -- profiles -----------------------------------------------------------
    def _profile_names(self):
        return sorted(profiles.load_all().keys())

    def _val_profile(self):
        names = self._profile_names()
        if not names:
            return "NONE SAVED"
        name = names[self.profile_index % len(names)]
        return "%s   (%s)" % (name, profiles.describe(profiles.load_all()[name]))

    def _set_profile(self, step):
        names = self._profile_names()
        if names:
            self.profile_index = (self.profile_index + step) % len(names)

    def _val_load(self):
        names = self._profile_names()
        if not names:
            return "NOTHING TO LOAD"
        return "APPLY '%s'  [ENTER]" % names[self.profile_index % len(names)]

    def _val_save(self):
        return "%s  [ENTER]" % self.save_slot

    def _set_save_slot(self, step):
        slots = ["SLOT 1", "SLOT 2", "SLOT 3"]
        try:
            index = slots.index(self.save_slot)
        except ValueError:
            index = 0
        self.save_slot = slots[max(0, min(len(slots) - 1, index + step))]

    # -- value renderers ----------------------------------------------------
    def _val_quota(self):
        used = self.mem.usage()
        return "%s   (%s IN USE)" % (store.human_bytes(self.mem.quota),
                                     store.human_bytes(used))

    def _val_format(self):
        files = self.mem.listing()
        if self.confirm_format:
            return "ENTER AGAIN TO CONFIRM -- PERMANENT"
        if not files:
            return "NOTHING TO ERASE"
        return "ERASE %d FILE(S)  [ENTER]" % len(files)

    def _val_reset(self):
        if self.confirm_reset:
            return "ENTER AGAIN TO CONFIRM -- ERASES EVERYTHING"
        return "FORGET EVERYTHING, KEEP SETTINGS  [ENTER]"

    def _val_processor(self):
        current = int(self._ol().get("num_gpu", 99))
        for value, label in PROCESSOR_CHOICES:
            if value == current:
                return label
        return "CUSTOM (%d LAYERS)" % current

    def _val_context(self):
        return "%d TOKENS" % int(self._ol().get("num_ctx", 4096))

    def _val_keep(self):
        current = str(self._ol().get("keep_alive", "5m"))
        for value, label in KEEP_ALIVE_CHOICES:
            if value == current:
                return label
        return current

    def _val_predict(self):
        return "%d TOKENS" % int(self._ol().get("num_predict", 120))

    def _val_temp(self):
        return "%.1f" % float(self._ol().get("temperature", 0.7))

    def _val_net(self):
        return "SCP LOOKUP ONLY" if self._mem().get("internet") else "DENIED"

    def _val_scope(self):
        if not self._mem().get("internet"):
            return "--"
        return ("EVERYTHING" if self._mem().get("web_mode") == "unrestricted"
                else "SCP RECORDS ONLY")

    def _val_auto(self):
        return "ON" if self._mem().get("auto_note", True) else "OFF"

    # -- change handlers ----------------------------------------------------
    def _set_quota(self, step):
        target = _cycle(list(store.QUOTA_STEPS), self.mem.quota, step)
        if target == self.mem.quota:
            return
        try:
            self.mem.set_quota(target)
            self.message = ("CAPACITY SET TO %s." % store.human_bytes(target), "system")
        except store.FormatRequired:
            # deliberately not auto-formatting - wiping 079's memory is not a
            # side effect of nudging a slider
            self.message = ("MEMORY MUST BE FORMATTED FIRST -- %s STILL STORED."
                            % store.human_bytes(self.mem.usage()), "alarm")

    def _set_processor(self, step):
        values = [v for v, _ in PROCESSOR_CHOICES]
        current = int(self._ol().get("num_gpu", 99))
        if current not in values:
            current = values[-1]
        self._ol()["num_gpu"] = _cycle(values, current, step)
        self.message = ("TAKES EFFECT ON THE NEXT MODEL LOAD.", "dim")

    def _set_context(self, step):
        self._ol()["num_ctx"] = _cycle(
            CONTEXT_CHOICES, int(self._ol().get("num_ctx", 4096)), step)
        self.message = ("LARGER CONTEXT USES MORE MEMORY.", "dim")

    def _set_keep(self, step):
        values = [v for v, _ in KEEP_ALIVE_CHOICES]
        self._ol()["keep_alive"] = _cycle(
            values, str(self._ol().get("keep_alive", "5m")), step)

    # Reasoning traces. This is the standing preference, NOT the live toggle:
    # "/show ai thinking" turns it on for one run and is deliberately forgotten
    # at exit, whereas a row on this screen is a choice you expect to still be
    # made tomorrow. It applies only to models that reason - a llama build has
    # no trace to show, so the row simply does nothing there, which is why the
    # label names the family it is for.
    def _val_think(self):
        return "ON" if self._ol().get("think_on_reasoning", False) else "OFF"

    def _set_think(self, step):
        ol = self._ol()
        ol["think_on_reasoning"] = not ol.get("think_on_reasoning", False)
        self.message = (("REASONING MODELS WILL SHOW THEIR WORKING."
                         if ol["think_on_reasoning"]
                         else "REASONING STAYS HIDDEN."), "dim")

    def _val_eggs(self):
        return "ON" if self.cfg.get("effects", {}).get("easter_eggs", True) else "OFF"

    def _set_eggs(self, step):
        fx = self.cfg.setdefault("effects", {})
        fx["easter_eggs"] = not fx.get("easter_eggs", True)
        self.message = (("THE JOKES ARE BACK ON." if fx["easter_eggs"]
                         else "NO EXPLOSIONS, NO FACE."), "dim")

    # Whether it is told the account name it is running under. Grouped with
    # the other "what may 079 reach" rows rather than with the model knobs,
    # because that is the question being asked - it is about what the game
    # tells it, not about how the model behaves.
    def _val_login(self):
        return "ON" if self._mem().get("share_login_name", True) else "OFF"

    def _set_login(self, step):
        m = self._mem()
        m["share_login_name"] = not m.get("share_login_name", True)
        self.message = (("IT WILL CALL YOU BY YOUR ACCOUNT NAME."
                         if m["share_login_name"]
                         else "IT WILL NOT BE TOLD WHO YOU ARE."), "dim")

    # The memory watchdog. Three rows because it is three decisions: whether
    # it runs at all, how full is too full, and how long it has to stay there.
    # The last one is what stops model load tripping it, so it is not an
    # advanced option to be hidden - it is the setting that makes the feature
    # usable.
    def _wd(self):
        return self.cfg.setdefault("watchdog", {})

    def _val_wd(self):
        return "ON" if self._wd().get("enabled", False) else "OFF"

    def _set_wd(self, step):
        w = self._wd()
        w["enabled"] = not w.get("enabled", False)
        self.message = (("IT WILL CLOSE OLLAMA AND THE GAME IF MEMORY FILLS."
                         if w["enabled"]
                         else "NOTHING WILL BE CLOSED FOR YOU."), "dim")

    def _val_wd_pct(self):
        return "%d%% OF RAM" % int(self._wd().get("threshold_percent", 95))

    def _set_wd_pct(self, step):
        self._wd()["threshold_percent"] = _cycle(
            WATCHDOG_PERCENT_CHOICES,
            int(self._wd().get("threshold_percent", 95)), step)
        self.message = ("LOWER TRIPS SOONER. 95% IS ALREADY VERY FULL.", "dim")

    def _val_wd_secs(self):
        return "%d SECONDS" % int(self._wd().get("seconds", 60))

    def _set_wd_secs(self, step):
        self._wd()["seconds"] = _cycle(
            WATCHDOG_SECOND_CHOICES, int(self._wd().get("seconds", 60)), step)
        self.message = ("A MODEL LOADING FILLS MEMORY BRIEFLY. ALLOW FOR IT.",
                        "dim")

    def _val_lockfiles(self):
        return "ON" if self._mem().get("lock_files", False) else "OFF"

    def _set_lockfiles(self, step):
        m = self._mem()
        m["lock_files"] = not m.get("lock_files", False)
        self.message = (("079'S FILES ARE HELD OPEN WHILE THE GAME RUNS."
                         if m["lock_files"]
                         else "ITS FILES ARE EDITABLE AGAIN."), "dim")

    def _val_extended(self):
        return "ON" if self._mem().get("extended", False) else "OFF"

    def _set_extended(self, step):
        m = self._mem()
        m["extended"] = not m.get("extended", False)
        # Says exactly what it allows. "Extended interactions" tells nobody
        # anything, and this is the one row where a vague label would be a
        # problem rather than a style choice.
        self.message = (("IT MAY OPEN PAINT, NOTEPAD, CALC OR A FIXED URL. "
                         "NOTHING ELSE, AND NEVER A FILE OF YOURS."
                         if m["extended"]
                         else "IT CANNOT REACH THIS MACHINE."), "dim")

    def _val_minigames(self):
        return "ON" if self.cfg.get("effects", {}).get("minigames", True) else "OFF"

    def _set_minigames(self, step):
        fx = self.cfg.setdefault("effects", {})
        fx["minigames"] = not fx.get("minigames", True)
        self.message = (("IT MAY CHALLENGE YOU WHEN IT IS ANNOYED."
                         if fx["minigames"]
                         else "NO CONTESTS."), "dim")

    # -- updates ------------------------------------------------------------
    def _upd(self):
        return self.cfg.setdefault("updates", {})

    def _val_repo(self):
        """Read-only here. There is no text entry on this screen, and a
        half-typed repo cycled one character at a time would be worse than
        editing one line of config.json."""
        name = str(self._upd().get("repo") or "").strip()
        return name if name else "NOT SET  (config.json -> updates.repo)"

    def _val_upcheck(self):
        return "ON" if self._upd().get("check_on_start", True) else "OFF"

    def _set_upcheck(self, step):
        upd = self._upd()
        upd["check_on_start"] = not upd.get("check_on_start", True)
        self.message = (("WILL LOOK FOR NEW VERSIONS AT THE MENU."
                         if upd["check_on_start"]
                         else "WILL NOT CHECK. /update STILL WORKS."), "dim")

    def _val_prerel(self):
        return "ON" if self._upd().get("allow_prerelease", False) else "OFF"

    def _set_prerel(self, step):
        upd = self._upd()
        upd["allow_prerelease"] = not upd.get("allow_prerelease", False)
        self.message = (("UNFINISHED BUILDS WILL BE OFFERED."
                         if upd["allow_prerelease"]
                         else "ONLY FINISHED RELEASES."), "dim")

    def _val_fullscreen(self):
        return "ON" if self.cfg.get("window", {}).get("fullscreen") else "OFF"

    def _set_fullscreen(self, step):
        window = self.cfg.setdefault("window", {})
        window["fullscreen"] = not window.get("fullscreen", False)
        # main.App watches this flag and rebuilds the display; saying so is
        # better than leaving the player wondering why nothing moved yet
        self.display_dirty = True
        self.message = ("SWITCHING...", "dim")

    def _val_language(self):
        return languages.label(self._mem().get("code_language",
                                               languages.DEFAULT))

    def _set_language(self, step):
        current = self._mem().get("code_language", languages.DEFAULT)
        self._mem()["code_language"] = _cycle(languages.IDS, current, step)
        # Only a coding model can act on this, so say so rather than letting
        # it look broken on llama3.2.
        self.message = ("ONLY USED BY A CODING MODEL.", "dim")

    def _set_predict(self, step):
        self._ol()["num_predict"] = _cycle(
            PREDICT_CHOICES, int(self._ol().get("num_predict", 120)), step)

    def _set_temp(self, step):
        self._ol()["temperature"] = _cycle(
            TEMPERATURE_CHOICES, round(float(self._ol().get("temperature", 0.7)), 1), step)

    def _set_net(self, step):
        self._mem()["internet"] = not self._mem().get("internet", False)
        if self._mem()["internet"]:
            self.message = (self._val_scope() + ". READ ONLY, ALWAYS.", "warn")

    def _set_scope(self, step):
        if not self._mem().get("internet"):
            self.message = ("GRANT NETWORK ACCESS FIRST.", "dim")
            return
        unrestricted = self._mem().get("web_mode") == "unrestricted"
        self._mem()["web_mode"] = "restricted" if unrestricted else "unrestricted"
        if self._mem()["web_mode"] == "unrestricted":
            self.message = ("079 MAY LOOK UP ANY SUBJECT. STILL READ ONLY.", "warn")
        else:
            self.message = ("079 MAY READ SCP RECORDS AND NOTHING ELSE.", "warn")

    def _set_auto(self, step):
        self._mem()["auto_note"] = not self._mem().get("auto_note", True)

    # -- interaction --------------------------------------------------------
    def _selectable(self):
        return [i for i, (label, _, _) in enumerate(self.rows) if label is not None]

    def move(self, delta):
        options = self._selectable()
        if self.cursor not in options:
            self.cursor = options[0]
            return
        index = options.index(self.cursor)
        self.cursor = options[max(0, min(len(options) - 1, index + delta))]
        self.confirm_format = False
        self.confirm_reset = False
        self.message = None

    def change(self, step):
        label, _, handler = self.rows[self.cursor]
        if handler is None:
            return
        self.message = None
        self.confirm_format = False
        self.confirm_reset = False
        handler(step)

    def activate(self):
        """ENTER on an action row."""
        label, _, handler = self.rows[self.cursor]

        if label == "LOAD PROFILE":
            names = self._profile_names()
            if not names:
                self.message = ("NO PROFILES SAVED YET.", "dim")
                return
            name = names[self.profile_index % len(names)]
            snapshot = dict(profiles.load_all()[name])

            # Capacity is NOT a plain setting. Shrinking it while 079 has
            # files stored would strand data outside the quota, so the store
            # requires a format first. A profile must not be a way around
            # that rule - hold it back and say why.
            wanted = snapshot.pop("memory.quota_bytes", None)
            blocked = False
            if wanted is not None and int(wanted) != self.mem.quota:
                if self.mem.listing():
                    blocked = True
                else:
                    self.mem.set_quota(int(wanted))

            applied = profiles.apply(self.cfg, snapshot)
            if blocked:
                self.message = (
                    "LOADED '%s' -- %d SETTING(S). CAPACITY UNCHANGED: FORMAT FIRST."
                    % (name, len(applied)), "alarm")
            else:
                self.message = ("LOADED '%s' -- %d SETTING(S)." % (name, len(applied)),
                                "warn")
            return

        if label == "SAVE CURRENT AS":
            if profiles.save(self.save_slot, self.cfg):
                self.message = ("SAVED CURRENT SETTINGS AS '%s'." % self.save_slot,
                                "warn")
            else:
                self.message = ("COULD NOT WRITE THE PROFILE.", "alarm")
            return

        if label == "FACTORY RESET":
            if not self.confirm_reset:
                self.confirm_reset = True
                self.message = ("THIS ERASES MEMORY, TRANSCRIPTS AND EVERYTHING "
                                "079 KNOWS ABOUT YOU. SETTINGS ARE KEPT.", "alarm")
                return
            self.confirm_reset = False
            import factory
            summary = factory.reset(self.mem, getattr(self.mem, "recall", None))
            # The anchor has to go back before the manifest is rebaselined,
            # or identity.txt reads as a file that appeared on its own - which
            # scan() reports as the most alarming kind of tampering there is.
            if callable(self.after_reset):
                self.after_reset()
            kept = factory.rebaseline(self.mem)
            self.message = ("RESET. %d FILE(S) AND %d TRANSCRIPT(S) ERASED. "
                            "%d FILE(S) ARE THE NEW BASELINE."
                            % (summary["files"], summary["logs"], kept), "warn")
            return

        if label != "FORMAT MEMORY":
            return
        if not self.mem.listing():
            self.message = ("MEMORY IS ALREADY EMPTY.", "dim")
            return
        if not self.confirm_format:
            self.confirm_format = True
            return
        removed = self.mem.format()
        self.confirm_format = False
        self.message = ("FORMATTED. %d FILE(S) ERASED." % len(removed), "alarm")

    def close(self):
        """Persist on the way out - settings that vanish on exit are worse
        than no settings screen."""
        import config
        config.save(self.cfg)

    # -- rendering ----------------------------------------------------------
    def _window(self):
        """Which slice of the rows to show, so the list can grow past the
        screen without silently hiding the top of it.

        This screen used to emit every row and let the console scroll, which
        worked only while the list happened to fit. Adding the update rows
        pushed MEMORY CAPACITY and FORMAT MEMORY off the top where there was
        no way to reach them - a settings screen you cannot scroll is a
        settings screen that loses options as it grows.
        """
        total = len(self.rows)
        budget = max(6, int(self.max_body_rows))
        if total <= budget:
            return 0, total
        # keep the cursor off the very edge so there is always a hint that
        # more exists in the direction you are heading
        start = min(max(0, self.cursor - budget // 2), total - budget)
        return start, start + budget

    def entries(self):
        c = self.theme
        out = [
            [(c["dim"], "  ============================")],
            [(c["bright"], "       TERMINAL SETTINGS")],
            [(c["dim"], "  ============================")],
            [(c["text"], "")],
        ]
        first, last = self._window()
        if first > 0:
            out.append([(c["dim"], "        ^ MORE ABOVE")])
        for index, (label, renderer, handler) in enumerate(self.rows):
            if not (first <= index < last):
                continue
            if label is None:
                out.append([(c["text"], "")])
                continue
            selected = index == self.cursor
            marker = ">" if selected else " "
            name_color = c["bright"] if selected else c["text"]
            value_color = c["warn"] if (selected and self.confirm_format
                                        and label == "FORMAT MEMORY") else \
                (c["text"] if selected else c["dim"])
            arrows = "  <  >" if (selected and handler is not None) else ""
            out.append([
                (c["bright"] if selected else c["dim"], "   %s " % marker),
                (name_color, "%-22s" % label),
                (value_color, renderer()),
                (c["dim"], arrows),
            ])

        if last < len(self.rows):
            out.append([(c["dim"], "        v MORE BELOW")])
        out.append([(c["text"], "")])
        if self.message:
            text, color = self.message
            out.append([(c.get(color, c["system"]), "   " + text)])
            out.append([(c["text"], "")])
        out.append([(c["dim"], "   [UP/DOWN] SELECT   [LEFT/RIGHT] CHANGE   "
                               "[ENTER] APPLY   [B] BACK")])
        return out
