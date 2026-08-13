"""Headless update check, for the optional login task Setup.bat can install.

Deliberately NOT part of main.py. This runs at every login if the player
opted in, and main.py imports pygame, the personality, the audio engine and
half a dozen other modules before it does anything - paying all of that to
make one HTTPS call at startup would be rude. This imports config, version
and updater and nothing else.

It also cannot open the game's own UI, because there is no window at login.
So a found update is reported with a native message box through ctypes -
no dependency, no console window, and clicking OK does nothing except close
it. INSTALLING IS STILL A DECISION MADE INSIDE THE TERMINAL. This tells you
there is something to install; it never installs anything itself, and it
never touches a file.

    py -3.13 updatecheck.py           check, and say so if there is one
    py -3.13 updatecheck.py --quiet   say nothing when there is nothing
                                      (what the login task uses)
    py -3.13 updatecheck.py --dry-run report to stdout, never pop a box

Exit codes: 0 nothing to do, 1 an update exists, 2 the check failed.
Anything unexpected exits 0 - a failed check at login must be silent and
must never be the reason someone sees an error box before their desktop
has finished loading.
"""

import sys

MB_OK = 0x0
MB_ICONINFORMATION = 0x40
MB_SETFOREGROUND = 0x10000
TITLE = "SCP-079 // CONTAINMENT TERMINAL"


def _box(text, title=TITLE):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            None, text, title, MB_OK | MB_ICONINFORMATION | MB_SETFOREGROUND)
        return True
    except Exception:
        return False


def main(argv):
    quiet = "--quiet" in argv
    dry = "--dry-run" in argv

    try:
        import config
        import updater
        import version
    except Exception as exc:                            # noqa: BLE001
        if not quiet and not dry:
            _box("Could not load the terminal's own files.\n\n%s" % exc)
        print("load failed: %s" % exc)
        return 0

    cfg = config.load()
    name = updater.repo(cfg)
    if not name:
        if dry:
            print("no update source configured")
        elif not quiet:
            _box("No update source is configured.\n\n"
                 "Set updates.repo in config.json.")
        return 0

    try:
        info = updater.check(cfg)
    except updater.UpdateError as exc:
        if dry:
            print("check failed: %s" % exc)
        elif not quiet:
            _box("Could not check for updates.\n\n%s" % exc)
        return 2
    except Exception as exc:                            # noqa: BLE001
        if dry:
            print("check failed: %s" % exc)
        return 2

    if info is None:
        if dry:
            print("up to date (%s)" % version.describe())
        elif not quiet:
            _box("You are on the newest version.\n\n%s" % version.describe())
        return 0

    # A version already turned down does not nag from the login task either.
    # Saying no in the terminal has to mean no everywhere, or the setting is
    # not worth having.
    if updater.declined(info["tag"]):
        if dry:
            print("update %s available but previously declined" % info["version"])
        return 0

    line = ("A newer version of SCP-079 is available.\n\n"
            "    installed   %s\n    available   %s\n\n"
            "Open the terminal and press [U] on the menu to install it. "
            "Nothing has been downloaded or changed."
            % (version.describe(), info["version"]))
    if dry:
        print("update available: %s -> %s" % (version.describe(), info["version"]))
    else:
        _box(line)
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception:                                   # noqa: BLE001
        sys.exit(0)
