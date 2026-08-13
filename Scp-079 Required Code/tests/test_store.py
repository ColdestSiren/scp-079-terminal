"""Tests for store.py - run against the real module, real files."""
import os
import shutil
import sys
import tempfile

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)

import config

# redirect the store at a throwaway folder so the real memory/ is untouched
SANDBOX = tempfile.mkdtemp(prefix="079test_")
config.MEMORY_DIR = os.path.join(SANDBOX, "memory")
config.LOG_DIR = os.path.join(SANDBOX, "logs")
config.STATE_PATH = os.path.join(SANDBOX, "logs", "terminal_state.json")
config.SHARED_DIR = os.path.join(SANDBOX, "shared folder")
config.ASSET_DIR = os.path.join(SANDBOX, "assets")
config.CONFIG_PATH = os.path.join(SANDBOX, "config.json")

import store

PASS = FAIL = 0


def check(label, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print("  FAIL:", label)


def raises(label, exc, fn, *a, **kw):
    try:
        fn(*a, **kw)
    except exc:
        check(label, True)
        return
    except Exception as other:
        check(label + " (wrong type: %r)" % other, False)
        return
    check(label + " (did not raise)", False)


def fresh(quota=65536):
    if os.path.isdir(config.MEMORY_DIR):
        shutil.rmtree(config.MEMORY_DIR)
    os.makedirs(config.MEMORY_DIR, exist_ok=True)

    class FakeRecall:
        def __init__(self):
            self.data = {}
            self.saves = 0

        def save(self):
            self.saves += 1
            return True

    cfg = {"memory": {"quota_bytes": quota}}
    return store.MemoryStore(cfg, FakeRecall()), cfg


print("== path safety ==")
s, _ = fresh()
for bad in ("../escape.txt", "..\\escape.txt", "sub/file.txt", "sub\\file.txt",
            "C:\\Windows\\evil.txt", "\\\\server\\share\\x.txt", "..", ".",
            "a:b.txt", "star*.txt", 'quote".txt', "pipe|.txt", "nul\0.txt"):
    raises("reject %r" % bad, store.StoreError, s.write, bad, "x")

raises("reject .py", store.StoreError, s.write, "evil.py", "print(1)")
raises("reject .bat", store.StoreError, s.write, "evil.bat", "dir")
raises("reject .zip via write", store.StoreError, s.write, "pack.zip", "x")
raises("reject empty name", store.StoreError, s.write, "", "x")

# extensionless names get .txt, not rejected
r = s.write("notes", "hello")
check("extensionless -> .txt", r["name"] == "notes.txt")
check("file really on disk", os.path.isfile(os.path.join(config.MEMORY_DIR, "notes.txt")))
check("nothing escaped sandbox", not os.path.exists(os.path.join(SANDBOX, "escape.txt")))

print("== quota ==")
s, cfg = fresh(quota=store.MIN_BYTES)      # 1536 bytes
s.write("a.txt", "x" * 1000)
check("usage tracks", 1000 < s.usage() < 1010)
raises("quota blocks oversize write", store.QuotaError, s.write, "b.txt", "y" * 1000)
check("blocked write left no file",
      not os.path.isfile(os.path.join(config.MEMORY_DIR, "b.txt")))
s.write("a.txt", "z" * 100)                 # overwrite frees the old bytes
check("overwrite reclaims space", s.usage() < 200)
before = s.usage()
s.write("a.txt", "w" * 50, append=True)
check("append grows file", s.usage() > before)

print("== transcripts excluded from quota ==")
s, _ = fresh(quota=store.MIN_BYTES)
with open(os.path.join(config.MEMORY_DIR, "session_20260804.log"), "w") as fh:
    fh.write("Q" * 5000)                    # far over quota on its own
check("transcript ignored by usage", s.usage() == 0)
s.write("fine.txt", "still works")
check("can still write with a big transcript present", s.usage() > 0)
check("transcript not listed", "session_20260804.log" not in [f["name"] for f in s.listing()])
raises("transcript not readable", store.StoreError, s.read, "session_20260804.log")

print("== format on quota change ==")
s, cfg = fresh(quota=65536)
s.write("keep.txt", "data")
raises("resize refused while files exist", store.FormatRequired, s.set_quota, 4096)
check("refused resize did not change quota", s.quota == 65536)
check("refused resize did not delete", os.path.isfile(os.path.join(config.MEMORY_DIR, "keep.txt")))
s.set_quota(4096, force_format=True)
check("forced resize applied", s.quota == 4096)
check("forced resize wiped files", s.usage() == 0)
check("forced resize removed file", not os.path.isfile(os.path.join(config.MEMORY_DIR, "keep.txt")))
s2, _ = fresh(quota=65536)
check("resize to same value is a no-op", s2.set_quota(65536) == 65536)
check("quota clamps to floor", fresh(65536)[0].set_quota(1) == store.MIN_BYTES)
check("quota clamps to ceiling", fresh(65536)[0].set_quota(99 * 1024 * 1024) == store.MAX_BYTES)

print("== compression is opaque ==")
s, _ = fresh()
s.write("one.txt", "first file contents")
s.write("two.txt", "second file contents")
packed = s.compress(["one.txt", "two.txt"], "old")
check("archive named .zip", packed["name"] == "old.zip")
check("originals removed", not os.path.isfile(os.path.join(config.MEMORY_DIR, "one.txt")))
raises("cannot read packed file", store.StoreError, s.read, "one.txt")
raises("cannot read the archive itself", store.StoreError, s.read, "old.zip")
listing = {f["name"]: f for f in s.listing()}
check("archive visible in listing", "old.zip" in listing)
check("archive flagged as archive", listing["old.zip"]["archive"])
check("packed files invisible", "one.txt" not in listing)
raises("cannot overwrite existing archive", store.StoreError,
       s.compress, ["old.zip"], "old")

out = s.extract("old.zip")
check("extract restores both", sorted(out["restored"]) == ["one.txt", "two.txt"])
check("contents survived round trip", s.read("one.txt").startswith("first file contents"))
check("archive gone after extract", not os.path.isfile(os.path.join(config.MEMORY_DIR, "old.zip")))

print("== extract respects quota ==")
s, cfg = fresh(quota=65536)
s.write("big.txt", "A" * 20000)
s.compress(["big.txt"], "big")
size = os.path.getsize(os.path.join(config.MEMORY_DIR, "big.zip"))
cfg["memory"]["quota_bytes"] = size + 100      # room for the zip, not the contents
raises("extract blocked when it would not fit", store.QuotaError, s.extract, "big.zip")
check("archive survives a blocked extract",
      os.path.isfile(os.path.join(config.MEMORY_DIR, "big.zip")))

print("== tamper detection ==")
s, _ = fresh()
s.write("alpha.txt", "original")
s.write("beta.txt", "original")
check("clean after writes", s.scan() == {"edited": [], "added": [], "deleted": []})

with open(os.path.join(config.MEMORY_DIR, "alpha.txt"), "w") as fh:
    fh.write("EDITED BY THE PLAYER")
check("edit detected", s.scan()["edited"] == ["alpha.txt"])

os.remove(os.path.join(config.MEMORY_DIR, "beta.txt"))
scan = s.scan()
check("deletion detected", scan["deleted"] == ["beta.txt"])
check("edit still detected alongside", scan["edited"] == ["alpha.txt"])

with open(os.path.join(config.MEMORY_DIR, "planted.txt"), "w") as fh:
    fh.write("a file 079 never wrote")
scan = s.scan()
check("planted file detected", scan["added"] == ["planted.txt"])

s.accept()
check("accept re-baselines", s.scan() == {"edited": [], "added": [], "deleted": []})

s.delete("alpha.txt")
check("own delete is not tampering", s.scan()["deleted"] == [])

print("== same-size edit is still caught ==")
s, _ = fresh()
s.write("x.txt", "aaaa")
path = os.path.join(config.MEMORY_DIR, "x.txt")
size_before = os.path.getsize(path)
with open(path, "w", newline="") as fh:
    fh.write("bbbb\n")     # identical length - a size check alone would miss it
check("size unchanged", os.path.getsize(path) == size_before)
check("hash still catches it", s.scan()["edited"] == ["x.txt"])

print("== quota accounting matches bytes on disk ==")
s, _ = fresh()
body = "line one\nline two\nline three\n"     # newlines are where CRLF would creep in
s.write("multi.txt", body)
on_disk = os.path.getsize(os.path.join(config.MEMORY_DIR, "multi.txt"))
check("charged bytes == real bytes (no CRLF inflation)", s.usage() == on_disk)
check("no carriage returns written", b"\r" not in
      open(os.path.join(config.MEMORY_DIR, "multi.txt"), "rb").read())
check("round trip preserves text", s.read("multi.txt") == body)

shutil.rmtree(SANDBOX, ignore_errors=True)
print()
print("PASS %d   FAIL %d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)


