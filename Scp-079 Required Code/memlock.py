"""Holding 079's memory files open while the terminal is running.

The request: while the game is active, the player should not be able to edit
079's files from outside, the way an open program keeps its own files busy.

HOW IT WORKS. Every file 079 owns gets an open handle with a byte-range lock
on it. Windows then refuses any other process opening it for writing, so
Notepad says the file is in use rather than quietly saving over 079's memory.

WHAT IT IS AND IS NOT. This is a courtesy lock, not protection. Anyone can
close the game and edit freely, and that is fine - the tamper detection is
what handles editing behind its back, and this only closes the window where
an edit could land WHILE 079 is mid-conversation and would never notice.

THE REAL RISK IS LOCKING 079 OUT OF ITS OWN MEMORY, so:

  * every store operation releases the lock first and takes it again after
  * anything unexpected releases everything rather than leaving a file stuck
  * a failure to lock is not an error. If it does not work on this machine
    the game runs exactly as before, per "if possible, otherwise ignore"
  * Windows drops all locks when the process dies, so a crash cannot leave
    files permanently unopenable

Deliberately off by default. A locked file is surprising if you did not ask
for it, and someone who wants to poke at the folder should not have to work
out why Notepad is refusing them.
"""

import ctypes
import os

# WHY NOT msvcrt.locking(). It takes an EXCLUSIVE byte-range lock, which
# blocks readers as well as writers - so 079 could no longer read its own
# memory, which is very much worse than a player being able to edit it. The
# Win32 share mode is the right tool: it says what OTHER openers may do,
# so readers get through and writers do not.
_GENERIC_READ = 0x80000000
_FILE_SHARE_READ = 0x00000001       # others may read, nobody may write
_OPEN_EXISTING = 3
_INVALID_HANDLE = ctypes.c_void_p(-1).value

try:
    _kernel32 = ctypes.windll.kernel32
    _kernel32.CreateFileW.restype = ctypes.c_void_p
    _kernel32.CreateFileW.argtypes = [
        ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
        ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    _kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
except Exception:                   # noqa: BLE001 - not Windows
    _kernel32 = None

# path -> raw Win32 handle holding the file open
_held = {}
enabled = False


def available():
    return _kernel32 is not None


def hold(path):
    """Hold one file open share-read. Silent no-op if it cannot be taken."""
    if not enabled or _kernel32 is None:
        return False
    path = os.path.abspath(path)
    if path in _held or not os.path.isfile(path):
        return False
    handle = _kernel32.CreateFileW(path, _GENERIC_READ, _FILE_SHARE_READ,
                                   None, _OPEN_EXISTING, 0, None)
    if not handle or handle == _INVALID_HANDLE:
        return False
    _held[path] = handle
    return True


def release(path):
    """Let go of one file, so the store can work on it."""
    path = os.path.abspath(path)
    handle = _held.pop(path, None)
    if handle is None:
        return False
    try:
        _kernel32.CloseHandle(handle)
    except Exception:               # noqa: BLE001
        pass
    return True


def release_all():
    for path in list(_held):
        release(path)


def hold_all(directory, extensions=(".txt", ".zip")):
    """Lock everything 079 owns in one directory. Returns how many."""
    if not enabled or _kernel32 is None:
        return 0
    try:
        names = os.listdir(directory)
    except OSError:
        return 0
    taken = 0
    for name in names:
        if os.path.splitext(name)[1].lower() in extensions:
            if hold(os.path.join(directory, name)):
                taken += 1
    return taken


class Unlocked:
    """Release a file for the duration of a store operation, then re-take it.

    Used as a context manager around every write, rename and delete. The
    re-take is in a finally block: an exception mid-write must not leave
    079 holding a lock on a file it then cannot open again itself.
    """

    def __init__(self, *paths):
        self.paths = [p for p in paths if p]
        self.were_held = []

    def __enter__(self):
        for path in self.paths:
            if release(path):
                self.were_held.append(path)
        return self

    def __exit__(self, *exc):
        for path in self.were_held:
            hold(path)
        return False


def count():
    return len(_held)
