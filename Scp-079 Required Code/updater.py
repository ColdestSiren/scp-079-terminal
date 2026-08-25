"""Update check and install, from GitHub releases or version tags.

WHAT THIS DOES: asks GitHub for the newest release of one specific repo,
compares its tag against version.VERSION, and - only if the player says yes -
downloads that release's zip and unpacks it over the install folder.

WHAT IT DELIBERATELY DOES NOT DO, because an updater is the most dangerous
code in any hobby project:

  * IT NEVER EXECUTES ANYTHING IT DOWNLOADS. No installer is run, no setup
    script is invoked, nothing is handed to the shell. The job ends when the
    files are on disk; the player restarts the game themselves. So a bad
    payload gains nothing at install time - it gains whatever the game
    already had, next time the game is launched, which is a trust the player
    already extended by running it at all. That boundary is the whole design.
  * IT NEVER DELETES. Files in the zip are written; everything else is left
    exactly where it is. This means a release cannot retire a stale module -
    accepted deliberately, because "the updater removed files" is how
    updaters eat people's work.
  * IT NEVER WRITES OVER YOUR DATA. PROTECTED below is refused even if the
    zip contains those paths, so a release cannot wipe 079's memory, your
    transcripts, your saves, your settings or your notes.
  * IT NEVER LEAVES THE ALLOWLIST. api.github.com and GitHub's own asset
    hosts, checked again after redirects.
  * 079 CANNOT REACH ANY OF IT. There is no verb for this in tools.py and
    this module is not imported there. Updating is the operator's decision
    and 079 is not consulted, which matters rather a lot given what it
    spends its time asking for.

The check prefers a GitHub Release because it carries notes and optional
assets. If there is no Release, it falls back to the newest semantic version
tag and GitHub's source zip for that tag. This matches the project's publish
workflow: ordinary main pushes are quiet; a version tag announces an update.

The check runs on a worker thread and any failure is silent by design: no
network, no GitHub, a rate limit, a repo that does not exist yet - none of
those are reasons to interrupt someone who only wanted to talk to 079.
"""

import json
import os
import re
import shutil
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

import config
# Job is the shared "run on a thread, poll once a frame" primitive. It lives
# in ollama.py because that is where it was first needed, not because this
# has anything to do with Ollama.
from ollama import Job
import version
import web

API_HOST = "api.github.com"
# A release asset download redirects off api.github.com onto GitHub's CDN, so
# those hosts have to be allowed too - but only those.
ALLOWED_HOSTS = (
    "api.github.com",
    "github.com",
    "codeload.github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
)

USER_AGENT = "SCP-079-Terminal/%s (updater)" % version.VERSION
TIMEOUT = 25
MAX_API_BYTES = 512_000
# A release should be a few megabytes. The cap is not a guess at the real
# size - it is a refusal to fill someone's disk if the URL is ever wrong.
MAX_DOWNLOAD_BYTES = 200 * 1024 * 1024
CHUNK = 64 * 1024

# How long to sit quiet between checks. GitHub allows 60 unauthenticated API
# calls an hour per IP; this is nowhere near it, and the point is really that
# nobody wants a network call every time they open a game.
CHECK_INTERVAL_SECONDS = 6 * 3600

STATE_NAME = "update_state.json"

# Never written by an install, whatever the zip claims. Relative to the
# project root, compared case-insensitively because Windows.
PROTECTED = (
    "memory",                               # 079's memory. The worst thing to lose.
    "logs",                                 # transcripts, hostility, session count
    "shared folder",                        # the player's own files
    "suggestions.txt",                      # the player's notes
    "scp-079 required code/config.json",    # settings, model choice, saves index
)


class UpdateError(Exception):
    """Anything that stopped an update. Shown as a line of text, never raised
    at the player as a traceback."""


class NotFound(UpdateError):
    """A 404, which on its own does not say what is missing.

    GitHub answers 404 for "no releases yet", "no such repo" and "the repo is
    private and you are not signed in" alike. Those need very different
    things from the player, so the meaning is decided by whoever made the
    call rather than assumed here.
    """


# ---------------------------------------------------------------------------
# where it looks
# ---------------------------------------------------------------------------
_REPO_RE = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")


def repo(cfg=None):
    """'owner/name', or None if nobody has configured one.

    No default on purpose. A guessed repo would mean the game quietly
    contacting a stranger's project and offering their files as an update,
    which is a supply chain with extra steps.
    """
    cfg = cfg if cfg is not None else {}
    raw = str((cfg.get("updates") or {}).get("repo") or "").strip()
    raw = raw.replace("https://github.com/", "").strip("/")
    if raw.endswith(".git"):
        raw = raw[:-4]
    return raw if _REPO_RE.match(raw) else None


def enabled(cfg):
    return bool((cfg.get("updates") or {}).get("check_on_start", True))


# ---------------------------------------------------------------------------
# remembering what happened last time
# ---------------------------------------------------------------------------
def _state_path():
    return os.path.join(config.LOG_DIR, STATE_NAME)


def load_state():
    try:
        with open(_state_path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_state(data):
    try:
        os.makedirs(config.LOG_DIR, exist_ok=True)
        with open(_state_path(), "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except Exception:
        pass        # bookkeeping. Never worth failing a launch over.


def decline(tag):
    """Remember a 'no' so the same version stops asking.

    This is the whole of what "no" means: it is not "never update", it is
    "not this one". The next release asks again, and /update ignores it
    entirely - saying no should not lock you out of changing your mind.
    """
    data = load_state()
    data["declined"] = str(tag)
    save_state(data)


def declined(tag):
    return bool(tag) and load_state().get("declined") == str(tag)


def due_for_check():
    last = load_state().get("last_check", 0)
    try:
        return (time.time() - float(last)) >= CHECK_INTERVAL_SECONDS
    except Exception:
        return True


def _stamp_check():
    data = load_state()
    data["last_check"] = time.time()
    save_state(data)


# ---------------------------------------------------------------------------
# transport
# ---------------------------------------------------------------------------
def _open(url, accept="application/vnd.github+json"):
    """GET, enforcing the allowlist on the FINAL url after redirects.

    Same rule as web.py and for the same reason: checking only the URL you
    asked for lets a redirect walk the request somewhere else entirely.
    """
    host = urllib.parse.urlparse(url).hostname or ""
    if host not in ALLOWED_HOSTS:
        raise UpdateError("BLOCKED: %s IS NOT A GITHUB HOST" % host.upper())
    request = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
    })
    try:
        response = urllib.request.urlopen(request, timeout=TIMEOUT,
                                          context=web.ssl_context())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise NotFound("NOT FOUND")
        if exc.code == 403:
            raise UpdateError("GITHUB RATE LIMIT REACHED -- TRY LATER")
        raise UpdateError("GITHUB RETURNED %s" % exc.code)
    except urllib.error.URLError as exc:
        raise UpdateError("NO ROUTE TO GITHUB (%s)" % str(exc.reason)[:50])
    landed = urllib.parse.urlparse(response.geturl()).hostname or ""
    if landed not in ALLOWED_HOSTS:
        response.close()
        raise UpdateError("BLOCKED: REDIRECTED TO %s" % landed.upper())
    return response


# ---------------------------------------------------------------------------
# the check
# ---------------------------------------------------------------------------
_NOTE_LIMIT = 700


def _tidy_notes(body):
    """Release notes are markdown written by a human. Flatten to plain lines."""
    text = str(body or "").replace("\r\n", "\n")
    text = re.sub(r"^#+\s*", "", text, flags=re.M)      # heading marks
    text = re.sub(r"[*_`]{1,3}", "", text)              # emphasis / code ticks
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > _NOTE_LIMIT:
        text = text[:_NOTE_LIMIT].rsplit(" ", 1)[0] + " [...]"
    return text


def _explain_missing(name):
    """Work out what a 404 on releases/latest actually meant.

    Costs one extra call, and only ever on the failure path. Worth it: a
    typo in updates.repo otherwise reads as "no releases published yet",
    which sounds like patience is the answer when the truth is that nothing
    will EVER arrive at that address.
    """
    try:
        with _open("https://api.github.com/repos/%s" % name):
            return "NO RELEASES PUBLISHED YET"
    except NotFound:
        return ("NO SUCH REPOSITORY: %s -- CHECK updates.repo IN config.json. "
                "A PRIVATE REPO LOOKS THE SAME FROM HERE." % name)
    except UpdateError:
        # Rate limited or offline on the second call; do not invent a
        # diagnosis from a failure to diagnose.
        return "NO RELEASES PUBLISHED YET"


def _read_json(url):
    with _open(url) as response:
        try:
            return json.loads(response.read(MAX_API_BYTES).decode("utf-8", "replace"))
        except Exception:
            raise UpdateError("GITHUB RESPONSE UNREADABLE")


def _latest_tag(name, cfg):
    """Newest semantic version tag, shaped like a release response."""
    url = "https://api.github.com/repos/%s/tags?per_page=100" % name
    try:
        rows = _read_json(url)
    except NotFound:
        raise UpdateError(_explain_missing(name))
    if not isinstance(rows, list):
        raise UpdateError("GITHUB TAG RESPONSE UNREADABLE")

    allow_pre = bool((cfg.get("updates") or {}).get("allow_prerelease", False))
    candidates = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        tag = str(row.get("name") or "").strip()
        parsed = version.parse(tag)
        if parsed is None or (parsed[1] and not allow_pre):
            continue
        # GitHub returns newest-by-commit, not necessarily highest version.
        key = parsed[0] + (0,) * max(0, 8 - len(parsed[0]))
        candidates.append((key, tag, row))
    if not candidates:
        raise UpdateError("NO VERSION TAGS PUBLISHED YET")
    _, tag, row = max(candidates, key=lambda item: item[0])
    return {
        "tag_name": tag,
        "name": "VERSION TAG %s" % tag,
        "body": "",
        "zipball_url": row.get("zipball_url"),
        "assets": [],
        "draft": False,
        "prerelease": bool(version.parse(tag)[1]),
        "published_at": "",
    }


def check(cfg):
    """Look for a newer release. Returns an info dict, or None if current.

    Raises UpdateError for anything the player asked to see (a manual
    /update). The background path swallows it.
    """
    name = repo(cfg)
    if not name:
        raise UpdateError("NO UPDATE SOURCE CONFIGURED")

    url = "https://api.github.com/repos/%s/releases/latest" % name
    release = None
    try:
        release = _read_json(url)
    except NotFound:
        pass

    # A Release and a tag are separate GitHub objects. The author may publish
    # a proper Release for v1.0.3, then use Publish.bat to push the v1.0.4 tag
    # before writing its notes. releases/latest still succeeds in that state,
    # but it points at the older build. Always compare the newest semantic tag
    # with the newest Release and use whichever version is actually newer.
    tagged = None
    try:
        tagged = _latest_tag(name, cfg)
    except UpdateError:
        if release is None:
            raise

    data = release or tagged
    if release is not None and tagged is not None:
        release_tag = str(release.get("tag_name") or "").strip()
        tagged_tag = str(tagged.get("tag_name") or "").strip()
        if version.is_newer(tagged_tag, release_tag):
            data = tagged
    _stamp_check()

    if data.get("draft"):
        return None
    if data.get("prerelease") and not (cfg.get("updates") or {}).get("allow_prerelease", False):
        return None
    tag = str(data.get("tag_name") or "").strip()
    if not tag:
        raise UpdateError("RELEASE HAS NO VERSION TAG")
    if not version.is_newer(tag):
        return None

    # Prefer a zip the author uploaded; fall back to the source archive
    # GitHub generates for every tag.
    asset_url, size = None, 0
    for asset in data.get("assets") or []:
        if str(asset.get("name") or "").lower().endswith(".zip"):
            asset_url = asset.get("browser_download_url")
            size = int(asset.get("size") or 0)
            break
    if not asset_url:
        asset_url = data.get("zipball_url")
    if not asset_url:
        raise UpdateError("RELEASE HAS NOTHING TO DOWNLOAD")

    return {
        "tag": tag,
        "version": version.describe(tag),
        "title": str(data.get("name") or "").strip(),
        "notes": _tidy_notes(data.get("body")),
        "url": asset_url,
        "size": size,
        "prerelease": bool(data.get("prerelease")),
        "published": str(data.get("published_at") or "")[:10],
    }


def check_job(cfg):
    """The background version. Never raises - a failed check is silent."""
    def run(job):
        try:
            return check(cfg)
        except UpdateError:
            return None
        except Exception:
            return None
    return Job().start(run)


# ---------------------------------------------------------------------------
# the download
# ---------------------------------------------------------------------------
def download_job(info):
    """Stream the release zip to a temp file, reporting progress."""
    def run(job):
        handle, path = tempfile.mkstemp(prefix="079update_", suffix=".zip")
        os.close(handle)
        got = 0
        try:
            # "*/*", NOT "application/octet-stream". GitHub answers the
            # zipball endpoint with 415 Unsupported Media Type for
            # octet-stream, and zipball_url is what check() falls back to
            # whenever a release has no manually uploaded .zip - which is the
            # ordinary case, since GitHub generates the source archive for
            # every tag. So the octet-stream header broke the COMMON path and
            # only worked for a release someone had hand-attached a zip to.
            # Found by downloading from the real repo; every unit test passed
            # against hand-built zips that never touched GitHub.
            with _open(info["url"], accept="*/*") as response:
                total = info.get("size") or 0
                try:
                    total = int(response.headers.get("Content-Length") or total)
                except Exception:
                    pass
                if total and total > MAX_DOWNLOAD_BYTES:
                    raise UpdateError("RELEASE IS LARGER THAN EXPECTED -- REFUSED")
                with open(path, "wb") as out:
                    while True:
                        if job.cancelled.is_set():
                            raise UpdateError("CANCELLED")
                        block = response.read(CHUNK)
                        if not block:
                            break
                        got += len(block)
                        if got > MAX_DOWNLOAD_BYTES:
                            raise UpdateError("DOWNLOAD EXCEEDED THE SIZE LIMIT")
                        out.write(block)
                        job.emit("progress", {"completed": got, "total": total})
        except Exception:
            try:
                os.remove(path)
            except OSError:
                pass
            raise
        return path
    return Job().start(run)


# ---------------------------------------------------------------------------
# the install
# ---------------------------------------------------------------------------
def _is_protected(relative):
    low = relative.replace("\\", "/").lower().lstrip("/")
    for guard in PROTECTED:
        if low == guard or low.startswith(guard + "/"):
            return True
    return False


def _reject_dangerous(name):
    """Raise if a RAW archive name is trying to leave the folder.

    THIS RUNS BEFORE ANY PREFIX STRIPPING, and the order is the whole point.
    An earlier version stripped the archive's wrapper folder first, which
    happily treated ".." and "C:" as wrapper names and REMOVED them - quietly
    turning "../escaped.py" into "escaped.py" and defusing the exact attack
    the next check existed to catch. Validate the string you were given, then
    transform it.
    """
    if not name:
        return
    if name.startswith("/") or name.startswith("\\"):
        raise UpdateError("ARCHIVE CONTAINS AN ABSOLUTE PATH -- REFUSED")
    head = name.split("/")[0]
    if ":" in head or os.path.isabs(name):
        raise UpdateError("ARCHIVE CONTAINS AN ABSOLUTE PATH -- REFUSED")
    if any(part == ".." for part in name.split("/")):
        raise UpdateError("ARCHIVE TRIES TO WRITE OUTSIDE THE FOLDER -- REFUSED")


def _safe_members(archive, root):
    """Every member, checked, with the archive's top folder stripped.

    THE CHECK THAT MATTERS IS CONTAINMENT. A zip entry is just a string, and
    "../../Windows/System32/x.dll" is a legal one - the classic zip-slip. So
    every name is screened raw, and then the real destination is resolved and
    compared against the real root as a backstop.

    Validation covers the WHOLE member list before the caller writes anything,
    so a poisoned entry sitting after ten good ones means none of the eleven
    are installed.
    """
    real_root = os.path.realpath(root)
    names = [m.filename.replace("\\", "/") for m in archive.infolist()]
    for raw in names:
        _reject_dangerous(raw.rstrip("/"))

    prefix = _common_root(names)
    out = []
    for member, raw in zip(archive.infolist(), names):
        if raw.endswith("/"):
            continue                                    # directory entry
        name = raw[len(prefix):] if prefix and raw.startswith(prefix) else raw
        if not name:
            continue
        target = os.path.realpath(os.path.join(real_root, name))
        if target != real_root and not target.startswith(real_root + os.sep):
            raise UpdateError("ARCHIVE TRIES TO WRITE OUTSIDE THE FOLDER -- REFUSED")
        if _is_protected(name):
            continue                                    # your data, not theirs
        out.append((member, name, target))
    return out


# What a real project root looks like from the inside. Used only to recognise
# GitHub's wrapper folder; nothing depends on these existing.
_MARKERS = ("run.bat", "setup.bat", "scp-079 required code")


def _common_root(names):
    """GitHub's source zips wrap everything in 'repo-1.2.0/'. Strip that.

    Only when it really is a wrapper, which means: exactly one top-level
    entry, everything inside it, AND the project's own furniture directly
    within. Requiring the marker is what stops a release that only ships
    memory/ from having "memory" mistaken for a wrapper and stripped - which
    would turn protected paths into ordinary ones and write straight over
    079's files.
    """
    tops = {n.lstrip("/").split("/")[0] for n in names}
    tops.discard("")
    if len(tops) != 1:
        return ""
    only = tops.pop()
    if only in (".", ".."):
        return ""
    prefix = only + "/"
    inside = set()
    for name in names:
        clean = name.lstrip("/")
        if clean and not clean.startswith(prefix):
            return ""                                   # something sits outside it
        rest = clean[len(prefix):]
        if rest:
            inside.add(rest.split("/")[0].lower())
    return prefix if inside & set(_MARKERS) else ""


def backup_dir():
    return os.path.join(config.DATA_DIR, "backup")


def install(zip_path, root=None, keep_backup=True):
    """Unpack a verified zip over the install folder.

    Returns {"written": n, "backup": path or None}. Raises UpdateError and
    changes NOTHING if the archive fails any check - validation happens over
    the whole member list before the first byte is written.
    """
    root = root or config.DATA_DIR
    try:
        archive = zipfile.ZipFile(zip_path)
    except Exception:
        raise UpdateError("DOWNLOAD IS NOT A VALID ZIP -- NOTHING INSTALLED")

    with archive:
        if archive.testzip() is not None:
            raise UpdateError("DOWNLOAD IS CORRUPT -- NOTHING INSTALLED")
        members = _safe_members(archive, root)
        if not members:
            raise UpdateError("RELEASE CONTAINS NOTHING TO INSTALL")

        # Back up only what is about to be overwritten. Copying the whole
        # project would drag 079's memory and every transcript along with it.
        stamp = time.strftime("%Y-%m-%d_%H%M%S")
        backup = os.path.join(backup_dir(), stamp) if keep_backup else None
        written = 0
        for member, name, target in members:
            if backup and os.path.isfile(target):
                spare = os.path.join(backup, name)
                os.makedirs(os.path.dirname(spare), exist_ok=True)
                try:
                    shutil.copy2(target, spare)
                except OSError:
                    pass
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with archive.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst, CHUNK)
            written += 1

    data = load_state()
    data["installed"] = version.VERSION
    data["declined"] = None
    save_state(data)
    return {"written": written,
            "backup": backup if backup and os.path.isdir(backup) else None}


def human_bytes(count):
    value = float(count or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return "%.0f %s" % (value, unit) if unit == "B" else "%.1f %s" % (value, unit)
        value /= 1024
    return "%.1f GB" % value
