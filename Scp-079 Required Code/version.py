"""What build this is.

DELIBERATELY NOT IN config.py. Everything in config.json is user-editable and
deep-merged over the defaults, so a version living there could be edited to
"99.0.0" - which would silently switch updates off forever and look exactly
like a working install. The build number is a fact about the code, not a
setting, so it lives in the code.

Bump VERSION whenever a release is cut. The updater compares this against the
tag on the newest GitHub release, so a build that forgets to bump it will
offer its own version as an update.
"""

import re

VERSION = "1.0.3"

# Tags are compared numerically, not as strings: "1.10.0" is NEWER than
# "1.9.0" even though it sorts earlier. A leading v is accepted because that
# is how GitHub tags usually look, and anything trailing (-beta, +build) is
# kept only for display.
_PARTS = re.compile(r"^\s*v?(\d+(?:\.\d+)*)(.*)$", re.I)


def parse(text):
    """'v1.2.3-beta' -> ((1, 2, 3), '-beta'). None if it is not a version."""
    match = _PARTS.match(str(text or ""))
    if not match:
        return None
    numbers = tuple(int(part) for part in match.group(1).split("."))
    return numbers, match.group(2).strip()


def _padded(a, b):
    width = max(len(a), len(b))
    return a + (0,) * (width - len(a)), b + (0,) * (width - len(b))


def is_newer(candidate, current=VERSION):
    """Is `candidate` a later release than `current`?

    Unparseable input is never newer. That direction matters: a garbled tag
    should mean "no update", never "update to something we cannot read".
    """
    left, right = parse(candidate), parse(current)
    if left is None or right is None:
        return False
    a, b = _padded(left[0], right[0])
    if a != b:
        return a > b
    # Same numbers: a plain release beats a pre-release of itself (1.2.0 is
    # newer than 1.2.0-beta), but two different suffixes are not ranked - we
    # do not guess whether -rc2 follows -beta.
    return bool(right[1]) and not left[1]


def describe(text=VERSION):
    parsed = parse(text)
    if parsed is None:
        return str(text or "UNKNOWN").upper()
    return ("v" + ".".join(str(n) for n in parsed[0]) + parsed[1]).upper()
