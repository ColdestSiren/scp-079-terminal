"""Optional sound: CRT hum, key clicks, relay clicks, static, warning beep.

Every sound is generated as raw PCM at startup rather than shipped as a
file, so there are no assets to lose and no extra dependency (numpy is not
needed - pygame.mixer.Sound takes a plain bytes buffer).

Audio is entirely best-effort: if the mixer will not start, or a machine has
no output device, the terminal runs silently instead of failing.
"""

import array
import math
import random

import pygame

RATE = 22050
_MAX = 32767

# Filename fragments that mark a sound as belonging to the GAME's own effects
# rather than to 079. Anything matching is loaded but kept out of 079's reach:
# it found the explosion mp3 in its sound list and started playing it in
# conversation, which fires the bang without the gif, the lockout or the joke.
# Substrings rather than exact names, because these files are dropped in by
# hand and "tenor_explosiom" is already a typo nobody should have to reproduce.
RESERVED_MARKERS = ("explos", "explosiom", "nuke", "fire", "are you sure")


def _is_reserved(stem):
    low = (stem or "").strip().lower()
    return any(marker in low for marker in RESERVED_MARKERS)


def _envelope(i, n, attack=0.02, release=0.35):
    """Simple attack/release shaping so nothing clicks at the edges."""
    a = max(1, int(n * attack))
    r = max(1, int(n * release))
    if i < a:
        return i / a
    if i > n - r:
        return max(0.0, (n - i) / r)
    return 1.0


def _tone(freq, ms, volume=0.5, wave="sine", attack=0.02, release=0.35):
    n = int(RATE * ms / 1000.0)
    out = array.array("h", bytes(2 * n))
    for i in range(n):
        phase = 2.0 * math.pi * freq * (i / RATE)
        if wave == "square":
            value = 1.0 if math.sin(phase) >= 0 else -1.0
        else:
            value = math.sin(phase)
        out[i] = int(_MAX * volume * value * _envelope(i, n, attack, release))
    return out


def _noise(ms, volume=0.5, attack=0.01, release=0.6):
    n = int(RATE * ms / 1000.0)
    out = array.array("h", bytes(2 * n))
    for i in range(n):
        out[i] = int(_MAX * volume * random.uniform(-1.0, 1.0) * _envelope(i, n, attack, release))
    return out


def _mix(*tracks):
    n = max(len(t) for t in tracks)
    out = array.array("h", bytes(2 * n))
    for track in tracks:
        for i, sample in enumerate(track):
            merged = out[i] + sample
            out[i] = max(-_MAX, min(_MAX, merged))
    return out


def _hum_loop(seconds=1.0, volume=0.5):
    """A mains-hum drone. The length is a whole number of 60Hz cycles so the
    loop point is seamless."""
    n = int(RATE * seconds)
    out = array.array("h", bytes(2 * n))
    for i in range(n):
        t = i / RATE
        value = (0.65 * math.sin(2.0 * math.pi * 60.0 * t)
                 + 0.25 * math.sin(2.0 * math.pi * 120.0 * t)
                 + 0.10 * random.uniform(-1.0, 1.0))
        out[i] = int(_MAX * volume * value)
    return out


class Audio:
    def __init__(self, cfg, personality=None):
        sound_cfg = cfg.get("sound", {})
        profile = getattr(personality, "audio", {}) or {}
        self.enabled = bool(sound_cfg.get("enabled", True))
        self.volume = float(sound_cfg.get("volume", 0.35))
        self.wants = {
            key: bool(sound_cfg.get(key, True)) and bool(profile.get(key, True))
            for key in ("hum", "keys", "relay", "static", "beep")
        }
        self.sounds = {}
        self._hum_channel = None
        if self.enabled:
            self._build()

    def _build(self):
        try:
            pygame.mixer.init(frequency=RATE, size=-16, channels=1, buffer=512)
        except Exception:
            self.enabled = False
            return
        recipes = {
            "key": lambda: _noise(11, 0.30, attack=0.05, release=0.85),
            "relay": lambda: _mix(_noise(18, 0.45, attack=0.02, release=0.9),
                                  _tone(1900, 26, 0.20, "square", release=0.8)),
            "static": lambda: _noise(240, 0.55, attack=0.02, release=0.5),
            "beep": lambda: _tone(880, 150, 0.35, "square"),
            "hum": lambda: _hum_loop(1.0, 0.30),
            # For the face flicker. Shaped to match what is on screen: a hard
            # front edge with no attack ramp (the image appears between two
            # frames, so a fade-in would sound wrong against it) over a short
            # noise burst, with a low thump underneath for the deflection kick
            # a real tube makes. Longer than the image itself on purpose -
            # the sound is what tells you something happened after the picture
            # has already gone.
            "crackle": lambda: _mix(
                _noise(90, 0.60, attack=0.0, release=0.75),
                _tone(70, 130, 0.35, "sine", attack=0.0, release=0.85),
                _tone(2600, 40, 0.12, "square", attack=0.0, release=0.9)),
        }
        for name, make in recipes.items():
            try:
                self.sounds[name] = pygame.mixer.Sound(buffer=make().tobytes())
            except Exception:
                continue
        self._load_custom()

    def _load_custom(self):
        """Load anything the player dropped in the sounds folder.

        These are the only sounds 079 can trigger itself. Keeping them to one
        folder means a >>PLAY command can never reach an arbitrary file on the
        machine - the name is looked up in this dict, never used as a path.
        """
        import os

        import config
        self.custom = {}
        self.reserved = {}
        folder = config.SOUND_DIR
        if not os.path.isdir(folder):
            return
        for entry in sorted(os.listdir(folder)):
            stem, ext = os.path.splitext(entry)
            if ext.lower() not in (".wav", ".ogg", ".mp3"):
                continue
            try:
                sound = pygame.mixer.Sound(os.path.join(folder, entry))
            except Exception:
                continue
            key = stem.strip().lower().replace(" ", "_")[:24]
            if not key:
                continue
            # Assets belonging to the game's own effects live in the same
            # folder and must NOT become part of 079's palette. It found the
            # explosion sound sitting in its sound list and started firing it
            # in conversation - the bang with no gif, no lockout and no joke,
            # just a noise. They go somewhere it cannot name.
            if _is_reserved(stem):
                self.reserved[key] = sound
            else:
                self.custom[key] = sound
                self.sounds["custom:" + key] = sound

    def custom_names(self):
        """Only what 079 may trigger. Reserved effects are deliberately absent
        from this list AND from the dict >>PLAY resolves against, so guessing
        the name does not work either."""
        return sorted(getattr(self, "custom", {}).keys())

    def play_effect(self, marker, scale=1.0):
        """Play a reserved effect the GAME owns - never reachable by 079.

        Matched on a substring so the easter egg does not depend on the exact
        filename, which has a double space in it and is easy to retype wrong.
        """
        for key, sound in sorted(getattr(self, "reserved", {}).items()):
            if marker in key:
                if not self.enabled:
                    return False
                try:
                    sound.set_volume(max(0.0, min(1.0, self.volume * scale * 2.0)))
                    sound.play()
                    return True
                except Exception:
                    return False
        return False

    def play_custom(self, name, scale=1.0):
        """Play one of the player-supplied sounds by name. Returns True if it
        existed - 079 is told when a name is not real rather than silently
        doing nothing."""
        key = (name or "").strip().lower().replace(" ", "_")
        sound = getattr(self, "custom", {}).get(key)
        if sound is None or not self.enabled:
            return False
        try:
            sound.set_volume(max(0.0, min(1.0, self.volume * scale * 2.0)))
            sound.play()
            return True
        except Exception:
            return False

    def play(self, name, scale=1.0):
        if not self.enabled or not self.wants.get(_family(name), True):
            return
        sound = self.sounds.get(name)
        if sound is None:
            return
        try:
            sound.set_volume(max(0.0, min(1.0, self.volume * scale)))
            sound.play()
        except Exception:
            pass

    def start_hum(self):
        if not self.enabled or not self.wants.get("hum", True):
            return
        sound = self.sounds.get("hum")
        if sound is None or self._hum_channel is not None:
            return
        try:
            sound.set_volume(max(0.0, min(1.0, self.volume * 0.22)))
            self._hum_channel = sound.play(loops=-1)
        except Exception:
            self._hum_channel = None

    def stop_hum(self):
        if self._hum_channel is not None:
            try:
                self._hum_channel.stop()
            except Exception:
                pass
            self._hum_channel = None

    def shutdown(self):
        self.stop_hum()
        if self.enabled:
            try:
                pygame.mixer.quit()
            except Exception:
                pass


def _family(name):
    return {"key": "keys"}.get(name, name)
