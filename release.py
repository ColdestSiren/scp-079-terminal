"""Decide whether this is worth a release, and refuse to cut a broken one.

Two jobs, and the second matters more than the first.

DECIDING. Not every push is a release. A release is warranted for a major
update, a bug fix, or enough small changes to add up to something a player
would notice. A single tidy-up is not. So this counts what has landed since
the last release and says whether it clears the bar, rather than tagging on
reflex. The bar is a NUMBER, so it is arguable, and every number here can be
overridden - see --force and --limit. It advises. It does not decide.

REFUSING. The tag must equal the VERSION inside version.py at that commit.
Getting this wrong is not cosmetic and it has happened twice: v1.0.1 shipped
code saying 1.0.2, and v1.0.2 shipped code saying 1.0.3. A player installs
one of those, the code reports a version newer than the tag it came from, and
the updater offers the same release forever because it can never satisfy it.
That check is the reason this file exists, and --force does NOT skip it.

This does not publish. Creating a GitHub Release needs the web UI (gh is not
installed here), and publishing is the irreversible half - it goes out to
everyone with the update prompt. So this prepares and verifies, prints the
exact link, and stops.
"""

import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
VERSION_FILE = os.path.join(ROOT, "Scp-079 Required Code", "version.py")
REPO = "ColdestSiren/scp-079-terminal"

# How many commits since the last release before this counts as "enough small
# updates to matter". A starting point, not a law: --limit moves it and
# --force ignores it. Bug fixes are worth a release on their own, which no
# counter can detect, so a low number is the honest default.
DEFAULT_LIMIT = 4

# Commit subjects that do not move the needle for a player.
_QUIET = re.compile(r"^(test|tests|chore|docs|typo|comment|wip|refactor)\b",
                    re.IGNORECASE)


def git(*args):
    out = subprocess.run(["git"] + list(args), cwd=ROOT,
                         capture_output=True, text=True)
    return out.stdout.strip(), out.returncode


def current_version():
    with open(VERSION_FILE, "r", encoding="utf-8") as fh:
        match = re.search(r'^VERSION\s*=\s*"([^"]+)"', fh.read(), re.M)
    return match.group(1) if match else None


def version_at(ref):
    out, code = git("show", "%s:Scp-079 Required Code/version.py" % ref)
    if code != 0:
        return None
    match = re.search(r'^VERSION\s*=\s*"([^"]+)"', out, re.M)
    return match.group(1) if match else None


def last_tag():
    out, code = git("describe", "--tags", "--abbrev=0")
    return out if code == 0 and out else None


def commits_since(ref):
    span = "%s..HEAD" % ref if ref else "HEAD"
    out, _ = git("log", span, "--format=%s")
    return [line for line in out.splitlines() if line.strip()]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", nargs="?",
                        help="tag to cut, e.g. 1.0.5 (default: version.py)")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                        help="commits since the last release before one is "
                             "suggested (default %d)" % DEFAULT_LIMIT)
    parser.add_argument("--force", action="store_true",
                        help="release even if under the limit. Does NOT skip "
                             "the version/tag check.")
    parser.add_argument("--yes", action="store_true",
                        help="skip the confirmation prompt")
    args = parser.parse_args(argv)

    version = (args.version or current_version() or "").lstrip("v")
    if not version:
        print("could not read a version from version.py")
        return 2
    tag = "v" + version

    dirty, _ = git("status", "--porcelain")
    previous = last_tag()
    landed = commits_since(previous)
    notable = [c for c in landed if not _QUIET.match(c)]

    print("REPO      %s" % REPO)
    print("HEAD      %s" % (git("log", "--oneline", "-1")[0] or "?"))
    print("VERSION   %s   ->   tag %s" % (version, tag))
    print("SINCE     %s" % (previous or "(no previous tag)"))
    print()
    if landed:
        print("  %d commit(s), %d of them player-visible:" % (len(landed), len(notable)))
        for line in landed[:12]:
            mark = "  " if _QUIET.match(line) else "* "
            print("    %s%s" % (mark, line[:72]))
        if len(landed) > 12:
            print("    ... and %d more" % (len(landed) - 12))
    else:
        print("  nothing has landed since the last tag.")
    print()

    problems = []
    if dirty:
        problems.append("working tree is dirty - commit or stash first")
    existing, code = git("rev-parse", "-q", "--verify", "refs/tags/%s" % tag)
    if code == 0:
        problems.append("tag %s already exists (%s)" % (tag, existing[:8]))
    if not landed:
        problems.append("no commits since %s" % previous)

    # THE CHECK THIS FILE EXISTS FOR. Not skippable by --force.
    head_version = current_version()
    if head_version != version:
        problems.append("version.py says %s but you are tagging %s - fix "
                        "version.py first, or the release offers itself "
                        "forever" % (head_version, tag))

    if problems:
        print("REFUSING:")
        for item in problems:
            print("  - %s" % item)
        return 1

    if len(notable) < args.limit and not args.force:
        print("UNDER THE LIMIT: %d player-visible commit(s), limit is %d."
              % (len(notable), args.limit))
        print()
        print("  That is a judgement call, not a rule. A single bug fix is")
        print("  worth releasing and this counter cannot tell. Override with:")
        print("      py -3.13 release.py %s --force" % version)
        print("  or move the bar with --limit N.")
        return 3

    print("READY. This will create the tag locally and push it.")
    print("Publishing the RELEASE is still a separate, manual step.")
    if not args.yes:
        try:
            reply = input("\ncut and push %s? [y/N] " % tag).strip().lower()
        except EOFError:
            print("\nno answer, doing nothing.")
            return 4
        if reply not in ("y", "yes"):
            print("doing nothing.")
            return 4

    out, code = git("tag", "-a", tag, "-m", tag)
    if code != 0:
        print("could not create the tag: %s" % out)
        return 5
    out, code = git("push", "origin", tag)
    if code != 0:
        print("could not push the tag: %s" % out)
        return 5

    print()
    print("tagged and pushed %s" % tag)
    print()
    print("NOW PUBLISH THE RELEASE (a tag alone offers nobody anything):")
    print("  https://github.com/%s/releases/new?tag=%s" % (REPO, tag))
    print()
    print("  title: %s" % tag)
    print("  label: None, NOT pre-release (pre-releases are skipped by the")
    print("         updater, so nobody would be offered it)")
    print("  notes: player-facing, in-world, and NOTHING about easter eggs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
