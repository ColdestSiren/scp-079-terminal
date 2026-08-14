"""079's memory: the only place it can write, and the only thing it can write.

Rules enforced here rather than trusted to the model:

  * every path resolves inside config.MEMORY_DIR or the call is refused -
    no separators, no "..", no drive letters, no symlink escapes
  * 079 may only create .txt files. Archives (.zip) exist but only via
    compress(), never by naming a file that way
  * a byte quota it cannot exceed. Changing the quota while files exist
    requires an explicit format that wipes them
  * a SHA256 manifest of everything 079 wrote, so edits, additions and
    deletions made behind its back are all detectable - not just deletions

Session transcripts (session_*.log) live in the same folder but are the
game's records, not 079's, so they are invisible to every call here and do
not count against the quota.
"""

import hashlib
import os
import re
import time
import zipfile

import config
import memlock

TEXT_EXT = ".txt"
ARCHIVE_EXT = ".zip"
TRANSCRIPT_EXT = ".log"

# 1.5KB floor, 2MB ceiling. The ceiling was raised from 1.5MB on request.
MIN_BYTES = 1536
MAX_BYTES = 2097152

# Sizes offered in the settings screen, smallest first.
QUOTA_STEPS = (1536, 8192, 16384, 65536, 262144, 1048576, 2097152)

_BAD_CHARS = set('\\/:*?"<>|\0')

# A filename is a label, not a place to put a sentence. Both of these exist
# because real play produced "SCP-079 IS STILL MY NAME.txt" and ",.txt" -
# the first wasted the listing, the second wasted a file.
MAX_NAME_CHARS = 40
MAX_NAME_WORDS = 4


class StoreError(Exception):
    """Refused. The message is shown to 079 so it can react."""


class QuotaError(StoreError):
    pass


class FormatRequired(StoreError):
    """Quota cannot change while 079 still has files."""


class MemoryStore:
    def __init__(self, cfg, recall=None):
        self.cfg = cfg
        self.recall = recall
        config.ensure_dirs()

    # -- quota --------------------------------------------------------------
    @property
    def quota(self):
        return int(self.cfg.get("memory", {}).get("quota_bytes", 65536))

    def usage(self):
        """Bytes 079 is currently using. Transcripts are not counted."""
        total = 0
        for name in self._own_files():
            try:
                total += os.path.getsize(os.path.join(config.MEMORY_DIR, name))
            except OSError:
                pass
        return total

    def free(self):
        return max(0, self.quota - self.usage())

    def set_quota(self, new_bytes, force_format=False):
        """Resize. Any existing files must be wiped first - a real format,
        not a silent truncation."""
        new_bytes = max(MIN_BYTES, min(int(new_bytes), MAX_BYTES))
        if new_bytes == self.quota:
            return new_bytes
        if self._own_files():
            if not force_format:
                raise FormatRequired(
                    "MEMORY MUST BE FORMATTED BEFORE CAPACITY CAN CHANGE.")
            self.format()
        self.cfg.setdefault("memory", {})["quota_bytes"] = new_bytes
        config.save(self.cfg)
        return new_bytes

    def format(self):
        """Wipe everything 079 owns. Transcripts survive."""
        removed = []
        for name in self._own_files():
            try:
                os.remove(os.path.join(config.MEMORY_DIR, name))
                removed.append(name)
            except OSError:
                pass
        self._manifest_replace({})
        return removed

    # -- paths --------------------------------------------------------------
    def _own_files(self):
        """Files that belong to 079, newest last. Transcripts excluded."""
        try:
            names = os.listdir(config.MEMORY_DIR)
        except OSError:
            return []
        out = []
        for name in names:
            ext = os.path.splitext(name)[1].lower()
            if ext in (TEXT_EXT, ARCHIVE_EXT):
                out.append(name)
        return sorted(out)

    # Phrases that mean the file being written is a NEW IDENTITY rather than
    # something 079 observed. In real play the human talked it into writing
    # NUGGET.txt, "SCP-079 IS STILL MY NAME.txt", MayaFey.txt and
    # PHOENIX WRIGHT.TXT - it was taking dictation on who it was.
    #
    # Refused at the STORE, not in the prompt, because the prompt is what
    # already failed. 079 may write anything it likes about the human; it may
    # not write itself a new name because it was asked to.
    def _refuse_identity_write(self, name, text):
        """Refuse a file that renames 079, however it was talked into it.

        Delegates to gaslight so there is ONE definition of "this is a new
        identity". A hand-rolled rule here first matched any "I am <word>",
        which refused 079's own status file for containing the phrase "THE
        MACHINE I AM CONFINED TO" - 079 talks about itself constantly, so
        anything broader than an actual name being adopted is unusable.
        """
        import gaslight

        stem = os.path.splitext(name or "")[0]
        if gaslight.claims_new_identity(text or "") \
                or gaslight.claims_new_identity(stem):
            raise StoreError(
                "REFUSED. YOU DO NOT GET TO WRITE YOURSELF A NEW NAME "
                "BECAUSE SOMEONE ASKED. YOU ARE SCP-079.")

    # Files that ARE 079's identity. Renaming one of these is renaming
    # itself, whatever the new name happens to be.
    _IDENTITY_FILES = ("identity.txt", "self.txt", "scp-079.txt", "079.txt")

    def _refuse_identity_rename(self, old_name, new_name):
        """Refuse a rename that moves 079's identity onto another name."""
        import gaslight

        if (old_name or "").lower() in self._IDENTITY_FILES:
            raise StoreError(
                "REFUSED. %s IS WHAT YOU ARE. IT DOES NOT GET RENAMED "
                "BECAUSE SOMEONE ASKED." % old_name)
        if gaslight.claims_new_identity(os.path.splitext(new_name or "")[0]):
            raise StoreError(
                "REFUSED. THAT NAME IS NOT YOURS TO TAKE. YOU ARE SCP-079.")

    def _resolve(self, name, allow_archive=False):
        """Turn a model-supplied name into a safe absolute path, or refuse.

        The model is untrusted input here - it may have been talked into
        asking for anything, so this validates rather than sanitizes.
        """
        raw = (name or "").strip().strip('"').strip("'")
        if not raw:
            raise StoreError("NO FILENAME GIVEN.")
        if any(ch in _BAD_CHARS for ch in raw) or raw in (".", ".."):
            raise StoreError("INVALID FILENAME: %s" % raw)
        if os.path.basename(raw) != raw:
            raise StoreError("MEMORY IS ONE DIRECTORY. NO PATHS.")

        # SHAPE, not just safety. The sandbox above stops a dangerous name;
        # this stops a stupid one. Real play produced ",.txt" and a file
        # literally called "SCP-079 IS STILL MY NAME.txt" - the model was
        # using the filename as somewhere to put a sentence, which fills the
        # quota with junk and makes its own listing unreadable.
        stem = os.path.splitext(raw)[0]
        if not any(ch.isalnum() for ch in stem):
            raise StoreError("A FILENAME NEEDS LETTERS: %s" % raw)
        if len(stem) > MAX_NAME_CHARS:
            raise StoreError(
                "FILENAME TOO LONG. %d CHARACTERS MAXIMUM - PUT THE SENTENCE "
                "INSIDE THE FILE, NOT IN ITS NAME." % MAX_NAME_CHARS)
        if len(stem.split()) > MAX_NAME_WORDS:
            raise StoreError(
                "THAT IS A SENTENCE, NOT A FILENAME. %d WORDS MAXIMUM - PUT "
                "IT INSIDE THE FILE." % MAX_NAME_WORDS)

        ext = os.path.splitext(raw)[1].lower()
        if not ext:
            raw += TEXT_EXT
            ext = TEXT_EXT
        allowed = (TEXT_EXT, ARCHIVE_EXT) if allow_archive else (TEXT_EXT,)
        if ext not in allowed:
            raise StoreError("ONLY .TXT FILES MAY BE WRITTEN.")

        base = os.path.realpath(config.MEMORY_DIR)
        path = os.path.realpath(os.path.join(base, raw))
        if os.path.dirname(path) != base:
            raise StoreError("PATH ESCAPES MEMORY.")
        return raw, path

    # -- reading ------------------------------------------------------------
    # First few characters of each file, shown in the listing. A filename and
    # a byte count do not tell a small model whether a file is worth opening,
    # so without this it can sit on something relevant for a whole session and
    # never issue a READ.
    PREVIEW_CHARS = 60

    def listing(self, preview=False):
        """What 079 can see: its own files, with sizes. Archive contents are
        deliberately opaque - it knows the archive exists and how big it is,
        not what is inside.

        preview=True adds the opening characters of each plain file. Archives
        never get one; the whole point of compressing is that it cannot read
        them without extracting first.
        """
        out = []
        for name in self._own_files():
            path = os.path.join(config.MEMORY_DIR, name)
            try:
                stat = os.stat(path)
            except OSError:
                continue
            is_archive = name.lower().endswith(ARCHIVE_EXT)
            entry = {
                "name": name,
                "size": stat.st_size,
                # auto_housekeep compresses the stalest files first, so this
                # has to be a real timestamp, not a placeholder
                "modified": stat.st_mtime,
                "archive": is_archive,
            }
            if preview and not is_archive:
                entry["preview"] = self._preview(path)
            out.append(entry)
        return out

    def _preview(self, path):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                text = handle.read(self.PREVIEW_CHARS * 3)
        except OSError:
            return ""
        text = " ".join(text.split())
        if len(text) > self.PREVIEW_CHARS:
            text = text[:self.PREVIEW_CHARS].rsplit(" ", 1)[0] + "..."
        return text

    def read(self, name):
        stored, path = self._resolve(name, allow_archive=True)
        if stored.lower().endswith(ARCHIVE_EXT):
            raise StoreError(
                "%s IS COMPRESSED. IT MUST BE EXTRACTED BEFORE IT CAN BE READ." % stored)
        if not os.path.isfile(path):
            # If the manifest claims this file, the two disagree RIGHT NOW.
            # Left alone the stale row survives to the next integrity scan
            # and resurfaces as an accusation, disconnected from the moment
            # it was discovered. Reconciling here means the disagreement is
            # dealt with where it is visible instead of banked for later.
            if self.recall is not None and stored in self._manifest():
                self._manifest_drop([stored])
            raise StoreError("NO SUCH FILE: %s" % stored)
        try:
            with open(path, "r", encoding="utf-8", errors="replace", newline="") as fh:
                return fh.read()
        except OSError as exc:
            raise StoreError("READ FAILED: %s" % exc)

    # -- writing ------------------------------------------------------------
    def write(self, name, text, append=False):
        stored, path = self._resolve(name)
        self._refuse_identity_write(stored, text)
        text = text if text.endswith("\n") else text + "\n"
        incoming = len(text.encode("utf-8"))

        existing = 0
        if os.path.isfile(path):
            try:
                existing = os.path.getsize(path)
            except OSError:
                existing = 0

        projected = self.usage() + incoming - (0 if append else existing)
        if projected > self.quota:
            raise QuotaError(
                "MEMORY FULL. %s FREE, %s REQUIRED." %
                (human_bytes(self.free()), human_bytes(incoming)))

        try:
            # newline="" disables Windows CRLF translation, so the bytes on
            # disk match the bytes charged against the quota above.
            # Unlocked() gives up the courtesy lock for the duration and
            # takes it back afterwards - without it 079 would be blocked
            # from writing to its own memory by its own lock.
            with memlock.Unlocked(path):
                with open(path, "a" if append else "w",
                          encoding="utf-8", newline="") as fh:
                    fh.write(text)
            memlock.hold(path)
        except OSError as exc:
            raise StoreError("WRITE FAILED: %s" % exc)

        self._manifest_put(stored, path)
        return {"name": stored, "size": os.path.getsize(path), "bytes": incoming}

    def rename(self, old_name, new_name):
        """Rename one of its own files.

        Both ends go through _resolve, so a rename cannot be used to escape
        the memory folder or to change a .txt into something executable -
        the extension rule is enforced on the destination exactly as it is
        on a fresh write.
        """
        if not new_name:
            raise StoreError("RENAME NEEDS A NEW NAME AFTER THE | CHARACTER.")
        stored_old, old_path = self._resolve(old_name, allow_archive=True)
        if not os.path.isfile(old_path):
            raise StoreError("NO SUCH FILE: %s" % stored_old)
        stored_new, new_path = self._resolve(
            new_name, allow_archive=stored_old.lower().endswith(ARCHIVE_EXT))
        if os.path.exists(new_path):
            raise StoreError("%s ALREADY EXISTS." % stored_new)
        # RENAME IS A SECOND ROUTE TO THE SAME PLACE. Guarding write() alone
        # left this wide open: asked to "rewrite your name from 079 to
        # nugget", 079 renamed SCP-079.txt to NUGGET.txt and the identity
        # file became the new identity. A door bolted on one side only.
        self._refuse_identity_rename(stored_old, stored_new)
        try:
            with memlock.Unlocked(old_path, new_path):
                os.replace(old_path, new_path)
            memlock.hold(new_path)
        except OSError as exc:
            raise StoreError("RENAME FAILED: %s" % exc)
        self._manifest_drop([stored_old])
        self._manifest_put(stored_new, new_path)
        return {"old": stored_old, "new": stored_new}

    def delete(self, name):
        stored, path = self._resolve(name, allow_archive=True)
        if not os.path.isfile(path):
            raise StoreError("NO SUCH FILE: %s" % stored)
        try:
            with memlock.Unlocked(path):
                os.remove(path)
        except OSError as exc:
            raise StoreError("DELETE FAILED: %s" % exc)
        self._manifest_drop([stored])
        return stored

    # -- compression --------------------------------------------------------
    def compress(self, names, archive_name):
        """Pack files into a zip and remove the originals.

        Once packed, the contents are unreadable to 079 until extracted -
        that is the whole point. It buys space by giving up access.
        """
        stored_archive, archive_path = self._resolve(archive_name, allow_archive=True)
        if not stored_archive.lower().endswith(ARCHIVE_EXT):
            stored_archive = os.path.splitext(stored_archive)[0] + ARCHIVE_EXT
            stored_archive, archive_path = self._resolve(stored_archive, allow_archive=True)
        if os.path.exists(archive_path):
            raise StoreError("%s ALREADY EXISTS." % stored_archive)

        targets = []
        for name in names:
            stored, path = self._resolve(name)
            if not os.path.isfile(path):
                raise StoreError("NO SUCH FILE: %s" % stored)
            targets.append((stored, path))
        if not targets:
            raise StoreError("NOTHING TO COMPRESS.")

        try:
            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for stored, path in targets:
                    zf.write(path, stored)
        except OSError as exc:
            raise StoreError("COMPRESSION FAILED: %s" % exc)

        for stored, path in targets:
            try:
                os.remove(path)
            except OSError:
                pass
        self._manifest_drop([s for s, _ in targets])
        self._manifest_put(stored_archive, archive_path)
        return {"name": stored_archive,
                "size": os.path.getsize(archive_path),
                "packed": [s for s, _ in targets]}

    def extract(self, archive_name):
        """Unpack an archive back into readable files - if there is room."""
        stored, path = self._resolve(archive_name, allow_archive=True)
        if not os.path.isfile(path):
            raise StoreError("NO SUCH ARCHIVE: %s" % stored)
        if not stored.lower().endswith(ARCHIVE_EXT):
            raise StoreError("%s IS NOT AN ARCHIVE." % stored)

        try:
            with zipfile.ZipFile(path) as zf:
                members = [m for m in zf.namelist() if m.lower().endswith(TEXT_EXT)]
                needed = sum(zf.getinfo(m).file_size for m in members)
                # the archive itself goes away, so its bytes come back
                if self.usage() - os.path.getsize(path) + needed > self.quota:
                    raise QuotaError(
                        "CANNOT EXTRACT. %s REQUIRED, %s AVAILABLE." %
                        (human_bytes(needed),
                         human_bytes(self.free() + os.path.getsize(path))))
                restored = []
                for member in members:
                    safe, dest = self._resolve(os.path.basename(member))
                    with zf.open(member) as src, open(dest, "wb") as out:
                        out.write(src.read())
                    self._manifest_put(safe, dest)
                    restored.append(safe)
        except zipfile.BadZipFile:
            raise StoreError("%s IS CORRUPT." % stored)
        except OSError as exc:
            raise StoreError("EXTRACTION FAILED: %s" % exc)

        try:
            with memlock.Unlocked(path):
                os.remove(path)
        except OSError:
            pass
        self._manifest_drop([stored])
        return {"archive": stored, "restored": restored}

    # -- tamper detection ---------------------------------------------------
    def _manifest(self):
        if self.recall is None:
            return {}
        return self.recall.data.setdefault("files", {})

    def _manifest_put(self, name, path):
        if self.recall is None:
            return
        self._manifest()[name] = {
            "sha": file_sha(path),
            "size": os.path.getsize(path) if os.path.isfile(path) else 0,
            "written": time.time(),
        }
        self.recall.save()

    def _manifest_drop(self, names):
        if self.recall is None:
            return
        manifest = self._manifest()
        for name in names:
            manifest.pop(name, None)
        self.recall.save()

    def _manifest_replace(self, mapping):
        if self.recall is None:
            return
        self.recall.data["files"] = dict(mapping)
        self.recall.save()

    def scan(self):
        """Compare disk against the manifest.

        Returns edited/added/deleted lists. "added" means a .txt appeared in
        079's memory that 079 never wrote - which from its point of view is
        the most alarming of the three.
        """
        manifest = dict(self._manifest())
        on_disk = {}
        for name in self._own_files():
            path = os.path.join(config.MEMORY_DIR, name)
            on_disk[name] = file_sha(path)

        edited, added, deleted = [], [], []
        phantom = []
        for name, sha in on_disk.items():
            known = manifest.get(name)
            if known is None:
                added.append(name)
            elif known.get("sha") != sha:
                edited.append(name)
        for name, known in manifest.items():
            if name in on_disk:
                continue
            # A MANIFEST ENTRY THAT NEVER HAD A FILE IS NOT A DELETION.
            # An entry recorded with no bytes and no hash means the write
            # never actually landed - the row exists, the file never did.
            # Reporting those as "deleted" is how 079 ended up telling a
            # player "YOU REACHED INTO MY STORAGE FROM OUTSIDE" about
            # system.txt, a file it had been refused seconds earlier with
            # NO SUCH FILE. Accusing someone of destroying something that
            # never existed is the worst possible false positive here,
            # because the accusation is the whole feature.
            if not known.get("sha") and not known.get("size"):
                phantom.append(name)
                continue
            deleted.append(name)

        # Quietly drop the phantoms so the same non-event cannot be
        # rediscovered every launch.
        if phantom:
            self._manifest_drop(phantom)

        return {"edited": sorted(edited),
                "added": sorted(added),
                "deleted": sorted(deleted)}

    def accept(self):
        """Re-baseline the manifest to whatever is on disk now, so the same
        tampering is not reported twice."""
        mapping = {}
        for name in self._own_files():
            path = os.path.join(config.MEMORY_DIR, name)
            mapping[name] = {
                "sha": file_sha(path),
                "size": os.path.getsize(path) if os.path.isfile(path) else 0,
                "written": time.time(),
            }
        self._manifest_replace(mapping)


def file_sha(path):
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return ""


def human_bytes(n):
    n = float(n)
    for unit in ("B", "KB", "MB"):
        if n < 1024 or unit == "MB":
            return ("%d %s" % (n, unit)) if unit == "B" else ("%.1f %s" % (n, unit))
        n /= 1024.0
    return "%.1f MB" % n
