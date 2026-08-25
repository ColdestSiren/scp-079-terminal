"""Battery state, for the CHECKING POWER line.

Laptops only. A desktop has no battery and gets the plain OK it always had -
this must never invent a warning for a machine that cannot run out.

Uses the Win32 GetSystemPowerStatus through ctypes rather than psutil,
because psutil is not installed under the Python that actually runs the game
(3.13 has pygame, 3.12 has psutil) and a decorative power reading is not
worth a dependency. Anything unexpected reports "unknown" and the boot
carries on - a battery check must never be the reason the terminal will not
start.
"""

import ctypes

# ACLineStatus
OFFLINE, ONLINE, AC_UNKNOWN = 0, 1, 255
# BatteryFlag bit meaning "this machine has no battery at all"
NO_BATTERY = 128

# Below this, unplugged, the player is asked whether to continue. A long
# session with a big model is a genuinely heavy load.
WARN_PERCENT = 30
# At or above this, say nothing - the user asked for it to stop nagging.
IGNORE_PERCENT = 50


class _Status(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", ctypes.c_byte),
        ("BatteryFlag", ctypes.c_byte),
        ("BatteryLifePercent", ctypes.c_byte),
        ("SystemStatusFlag", ctypes.c_byte),
        ("BatteryLifeTime", ctypes.c_ulong),
        ("BatteryFullLifeTime", ctypes.c_ulong),
    ]


def status():
    """{has_battery, plugged_in, percent, known}. Never raises."""
    blank = {"has_battery": False, "plugged_in": True, "percent": None,
             "known": False}
    try:
        raw = _Status()
        if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.pointer(raw)):
            return blank
    except Exception:
        return blank        # not Windows, or the call is unavailable

    flag = raw.BatteryFlag & 0xFF
    if flag == NO_BATTERY or flag == 0xFF:
        return blank        # desktop, or it will not say

    percent = raw.BatteryLifePercent & 0xFF
    ac = raw.ACLineStatus & 0xFF
    return {
        "has_battery": True,
        "plugged_in": ac == ONLINE,
        "percent": None if percent == 255 else int(percent),
        "known": ac in (OFFLINE, ONLINE) and percent != 255,
    }


def concern(state=None):
    """How worried to be: 'none', 'note' or 'warn'.

    warn - unplugged and low enough to ask before starting
    note - unplugged, not critical, worth one line
    none - plugged in, no battery, healthy charge, or unreadable
    """
    state = state if state is not None else status()
    if not state["has_battery"] or not state["known"]:
        return "none"
    if state["plugged_in"]:
        return "none"
    percent = state["percent"]
    if percent is None or percent >= IGNORE_PERCENT:
        return "none"
    return "warn" if percent < WARN_PERCENT else "note"


# ---------------------------------------------------------------------------
# System RAM
# ---------------------------------------------------------------------------
# This is the HOST's memory - what the model has to fit in. Nothing to do with
# the "64K CORE" boot line (period flavour) or VERIFYING STORAGE (079's own
# quota). Three different numbers, all called memory; keep them apart.
#
# Win32 GlobalMemoryStatusEx through ctypes, same reasoning as the battery
# above: psutil is not installed under the Python that runs the game.
class _MemStatus(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def ram_gb():
    """Total physical RAM in GB, or None if it cannot be read.

    None means "do not know", and every caller must treat that as "say
    nothing" rather than "assume the worst" - refusing to load a model
    because a system call failed would be far worse than the risk it guards.
    """
    try:
        raw = _MemStatus()
        raw.dwLength = ctypes.sizeof(_MemStatus)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(raw)):
            return None
        total = int(raw.ullTotalPhys)
        return total / float(1024 ** 3) if total > 0 else None
    except Exception:
        return None


def ram_load_percent():
    """How much of physical RAM is in use, 0-100, or None if unreadable.

    Windows reports this directly as dwMemoryLoad, so it is taken rather than
    worked out from total and free - the two disagree slightly, and a
    threshold compared against a number the OS did not produce is a threshold
    that trips at a figure nobody can reproduce in Task Manager.

    None means "do not know". The watchdog treats that as "not over the line",
    because closing someone's game on the strength of a failed system call is
    far worse than the thing it guards against.
    """
    try:
        raw = _MemStatus()
        raw.dwLength = ctypes.sizeof(_MemStatus)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(raw)):
            return None
        load = int(raw.dwMemoryLoad)
        return load if 0 <= load <= 100 else None
    except Exception:
        return None


def free_ram_gb():
    try:
        raw = _MemStatus()
        raw.dwLength = ctypes.sizeof(_MemStatus)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(raw)):
            return None
        return int(raw.ullAvailPhys) / float(1024 ** 3)
    except Exception:
        return None


# Windows never reports the full sticker figure - firmware and integrated
# graphics reserve a slice before the OS ever sees it. THIS MACHINE reports
# 31.04 GB for 32 GB installed, which is a 3% shortfall and would have failed
# a naive "do you have 32 GB?" test on a machine that plainly does.
#
# So: snap to the nearest standard module total for display, and compare with
# a tolerance. Getting this wrong means telling someone their 32 GB machine
# is too small for the model it can obviously run.
_STANDARD_GB = (2, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 128, 192, 256)
RAM_TOLERANCE = 0.94        # 6% under the sticker figure still counts


def installed_ram_gb(total=None):
    """RAM as the OWNER would describe it, snapped to the nearest real size."""
    total = ram_gb() if total is None else total
    if total is None:
        return None
    for size in _STANDARD_GB:
        if total >= size * RAM_TOLERANCE and total < size * 1.06:
            return float(size)
    return total


def has_ram(required_gb, total=None):
    """Does this machine meet a requirement? None (unknown) counts as YES.

    Unknown must never block: a failed system call is not evidence of a
    small machine, and refusing to load over it would be worse than the
    problem being guarded against.

    `total` overrides the reading, which is what makes any of this testable -
    an earlier version accepted a figure and then ignored it, so every test
    silently measured the developer's own machine instead.
    """
    if total is None:
        total = ram_gb()
    if total is None or not required_gb:
        return True
    return float(total) >= float(required_gb) * RAM_TOLERANCE


def describe_ram(total=None):
    total = installed_ram_gb(total)
    if total is None:
        return "UNKNOWN"
    return "%d GB" % int(round(total))


# ---------------------------------------------------------------------------
# Disk space
# ---------------------------------------------------------------------------
# A language model needs room to page and Ollama writes while it runs. Under
# this, Windows itself starts struggling before the game does.
DISK_CRITICAL_GB = 1.0
DISK_LOW_GB = 3.0


def free_gb(path=None):
    """Free space on the drive the game lives on, in GB. None if unknown."""
    import shutil
    import config
    try:
        usage = shutil.disk_usage(path or config.DATA_DIR)
        return usage.free / float(1024 ** 3)
    except Exception:
        return None


def disk_concern(path=None):
    """'none', 'note' or 'warn'."""
    free = free_gb(path)
    if free is None:
        return "none"
    if free < DISK_CRITICAL_GB:
        return "warn"
    if free < DISK_LOW_GB:
        return "note"
    return "none"


def describe_disk(path=None):
    free = free_gb(path)
    if free is None:
        return "UNKNOWN"
    if free < 10:
        return "%.1f GB FREE" % free
    return "%d GB FREE" % round(free)


def describe(state=None):
    """Short text for the boot line."""
    state = state if state is not None else status()
    if not state["has_battery"]:
        return "AC"
    if not state["known"]:
        return "UNKNOWN"
    if state["plugged_in"]:
        return "AC" if state["percent"] is None else "AC  %d%%" % state["percent"]
    return "BATTERY" if state["percent"] is None else "BATTERY  %d%%" % state["percent"]
