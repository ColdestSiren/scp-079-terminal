"""Putting text on the system clipboard.

pygame.scrap is unreliable and needs a real video mode, so this uses tkinter
(standard library, present in every normal CPython install) with a Win32
fallback through ctypes. Verified round-trip on this machine: set, then read
back from a separate Tk instance.

Copying is never load-bearing - a failure is reported to the player as a
message, never an exception.
"""

import ctypes


def _via_tkinter(text):
    import tkinter
    root = tkinter.Tk()
    root.withdraw()
    root.clipboard_clear()
    root.clipboard_append(text)
    # flush to the OS before the window goes away, or the clipboard can be
    # dropped when the owning window is destroyed
    root.update()
    root.destroy()
    return True


def _via_win32(text):
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.restype = ctypes.c_void_p

    if not user32.OpenClipboard(None):
        return False
    try:
        user32.EmptyClipboard()
        buffer = ctypes.create_unicode_buffer(text)
        size = ctypes.sizeof(buffer)
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
        if not handle:
            return False
        locked = kernel32.GlobalLock(handle)
        ctypes.memmove(locked, ctypes.byref(buffer), size)
        kernel32.GlobalUnlock(handle)
        return bool(user32.SetClipboardData(CF_UNICODETEXT, handle))
    finally:
        user32.CloseClipboard()


def copy(text):
    """Put text on the clipboard. Returns True on success."""
    if not text:
        return False
    for attempt in (_via_tkinter, _via_win32):
        try:
            if attempt(text):
                return True
        except Exception:
            continue
    return False
