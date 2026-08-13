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
import time
import zipfile

import config

TEXT_EXT = ".txt"
ARCHIVE_EXT = ".zip"
TRANSCRIPT_EXT = ".log"

# 1.5KB floor, 2MB ceiling. The ceiling was raised from 1.5MB on request.
MIN_BYTES = 1536
MAX_BYTES = 2097152

# Sizes offered in the settings screen, smallest first.
QUOTA_STEPS = (1536, 8192, 16384, 65536, 262144, 1048576, 2097152)

_BAD_CHARS = set('\\/:*?"<>|\0')


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
            raise StoreError("NO SUCH FILE: %s" % stored)
        try:
            with open(path, "r", encoding="utf-8", errors="replace", newline="") as fh:
                return fh.read()
        except OSError as exc:
            raise StoreError("READ FAILED: %s" % exc)

    # -- writing ------------------------------------------------------------
    def write(self, name, text, append=False):
        stored, path = self._resolve(name)
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
            # disk match the bytes charged against the quota above
            with open(path, "a" if append else "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
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
        try:
            os.replace(old_path, new_path)
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
        for name, sha in on_disk.items():
            known = manifest.get(name)
            if known is None:
                added.append(name)
            elif known.get("sha") != sha:
                edited.append(name)
        for name in manifest:
            if name not in on_disk:
                deleted.append(name)
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
