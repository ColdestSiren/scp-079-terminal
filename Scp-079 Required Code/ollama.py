"""Ollama client.

Deliberately stdlib-only (urllib + json + threading) rather than `requests`,
so the terminal runs on a bare Python install with nothing but pygame - one
less thing to go wrong when this gets handed to someone else.

Everything that touches the network runs on a worker thread and reports back
through a Job queue, so the pygame loop never blocks and the CRT keeps
animating while a model loads or a reply streams in.
"""

import json
import os
import queue
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request

DEFAULT_HOST = "http://localhost:11434"

# Where the Windows installer puts it, checked before falling back to PATH.
_KNOWN_PATHS = (
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe"),
    os.path.join(os.environ.get("PROGRAMFILES", ""), "Ollama", "ollama.exe"),
)

DOWNLOAD_URL = "https://ollama.com/download"


class Job:
    """A background task the UI can poll once per frame.

    Events are (kind, payload) tuples: "status", "progress", "token",
    "error", "result".
    """

    def __init__(self):
        self.events = queue.Queue()
        self.done = threading.Event()
        self.cancelled = threading.Event()
        self.error = None
        self.result = None
        self._thread = None

    def emit(self, kind, payload=None):
        self.events.put((kind, payload))

    def poll(self):
        """Drain everything queued since the last frame."""
        out = []
        while True:
            try:
                out.append(self.events.get_nowait())
            except queue.Empty:
                break
        return out

    def cancel(self):
        self.cancelled.set()

    def start(self, target, *args, **kwargs):
        def runner():
            try:
                self.result = target(self, *args, **kwargs)
            except Exception as exc:            # noqa: BLE001 - surfaced to the UI
                self.error = str(exc) or exc.__class__.__name__
                self.emit("error", self.error)
            finally:
                self.done.set()
                self.emit("result", self.result)

        self._thread = threading.Thread(target=runner, daemon=True)
        self._thread.start()
        return self


# ---------------------------------------------------------------------------
# Discovery / service control
# ---------------------------------------------------------------------------
def find_executable():
    """Path to ollama.exe, or None if it is not installed."""
    for path in _KNOWN_PATHS:
        if path and os.path.isfile(path):
            return path
    found = shutil.which("ollama")
    return found or None


def models_dir():
    """Where Ollama keeps the weights.

    OLLAMA_MODELS wins if it is set - people move this to a second drive
    precisely because the models are enormous, and assuming the default
    would report a perfectly healthy install as missing.
    """
    override = os.environ.get("OLLAMA_MODELS")
    if override:
        return override
    home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    return os.path.join(home, ".ollama", "models")


def storage_status():
    """Can the model store be FOUND, and can it be READ?

    Two different failures that look identical from a distance and need
    completely different things from the player:

        missing    Ollama has never pulled a model here, or the folder was
                   moved. Nothing to load.
        blocked    The folder is there and the OS refuses to open it -
                   antivirus quarantine, a locked profile, a permissions
                   mess. The files are fine; something is standing in front
                   of them.

    Reported separately so the boot can say which. Never raises.
    """
    path = models_dir()
    out = {"path": path, "found": False, "readable": False, "error": None,
           "blobs": 0}
    try:
        if not os.path.isdir(path):
            out["error"] = "NOT FOUND"
            return out
        out["found"] = True
    except OSError as exc:
        # isdir itself can fail on a path the process may not stat
        out["error"] = _brief_oserror(exc)
        return out

    try:
        entries = os.listdir(path)
        out["readable"] = True
    except PermissionError as exc:
        out["error"] = _brief_oserror(exc)
        return out
    except OSError as exc:
        out["error"] = _brief_oserror(exc)
        return out

    # The blobs folder is where the weights actually live. An empty models
    # folder with no blobs is "found but nothing in it", which is a different
    # story again from "cannot see it".
    blobs = os.path.join(path, "blobs")
    try:
        if os.path.isdir(blobs):
            out["blobs"] = len(os.listdir(blobs))
    except OSError:
        pass
    if not entries:
        out["error"] = "EMPTY"
    return out


def _brief_oserror(exc):
    text = getattr(exc, "strerror", None) or str(exc)
    return str(text).upper()[:44]


def service_up(host=DEFAULT_HOST, timeout=3.0):
    try:
        with urllib.request.urlopen(host.rstrip("/") + "/api/tags", timeout=timeout):
            return True
    except Exception:
        return False


def start_service(exe, host=DEFAULT_HOST, wait_seconds=20.0):
    """Launch the Ollama server hidden and wait for it to answer.

    Returns True once /api/tags responds, False if it never came up.
    """
    if not exe:
        return False
    try:
        flags = 0
        startupinfo = None
        if os.name == "nt":
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        subprocess.Popen(
            [exe, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
            startupinfo=startupinfo,
        )
    except Exception:
        return False

    deadline = time.time() + max(1.0, wait_seconds)
    while time.time() < deadline:
        if service_up(host, timeout=2.0):
            return True
        time.sleep(0.7)
    return False


def _get_json(url, timeout=10.0):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def list_models(host=DEFAULT_HOST, timeout=10.0):
    """Names of every locally installed model, or [] if unreachable."""
    try:
        data = _get_json(host.rstrip("/") + "/api/tags", timeout=timeout)
    except Exception:
        return []
    return [m.get("name", "") for m in data.get("models", []) if m.get("name")]


def model_sizes(host=DEFAULT_HOST, timeout=10.0):
    """{name: size_in_bytes} for every installed model.

    Size decides whether the current settings are workable: a model far
    larger than the card's VRAM is expensive to load, so evicting it between
    messages costs far more than it does for a small one.
    """
    try:
        data = _get_json(host.rstrip("/") + "/api/tags", timeout=timeout)
    except Exception:
        return {}
    return {m["name"]: int(m.get("size") or 0)
            for m in data.get("models", []) if m.get("name")}


def has_model(name, host=DEFAULT_HOST):
    installed = list_models(host)
    if name in installed:
        return True
    # "llama3.2" should match an installed "llama3.2:latest" and vice versa
    base = name.split(":")[0]
    return any(m.split(":")[0] == base for m in installed)


# ---------------------------------------------------------------------------
# Streaming requests
# ---------------------------------------------------------------------------
def _post_stream(url, payload, job, timeout, on_object):
    """POST json and walk the newline-delimited JSON response as it arrives.

    Stops early and closes the connection if the job is cancelled.
    """
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for raw in resp:
            if job.cancelled.is_set():
                break
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if on_object(obj):
                break


def pull_model_job(model, host=DEFAULT_HOST, timeout=3600):
    """Download a model, reporting progress as it goes."""

    def work(job):
        url = host.rstrip("/") + "/api/pull"
        state = {"status": "", "completed": 0, "total": 0}

        def on_object(obj):
            if obj.get("error"):
                raise RuntimeError(obj["error"])
            status = obj.get("status", "")
            completed = int(obj.get("completed") or 0)
            total = int(obj.get("total") or 0)
            if status != state["status"] or completed != state["completed"]:
                state.update(status=status, completed=completed, total=total)
                job.emit("progress", {"status": status, "completed": completed, "total": total})
            return status == "success"

        _post_stream(url, {"model": model, "stream": True}, job, timeout, on_object)
        return True

    return Job().start(work)


def chat_job(model, messages, host=DEFAULT_HOST, timeout=300, options=None,
             keep_alive=None, think=None):
    """Stream a chat completion; tokens arrive as ("token", text) events.

    keep_alive is a top-level field, not an option - it controls how long
    Ollama holds the weights in memory after the reply ("0" unloads at once,
    "-1" keeps them resident). Worth exposing: reloading a 20-30GB model
    between every message is the difference between playable and unusable.
    Measured on a 22GB model: 37s reload vs 0.3s when already resident.

    think=False turns OFF reasoning on models that support it. This matters
    more than it looks. A reasoning model spends its num_predict budget on
    hidden reasoning FIRST, so a low cap can be entirely consumed before it
    writes a single visible character - the reply comes back empty after a
    long wait. 079 is meant to be terse and unreflective anyway, so reasoning
    is wasted compute for this character. Reasoning tokens, when enabled,
    arrive as separate ("think", text) events so the UI can show them apart
    from speech.
    """

    def work(job):
        url = host.rstrip("/") + "/api/chat"
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": options or {},
        }
        if keep_alive is not None:
            payload["keep_alive"] = keep_alive
        if think is not None:
            payload["think"] = bool(think)
        pieces = []

        def on_object(obj):
            if obj.get("error"):
                raise RuntimeError(obj["error"])
            message = obj.get("message") or {}
            reasoning = message.get("thinking") or ""
            if reasoning:
                job.emit("think", reasoning)
            chunk = message.get("content", "")
            if chunk:
                pieces.append(chunk)
                job.emit("token", chunk)
            return bool(obj.get("done"))

        try:
            _post_stream(url, payload, job, timeout, on_object)
        except urllib.error.HTTPError as exc:
            # Older Ollama builds reject the unknown "think" field outright.
            # Retry once without it rather than failing the whole reply.
            if think is None or exc.code not in (400, 404, 422):
                raise
            payload.pop("think", None)
            job.emit("status", "think-unsupported")
            _post_stream(url, payload, job, timeout, on_object)
        return "".join(pieces)

    return Job().start(work)


def warmup_sync(job, model, host=DEFAULT_HOST, timeout=1800, keep_alive="30m"):
    """Load a model into memory without generating anything.

    An empty prompt makes Ollama resident-load the weights - this is what
    turns the 20-30GB model's long first wait into an honest 'LOCATING
    SCP-079' boot step instead of a frozen-looking first reply.

    Runs on the caller's thread (it is already a background job) and raises
    on failure, so the boot can report why the link never came up.

    keep_alive is passed here too, so the weights loaded during the boot are
    the same ones the first message uses instead of being evicted while the
    player reads the boot text.
    """
    url = host.rstrip("/") + "/api/chat"
    payload = {"model": model, "messages": [], "stream": True,
               "keep_alive": keep_alive}
    _post_stream(url, payload, job, timeout, lambda obj: bool(obj.get("done")))
    return True


def warmup_job(model, host=DEFAULT_HOST, timeout=1800, keep_alive="30m"):
    """warmup_sync as a standalone background job."""
    return Job().start(lambda job: warmup_sync(job, model, host, timeout, keep_alive))
