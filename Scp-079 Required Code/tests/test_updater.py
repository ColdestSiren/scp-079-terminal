"""The updater.

Weighted heavily towards what it REFUSES, because this is the one module that
writes files outside its own sandbox. A test proving it can install is worth
much less than a test proving it cannot be talked into writing over the memory
folder or somewhere outside the project entirely.

Nothing here touches the network. The install path is driven with zips built
on the spot, which is also the only sane way to test a malicious archive.
"""

import io
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP_DIR)

SANDBOX = tempfile.mkdtemp(prefix="079upd_")

import config
config.DATA_DIR = SANDBOX
config.LOG_DIR = os.path.join(SANDBOX, "logs")
os.makedirs(config.LOG_DIR, exist_ok=True)

import updater
import version

PASS = FAIL = 0


def check(label, condition):
    global PASS, FAIL
    if condition:
        PASS += 1
    else:
        FAIL += 1
        print("  FAIL: %s" % label)


def section(title):
    print()
    print("== %s ==" % title)


def make_zip(entries, root=""):
    """entries: {name: bytes|str}. Returns a path to a real zip file."""
    handle, path = tempfile.mkstemp(prefix="079test_", suffix=".zip", dir=SANDBOX)
    os.close(handle)
    with zipfile.ZipFile(path, "w") as archive:
        for name, body in entries.items():
            data = body.encode("utf-8") if isinstance(body, str) else body
            archive.writestr(root + name, data)
    return path


def fresh_root():
    root = tempfile.mkdtemp(prefix="079root_", dir=SANDBOX)
    return root


# ---------------------------------------------------------------------------
section("version comparison")
# ---------------------------------------------------------------------------
check("a higher patch is newer", version.is_newer("1.0.1", "1.0.0"))
check("a lower patch is not", not version.is_newer("1.0.0", "1.0.1"))
check("the same version is not newer", not version.is_newer("1.0.0", "1.0.0"))
check("a leading v is accepted", version.is_newer("v2.0.0", "1.9.9"))
# The whole reason not to compare tags as strings.
check("1.10.0 beats 1.9.0 numerically", version.is_newer("1.10.0", "1.9.0"))
check("1.9.0 does not beat 1.10.0", not version.is_newer("1.9.0", "1.10.0"))
check("short forms pad out", version.is_newer("1.1", "1.0.9"))
check("a release beats its own pre-release",
      version.is_newer("1.2.0", "1.2.0-beta"))
check("a pre-release does not beat the release",
      not version.is_newer("1.2.0-beta", "1.2.0"))
# Direction matters: unreadable must mean "no update", never "update anyway".
check("garbage is never newer", not version.is_newer("banana", "1.0.0"))
check("empty is never newer", not version.is_newer("", "1.0.0"))
check("None is never newer", not version.is_newer(None, "1.0.0"))
check("describe is readable", version.describe("v1.2.3") == "V1.2.3")

# ---------------------------------------------------------------------------
section("the repo is not guessed")
# ---------------------------------------------------------------------------
check("no config means no source", updater.repo({}) is None)
check("empty string means no source", updater.repo({"updates": {"repo": ""}}) is None)
check("owner/name is accepted",
      updater.repo({"updates": {"repo": "someone/thing"}}) == "someone/thing")
check("a full url is trimmed to owner/name",
      updater.repo({"updates": {"repo": "https://github.com/someone/thing"}})
      == "someone/thing")
check(".git is stripped",
      updater.repo({"updates": {"repo": "someone/thing.git"}}) == "someone/thing")
check("a bare word is rejected",
      updater.repo({"updates": {"repo": "thing"}}) is None)
check("a path with extra segments is rejected",
      updater.repo({"updates": {"repo": "a/b/c"}}) is None)
check("an injected space is rejected",
      updater.repo({"updates": {"repo": "a b/c"}}) is None)
# The shipped default points at this project's own home. It was empty once,
# which meant the update feature shipped dead: nobody finds the setting that
# turns it on, so a fix pushed to the repo would never reach anyone running
# the game. Tie it to the actual git remote so the two cannot drift apart.
_shipped = config.DEFAULTS["updates"]["repo"]
check("shipped default names a repo", updater.repo(config.DEFAULTS) is not None)
check("shipped default is well formed", updater.repo(config.DEFAULTS) == _shipped)

_remote = ""
try:
    _remote = subprocess.check_output(
        ["git", "remote", "get-url", "origin"],
        cwd=APP_DIR, stderr=subprocess.DEVNULL,
        text=True, timeout=20).strip()
except Exception:
    _remote = ""
if _remote:
    _slug = _remote.replace("https://github.com/", "").strip("/")
    if _slug.endswith(".git"):
        _slug = _slug[:-4]
    check("shipped default matches the git remote (%s)" % _slug,
          _shipped.lower() == _slug.lower())
else:
    # No git available, or not a clone. Skipping is right here: this is a
    # consistency check between two things, and with one of them missing
    # there is nothing to compare. Say so rather than passing quietly.
    check("SKIPPED remote comparison - no git remote found", True)

# Clearing the repo must still fully disable the feature, so opting out is
# always possible.
check("clearing the repo disables updates",
      updater.repo(config._deep_merge(config.DEFAULTS,
                                      {"updates": {"repo": ""}})) is None)
check("check_on_start off disables updates",
      not updater.enabled(config._deep_merge(
          config.DEFAULTS, {"updates": {"check_on_start": False}})))

check("check_on_start defaults on",
      config.DEFAULTS["updates"]["check_on_start"] is True)
check("prereleases default off",
      config.DEFAULTS["updates"]["allow_prerelease"] is False)

# ---------------------------------------------------------------------------
section("hosts outside github are refused")
# ---------------------------------------------------------------------------
for bad in ("https://evil.example.com/x.zip",
            "http://github.com.evil.net/x.zip",
            "https://raw.githubusercontent.com/a/b/x.zip"):
    try:
        updater._open(bad)
        check("refused %s" % bad, False)
    except updater.UpdateError as exc:
        check("refused %s" % bad, "NOT A GITHUB HOST" in str(exc))
    except Exception:
        check("refused %s before connecting: %s" % (bad, ""), False)

# ---------------------------------------------------------------------------
section("the download Accept header")
# ---------------------------------------------------------------------------
# A REAL BUG THAT EVERY UNIT TEST MISSED. Downloads asked for
# "application/octet-stream", and GitHub answers the zipball endpoint with
# 415 Unsupported Media Type for that. zipball_url is what check() falls back
# to whenever a release has no hand-uploaded .zip - the ordinary case, since
# GitHub generates a source archive for every tag. So the common path was
# broken and the tests all passed, because they build their own zips and
# never touch GitHub.
_upd_src = open(os.path.join(APP_DIR, "updater.py"), encoding="utf-8").read()
_dl = _upd_src.split("def download_job")[1].split(chr(10) + "def ")[0]
# Checked as USAGE, not as a mention: the comment explaining the fix
# naturally contains the header that caused it, so a plain substring search
# fails on the documentation of its own bug. Same trap as the fullscreen one.
_accepts = [ln for ln in _dl.splitlines() if "accept=" in ln]
check("the download passes an accept header", bool(_accepts))
check("none of them ask for octet-stream",
      not any("octet-stream" in ln for ln in _accepts))
check("it accepts anything instead", 'accept="*/*"' in _dl)
check("the reason is written down next to it",
      "415" in _dl)

# ---------------------------------------------------------------------------
section("a normal install")
# ---------------------------------------------------------------------------
root = fresh_root()
os.makedirs(os.path.join(root, "Scp-079 Required Code"))
with open(os.path.join(root, "Scp-079 Required Code", "main.py"), "w") as fh:
    fh.write("old code")

path = make_zip({
    "RUN.bat": "new launcher",
    "Scp-079 Required Code/main.py": "new code",
    "Scp-079 Required Code/newmodule.py": "brand new",
})
result = updater.install(path, root=root, keep_backup=False)
check("three files written", result["written"] == 3)
check("an existing file was replaced",
      open(os.path.join(root, "Scp-079 Required Code", "main.py")).read() == "new code")
check("a new file was created",
      os.path.isfile(os.path.join(root, "Scp-079 Required Code", "newmodule.py")))
check("a root file was created", os.path.isfile(os.path.join(root, "RUN.bat")))

# ---------------------------------------------------------------------------
section("the github source-zip wrapper folder is stripped")
# ---------------------------------------------------------------------------
root = fresh_root()
path = make_zip({"Scp-079 Required Code/main.py": "x", "RUN.bat": "y"},
                root="Scp-079-remake-1.2.0/")
updater.install(path, root=root, keep_backup=False)
check("wrapper folder stripped",
      os.path.isfile(os.path.join(root, "Scp-079 Required Code", "main.py")))
check("no wrapper left behind",
      not os.path.isdir(os.path.join(root, "Scp-079-remake-1.2.0")))

# A zip with two top-level entries has no wrapper and must not lose one.
root = fresh_root()
path = make_zip({"a/one.py": "1", "b/two.py": "2"})
updater.install(path, root=root, keep_backup=False)
check("two real top folders both survive",
      os.path.isfile(os.path.join(root, "a", "one.py"))
      and os.path.isfile(os.path.join(root, "b", "two.py")))

# ---------------------------------------------------------------------------
section("ZIP SLIP -- writing outside the folder is refused")
# ---------------------------------------------------------------------------
for evil in ("../escaped.py",
             "../../escaped.py",
             "Scp-079 Required Code/../../escaped.py",
             "a/b/../../../escaped.py"):
    root = fresh_root()
    outside = os.path.join(os.path.dirname(root), "escaped.py")
    if os.path.exists(outside):
        os.remove(outside)
    path = make_zip({evil: "pwned"})
    try:
        updater.install(path, root=root, keep_backup=False)
        check("refused traversal %s" % evil, False)
    except updater.UpdateError as exc:
        check("refused traversal %s" % evil, "OUTSIDE" in str(exc))
    check("nothing escaped for %s" % evil, not os.path.exists(outside))

# An absolute path is the blunter version of the same attack.
root = fresh_root()
path = make_zip({"C:/Windows/Temp/pwned.py": "no"})
try:
    updater.install(path, root=root, keep_backup=False)
    check("refused an absolute windows path", False)
except updater.UpdateError as exc:
    check("refused an absolute windows path",
          "ABSOLUTE" in str(exc) or "OUTSIDE" in str(exc))

# ---------------------------------------------------------------------------
section("your data is never overwritten")
# ---------------------------------------------------------------------------
root = fresh_root()
for relative, body in (
        (os.path.join("memory", "core", "0x4F", "humans.txt"), "MINE"),
        (os.path.join("logs", "terminal_state.json"), '{"hostility": 3}'),
        (os.path.join("shared folder", "notes.txt"), "MINE TOO"),
        ("Suggestions.txt", "MY NOTES"),
        (os.path.join("Scp-079 Required Code", "config.json"), '{"model": "mine"}')):
    full = os.path.join(root, relative)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as fh:
        fh.write(body)

# A release that tries to ship over every one of them.
path = make_zip({
    "memory/core/0x4F/humans.txt": "REPLACED",
    "logs/terminal_state.json": '{"hostility": 0}',
    "shared folder/notes.txt": "REPLACED",
    "Suggestions.txt": "REPLACED",
    "Scp-079 Required Code/config.json": '{"model": "theirs"}',
    "Scp-079 Required Code/main.py": "legitimate new code",
})
result = updater.install(path, root=root, keep_backup=False)
check("only the code file was written", result["written"] == 1)
check("079's memory survived",
      open(os.path.join(root, "memory", "core", "0x4F", "humans.txt")).read() == "MINE")
check("hostility and session count survived",
      "3" in open(os.path.join(root, "logs", "terminal_state.json")).read())
check("the shared folder survived",
      open(os.path.join(root, "shared folder", "notes.txt")).read() == "MINE TOO")
check("your notes survived",
      open(os.path.join(root, "Suggestions.txt")).read() == "MY NOTES")
check("your settings survived",
      "mine" in open(os.path.join(root, "Scp-079 Required Code", "config.json")).read())
check("the real update still landed",
      open(os.path.join(root, "Scp-079 Required Code", "main.py")).read()
      == "legitimate new code")

# ---------------------------------------------------------------------------
section("nothing is ever deleted")
# ---------------------------------------------------------------------------
root = fresh_root()
os.makedirs(os.path.join(root, "sounds"))
with open(os.path.join(root, "sounds", "my custom sound.mp3"), "w") as fh:
    fh.write("mine")
path = make_zip({"Scp-079 Required Code/main.py": "new"})
updater.install(path, root=root, keep_backup=False)
check("a file absent from the release is left alone",
      os.path.isfile(os.path.join(root, "sounds", "my custom sound.mp3")))

# ---------------------------------------------------------------------------
section("a bad archive changes nothing")
# ---------------------------------------------------------------------------
root = fresh_root()
os.makedirs(os.path.join(root, "Scp-079 Required Code"))
target = os.path.join(root, "Scp-079 Required Code", "main.py")
with open(target, "w") as fh:
    fh.write("original")

junk = os.path.join(SANDBOX, "notazip.zip")
with open(junk, "wb") as fh:
    fh.write(b"this is not a zip file at all")
try:
    updater.install(junk, root=root, keep_backup=False)
    check("a non-zip is refused", False)
except updater.UpdateError as exc:
    check("a non-zip is refused", "NOT A VALID ZIP" in str(exc))
check("the old file is untouched after a bad download",
      open(target).read() == "original")

# An archive that validates but contains nothing installable.
root2 = fresh_root()
path = make_zip({"memory/core/0x4F/x.txt": "only protected content"})
try:
    updater.install(path, root=root2, keep_backup=False)
    check("an all-protected archive is refused", False)
except updater.UpdateError as exc:
    check("an all-protected archive is refused", "NOTHING TO INSTALL" in str(exc))

# The traversal check runs over the WHOLE member list before any write, so a
# poisoned entry after a legitimate one still installs nothing.
root3 = fresh_root()
path = make_zip({"Scp-079 Required Code/main.py": "good", "../escaped.py": "bad"})
try:
    updater.install(path, root=root3, keep_backup=False)
    check("a mixed archive is refused", False)
except updater.UpdateError:
    check("a mixed archive is refused", True)
check("the legitimate file was NOT written either",
      not os.path.isfile(os.path.join(root3, "Scp-079 Required Code", "main.py")))

# ---------------------------------------------------------------------------
section("backups")
# ---------------------------------------------------------------------------
root = fresh_root()
os.makedirs(os.path.join(root, "Scp-079 Required Code"))
with open(os.path.join(root, "Scp-079 Required Code", "main.py"), "w") as fh:
    fh.write("the version that worked")
_saved_data = config.DATA_DIR
config.DATA_DIR = root
path = make_zip({"Scp-079 Required Code/main.py": "the new one"})
result = updater.install(path, root=root, keep_backup=True)
check("a backup was made", result["backup"] and os.path.isdir(result["backup"]))
if result["backup"]:
    kept = os.path.join(result["backup"], "Scp-079 Required Code", "main.py")
    check("the backup holds the OLD contents",
          os.path.isfile(kept) and open(kept).read() == "the version that worked")
config.DATA_DIR = _saved_data

# ---------------------------------------------------------------------------
section("declining is per-version, not forever")
# ---------------------------------------------------------------------------
updater.save_state({})
check("nothing is declined to start with", not updater.declined("v1.1.0"))
updater.decline("v1.1.0")
check("the declined version is remembered", updater.declined("v1.1.0"))
check("a DIFFERENT version still asks", not updater.declined("v1.2.0"))
check("an empty tag is never 'declined'", not updater.declined(""))

# ---------------------------------------------------------------------------
section("the check interval")
# ---------------------------------------------------------------------------
updater.save_state({})
check("a first run is due", updater.due_for_check())
updater._stamp_check()
check("it does not check again immediately", not updater.due_for_check())
updater.save_state({"last_check": "not a number"})
check("a corrupt stamp falls back to checking", updater.due_for_check())

# ---------------------------------------------------------------------------
section("079 cannot reach any of this")
# ---------------------------------------------------------------------------
# The point of the whole design: updating is the operator's decision. If a
# verb for it ever appears in the command grammar, this fails.
import tools
source = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "tools.py"), encoding="utf-8").read()
check("tools.py does not import the updater", "import updater" not in source)
for verb in tools.VERBS:
    check("no update verb in the grammar (%s)" % verb,
          "UPDATE" not in verb.upper() and "INSTALL" not in verb.upper())

# And it must not be reachable through the background channel either.
import background
bg_source = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "background.py"), encoding="utf-8").read()
check("the background channel does not import the updater",
      "import updater" not in bg_source)

# ---------------------------------------------------------------------------
section("the updater never executes anything")
# ---------------------------------------------------------------------------
# The single most important property here. If this module ever grows a way to
# run what it downloaded, that is a different program with different risks.
upd_source = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "updater.py"), encoding="utf-8").read()
for forbidden in ("subprocess", "os.system", "os.startfile", "os.exec",
                  "eval(", "exec(", "__import__("):
    check("updater.py contains no %s" % forbidden, forbidden not in upd_source)

# ---------------------------------------------------------------------------
section("a 404 is diagnosed, not guessed at")
# ---------------------------------------------------------------------------
# GitHub answers 404 for "no releases yet", "no such repo" and "private repo"
# alike. Reporting a typo'd repo name as "no releases published yet" tells
# someone to wait for something that can never arrive.
_real_open = updater._open


def fake_open(pattern_404):
    """Every url containing pattern_404 raises NotFound; others succeed."""
    class Fake:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, *a): return b'{"tag_name": "v0.0.1", "assets": []}'
        headers = {}

    def opener(url, accept=None):
        if pattern_404 in url:
            raise updater.NotFound("NOT FOUND")
        return Fake()
    return opener


cfg404 = {"updates": {"repo": "someone/thing"}}
try:
    # releases/latest 404s but the repo itself resolves -> genuinely no release
    updater._open = fake_open("/releases/")
    try:
        updater.check(cfg404)
        check("no-release case reported", False)
    except updater.UpdateError as exc:
        check("a real repo with no release says so",
              "NO RELEASES PUBLISHED YET" in str(exc))

    # the repo itself 404s -> the address is wrong, not the timing
    updater._open = fake_open("/repos/")
    try:
        updater.check(cfg404)
        check("missing-repo case reported", False)
    except updater.UpdateError as exc:
        text = str(exc)
        check("a missing repo says the repo is missing",
              "NO SUCH REPOSITORY" in text)
        check("it names the repo it tried", "someone/thing" in text)
        check("it points at the setting to fix", "updates.repo" in text)
        check("it mentions the private-repo case", "PRIVATE" in text)
        check("it does NOT tell you to wait for a release",
              "NO RELEASES PUBLISHED YET" not in text)
finally:
    updater._open = _real_open

check("NotFound is still an UpdateError so callers catch it",
      issubclass(updater.NotFound, updater.UpdateError))

# ---------------------------------------------------------------------------
section("the flow is actually reachable")
# ---------------------------------------------------------------------------
# Driven through real key events rather than by setting app.stage directly.
# Two lockout bugs survived a whole session because the screenshot stages set
# their own state and never went through the code path that reaches them.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
config.MEMORY_ROOT = os.path.join(SANDBOX, "memory")
config.MEMORY_DIR = os.path.join(config.MEMORY_ROOT, "core", "0x4F")
config.STATE_PATH = os.path.join(config.LOG_DIR, "terminal_state.json")
config.SHARED_DIR = os.path.join(SANDBOX, "shared folder")
config.CONFIG_PATH = os.path.join(SANDBOX, "config.json")
os.makedirs(config.MEMORY_DIR, exist_ok=True)

import pygame
import main as main_mod

pygame.init()
pygame.display.set_mode((960, 720))

cfg = config._deep_merge(config.DEFAULTS, {})
cfg["updates"]["repo"] = "example/thing"
app = main_mod.App(cfg)
app.audio.enabled = False


def press(key, unicode_=""):
    app.handle_key(pygame.event.Event(pygame.KEYDOWN, key=key, unicode=unicode_))


def screen_text():
    # plain rows are (colour, text) tuples; segmented rows are lists of them
    out = []
    for entry in app.console.entries():
        out.append(entry[1] if isinstance(entry, tuple)
                   else "".join(seg[1] for seg in entry))
    return "\n".join(out)


OFFER = {"tag": "v9.9.9", "version": "V9.9.9", "title": "Test",
         "notes": "Notes here.", "url": "https://github.com/example/thing/x.zip",
         "size": 1000, "prerelease": False, "published": "2026-08-12"}

updater.save_state({})
app.draw_menu()
check("no update banner when there is nothing to offer", "[U]" not in screen_text())

app.upd_info = dict(OFFER)
app.draw_menu()
check("the banner appears when a release is found", "[U]" in screen_text())
check("the banner names the version", "V9.9.9" in screen_text())

app.stage = "menu"
app.probe_result = {"exe": "stub", "running": True, "models": []}
press(pygame.K_u, "u")
check("U from the menu opens the offer", app.stage == "update")
check("the offer states the no-execution rule",
      "NOTHING DOWNLOADED IS RUN" in screen_text())
check("the offer states data is safe", "NOT TOUCHED" in screen_text())

# Saying no must not download anything, and must be remembered.
press(pygame.K_n, "n")
check("N leaves the update screen", app.stage != "update")
check("N started no download", app.upd_pull is None)
check("N is remembered for that version", updater.declined("v9.9.9"))
check("the offer is cleared", app.upd_info is None)

# A declined version must not come back on the next check...
app.upd_check = type("J", (), {"done": type("E", (), {"is_set": staticmethod(lambda: True)})(),
                               "result": dict(OFFER)})()
app.poll_update_check()
check("a declined version does not re-offer", app.upd_info is None)

# ...but a NEWER one still does.
later = dict(OFFER, tag="v9.9.10", version="V9.9.10")
app.upd_check = type("J", (), {"done": type("E", (), {"is_set": staticmethod(lambda: True)})(),
                               "result": later})()
app.poll_update_check()
check("a newer version still offers", app.upd_info is not None)

# The install screen offers only honest choices - the running process still
# holds the old code, so there is no "continue on the new version" option.
app.upd_info = dict(OFFER)
app.enter_update_offer("menu")
app.upd_done = {"written": 3, "backup": None}
app.show_update_result()
check("the result says a restart is needed", "start it again" in screen_text())
press(pygame.K_n, "n")
check("LATER returns without quitting", app.running and app.stage != "update")

# A failure must never leave the player stuck on the error screen.
app.show_update_result(error="NO ROUTE TO GITHUB")
check("failure says nothing changed", "NOTHING WAS CHANGED" in screen_text())
press(pygame.K_SPACE, " ")
check("any key leaves the failure screen", app.stage != "update")

# The screenshot stages must stay reachable too.
for stage in ("update", "updating", "updated", "updatefail"):
    check("shot stage '%s' is handled" % stage,
          stage in open(os.path.join(APP_DIR, "main.py"), encoding="utf-8").read())

pygame.quit()

shutil.rmtree(SANDBOX, ignore_errors=True)
print()
print("PASS %d   FAIL %d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
