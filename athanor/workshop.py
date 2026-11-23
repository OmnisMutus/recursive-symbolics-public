"""The sandbox and its journal. athanor only ever writes to a copy it made itself (a 'vessel'), never to
Ollama's own files. Every write saves the old bytes first, with hashes, so each change can be undone exactly.

A vessel is <name>.gguf with a <name>.athanor/ folder beside it: vessel.json (where it came from), journal.jsonl
(one line per change) and undo/<id>.bin (the bytes before that change)."""
import datetime as dt
import hashlib
import json
import os
import tempfile
import time

from . import gguf

# Windows lets another program (a virus scanner, the search indexer, a backup tool) hold a file it has just seen
# being written, and while it does, renaming or deleting that file fails with a sharing or lock violation. It
# lasts milliseconds. These are the only errors retried, briefly and with backoff: anything else, and these after
# the last try, is raised at once. Elsewhere `winerror` does not exist, so nothing is ever retried there.
LOCKED = (32, 33)                     # ERROR_SHARING_VIOLATION, ERROR_LOCK_VIOLATION
TRIES = 10
WAIT = 0.05                           # seconds; the k-th retry waits k * WAIT, so at most 2.25 s in all


def _locked(e):
    return isinstance(e, OSError) and getattr(e, "winerror", None) in LOCKED


def _retrying(fn, *args):
    """fn(*args), retried only while Windows reports the file as held by another program."""
    for k in range(1, TRIES + 1):
        try:
            return fn(*args)
        except OSError as e:
            if not _locked(e) or k == TRIES:
                raise
            time.sleep(k * WAIT)


def _remove(path):
    _retrying(os.remove, path)


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _replace_durable(source, destination):
    """Atomically replace a same-directory file and request write-through on Windows."""
    _retrying(_move_once, source, destination)


def _move_once(source, destination):
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        move = ctypes.WinDLL("kernel32", use_last_error=True).MoveFileExW
        move.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD)
        move.restype = wintypes.BOOL
        if not move(source, destination, 0x1 | 0x8):  # REPLACE_EXISTING | WRITE_THROUGH
            raise ctypes.WinError(ctypes.get_last_error())
    else:
        os.replace(source, destination)


def _fsync_dir(path):
    """Persist directory-entry changes where the platform exposes directory fsync."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _undo_dir(d):
    root = os.path.realpath(d)
    path = os.path.join(d, "undo")
    actual = os.path.realpath(path)
    try:
        inside = os.path.normcase(os.path.commonpath((root, actual))) == os.path.normcase(root)
    except ValueError:
        inside = False
    if not inside:
        raise ValueError("Undo backup directory resolves outside the vessel metadata folder.")
    return actual


def _undo_path(d, name):
    if (not isinstance(name, str) or not name or name in (".", "..") or
            os.path.basename(name) != name or "/" in name or "\\" in name):
        raise ValueError("Unsafe undo recovery path.")
    undo_dir = _undo_dir(d)
    path = os.path.join(undo_dir, name)
    actual = os.path.realpath(path)
    try:
        inside = os.path.normcase(os.path.commonpath((undo_dir, actual))) == os.path.normcase(undo_dir)
    except ValueError:
        inside = False
    if not inside:
        raise ValueError("Undo backup resolves outside the undo directory.")
    return path


def _write_backup(d, name, data):
    undo_dir = _undo_dir(d)
    path = _undo_path(d, name)
    fd, tmp = tempfile.mkstemp(prefix=".backup.", suffix=".tmp", dir=undo_dir)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        _replace_durable(tmp, path)
        _fsync_dir(undo_dir)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            _remove(tmp)
        except FileNotFoundError:
            pass
        raise


def _write_pending(path, rec):
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(prefix=".pending.", suffix=".tmp", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(rec, fh)
            fh.flush()
            os.fsync(fh.fileno())
        _replace_durable(tmp, path)
        _fsync_dir(d)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            _remove(tmp)
        except FileNotFoundError:
            pass
        raise


def _forms(path):
    """The path as given and as the file system resolves it (symlinks, junctions), normalised for comparison."""
    return {os.path.abspath(path).replace("\\", "/").casefold(), os.path.realpath(path).replace("\\", "/").casefold()}


def is_ollama_blob(path):
    stores = _forms(gguf.ollama_dir())
    return any("/.ollama/models/" in p or any(p.startswith(s + "/") for s in stores) or "/blobs/sha256-" in p
               for p in _forms(path))


def file_sha(path, progress=None):
    h, size, done = hashlib.sha256(), os.path.getsize(path), 0
    with open(path, "rb") as fh:
        while True:
            b = fh.read(1 << 24)
            if not b:
                break
            h.update(b)
            done += len(b)
            if progress:
                progress(done, size)
    return h.hexdigest()


def create(source, dest, verify=True, models_dir=None, progress=None):
    """Copy a model (Ollama name or .gguf path) to `dest` (a new .gguf path) and register it as a vessel."""
    src = source if os.path.isfile(source) else gguf.find_ollama(source, models_dir)
    if os.path.exists(dest):
        raise FileExistsError(f"{dest} already exists; choose another name or remove it yourself.")
    if is_ollama_blob(dest):
        raise PermissionError("The vessel can't be inside Ollama's model store.")
    gguf.read(src)                                           # refuse anything that isn't a readable GGUF
    os.makedirs(os.path.dirname(os.path.abspath(dest)) or ".", exist_ok=True)
    size, done = os.path.getsize(src), 0
    stage_fd, stage_path = tempfile.mkstemp(prefix=f".{os.path.basename(dest)}.", suffix=".part",
                                           dir=os.path.dirname(os.path.abspath(dest)))
    try:
        with open(src, "rb") as a, os.fdopen(stage_fd, "wb") as b:
            h = hashlib.sha256()
            while True:
                chunk = a.read(1 << 24)
                if not chunk:
                    break
                b.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, size)
            b.flush()
            os.fsync(b.fileno())
        digest = h.hexdigest()
        if verify:
            expect = os.path.basename(src).replace("sha256-", "") if "sha256-" in os.path.basename(src) else None
            if expect and expect != digest:
                raise ValueError("The copy doesn't match Ollama's checksum for the model; nothing kept.")
        _retrying(os.replace, stage_path, dest)
    except BaseException:
        try:
            os.close(stage_fd)
        except OSError:
            pass
        try:
            _remove(stage_path)
        except FileNotFoundError:
            pass
        raise
    meta = {"source": source, "source_file": src, "sha256": digest, "bytes": size,
            "created": dt.datetime.now().isoformat(timespec="seconds")}
    d = _dir(dest)
    os.makedirs(os.path.join(d, "undo"))
    with open(os.path.join(d, "vessel.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1)
    open(os.path.join(d, "journal.jsonl"), "w").close()
    return meta


def _dir(path):
    return os.path.splitext(os.path.abspath(path))[0] + ".athanor"


def check_vessel(path):
    if is_ollama_blob(path):
        raise PermissionError("Refused: that is one of Ollama's own model files. Make a vessel first (athanor vessel).")
    if not os.path.isfile(os.path.join(_dir(path), "vessel.json")):
        raise PermissionError(f"Refused: {path} isn't a vessel made by athanor (no {os.path.basename(_dir(path))}/vessel.json).")
    if os.stat(path).st_nlink > 1:
        raise PermissionError("Refused: the vessel has multiple hard links, so another protected path may name the same file.")
    _recover(path)
    return _dir(path)


def _repair_tail(d):
    """Journal rows, after cutting a torn last line (the program stopped while appending it). Only called while a
    change is pending, so that line can only be the pending change's own record, which recovery rewrites whole.
    A damaged line anywhere else is not guessed at."""
    jp = os.path.join(d, "journal.jsonl")
    with open(jp, "rb") as fh:
        raw = fh.read()
    lines = raw.split(b"\n")
    rows, keep, torn = [], 0, False
    for k, line in enumerate(lines):
        if not line.strip():
            keep += len(line) + 1
            continue
        try:
            rows.append(json.loads(line.decode("utf-8")))
        except (ValueError, UnicodeDecodeError):
            if any(x.strip() for x in lines[k + 1:]):
                raise ValueError(f"The journal is damaged at line {k + 1}, not at its end. Stopped; nothing changed.")
            with open(jp, "r+b") as fh:
                fh.truncate(keep)
                fh.flush()
                os.fsync(fh.fileno())
            torn = True
            break
        keep += len(line) + 1
    if raw and not raw.endswith(b"\n") and lines[-1].strip() and not torn:
        with open(jp, "ab") as fh:
            fh.write(b"\n")
            fh.flush()
            os.fsync(fh.fileno())
    return rows


def _recover(path):
    """Finish or roll back a write or undo that was interrupted, using the pending marker it left behind.

    The bytes now in the changed range tell how far it got: sha_after means the change landed and only its journal
    entry may be missing; sha_before means it never started; anything else means it stopped partway, so the bytes
    saved before it are put back."""
    d = _dir(path)
    mark = os.path.join(d, "pending.json")
    if not os.path.exists(mark):
        return
    with open(mark, encoding="utf-8") as fh:
        rec = json.load(fh)
    backup = _checked_backup(path, d, rec)
    with open(path, "rb") as fh:
        fh.seek(rec["start"])
        now = _sha(fh.read(rec["bytes"]))
    if now == rec["sha_after"]:
        _journal_recovered(path, d, rec)
    elif now != rec["sha_before"]:
        _put_back(path, backup, rec)
    _remove(mark)
    if rec.get("operation", "write") == "undo":
        try:
            _remove(backup)
        except FileNotFoundError:
            pass
    _fsync_dir(d)


def _checked_backup(path, d, rec):
    """Check a pending record before acting on it, and return the file holding the bytes from before the change:
    undo/<id>.bin for a write, undo/<id>.redo.bin for an undo."""
    if not isinstance(rec, dict) or type(rec.get("id")) is not int or rec["id"] < 1:
        raise ValueError("The pending change record has an invalid id. Stopped.")
    start, count = rec.get("start"), rec.get("bytes")
    if type(start) is not int or type(count) is not int or start < 0 or count <= 0 or start + count > os.path.getsize(path):
        raise ValueError("The pending change record has an invalid byte range. Stopped.")
    operation = rec.get("operation", "write")
    if operation not in ("write", "undo"):
        raise ValueError("The pending change record has an unknown operation. Stopped.")
    if operation == "undo":
        expected_redo = f"{rec['id']}.redo.bin"
        if rec.get("redo") != expected_redo:
            raise ValueError("Unsafe undo recovery path.")
        backup = _undo_path(d, expected_redo)
    else:
        backup = _undo_path(d, f"{rec['id']}.bin")
    info = gguf.read(path)
    gguf.validate_edit_layout(info)
    if _tensor_holding(info, start, start + count) is None:
        raise ValueError("The pending change range is not inside one known tensor. Stopped.")
    return backup


def _journal_recovered(path, d, rec):
    """The change landed; make the journal say so. A write gets its row if missing; an undo marks its row undone."""
    rows = _repair_tail(d)
    if rec.get("operation", "write") == "undo":
        row = next((r for r in rows if r["id"] == rec["id"]), None)
        if row is None:
            raise ValueError(f"Undo {rec['id']} completed but its journal row is missing. Stopped.")
        row["undone"] = True
        _rewrite(path, rows)
    elif rec["id"] not in [r["id"] for r in rows]:
        with open(os.path.join(d, "journal.jsonl"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(dict(rec, what=rec["what"] + " (recovered after an interruption)")) + "\n")
            fh.flush()
            os.fsync(fh.fileno())


def _put_back(path, backup, rec):
    """The change stopped partway; write back the bytes saved before it, after checking they are the right ones."""
    start, count = rec["start"], rec["bytes"]
    label = "Undo" if rec.get("operation", "write") == "undo" else "Change"
    with open(backup, "rb") as fh:
        original = fh.read()
    if len(original) != count or _sha(original) != rec["sha_before"]:
        raise ValueError(f"{label} {rec['id']} recovery bytes are damaged. Stopped.")
    with open(path, "r+b") as fh:
        fh.seek(start)
        fh.write(original)
        fh.flush()
        os.fsync(fh.fileno())


def _tensor_holding(info, start, end):
    """The one tensor whose data holds bytes start..end, or None if no single tensor does."""
    return next((t for t in info["tensors"] if info["data_start"] + t["offset"] <= start
                 and end <= info["data_start"] + t["offset"] + t["bytes"]), None)


def journal(path):
    d = check_vessel(path)
    rows = []
    with open(os.path.join(d, "journal.jsonl"), encoding="utf-8") as fh:
        for k, line in enumerate(fh, 1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    raise ValueError(f"The journal is damaged at line {k} and no change was pending. "
                                     f"Stopped: nothing written, nothing undone.") from None
    return rows


def write(path, start, new, what, info=None):
    """Write `new` at byte `start` of a vessel, inside one tensor's data only, journaling the old bytes."""
    d = check_vessel(path)
    info = info or gguf.read(path)
    gguf.validate_edit_layout(info)
    end = start + len(new)
    owner = _tensor_holding(info, start, end)
    if owner is None:
        raise PermissionError("Refused: the write isn't inside one tensor's data (header, metadata and gaps are never written).")
    with open(path, "r+b") as fh:
        fh.seek(start)
        old = fh.read(len(new))
        if old == new:
            return None
        rows = journal(path)
        n = (rows[-1]["id"] + 1) if rows else 1
        rec = {"id": n, "time": dt.datetime.now().isoformat(timespec="seconds"), "what": what, "tensor": owner["name"],
               "start": start, "bytes": len(new), "sha_before": _sha(old), "sha_after": _sha(new), "undone": False}
        _write_backup(d, f"{n}.bin", old)
        _write_pending(os.path.join(d, "pending.json"), rec)  # durable marker after durable undo backup
        fh.seek(start)
        fh.write(new)
        fh.flush()
        os.fsync(fh.fileno())
    with open(os.path.join(d, "journal.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    _remove(os.path.join(d, "pending.json"))
    _fsync_dir(d)
    return rec


def _rewrite(path, rows):
    d = _dir(path)
    journal = os.path.join(d, "journal.jsonl")
    fd, tmp = tempfile.mkstemp(prefix=".journal.", suffix=".tmp", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        _replace_durable(tmp, journal)
        _fsync_dir(d)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            _remove(tmp)
        except FileNotFoundError:
            pass
        raise


def undo(path, which="last"):
    """Undo the last change, a change by id, or 'all' (newest first). Each undo checks the bytes are still the ones
    that change wrote; if not, it stops instead of guessing."""
    rows = journal(path)
    live = [r for r in rows if not r["undone"]]
    if which == "all":
        targets = list(reversed(live))
    elif which == "last":
        targets = live[-1:]
    else:
        targets = [r for r in live if r["id"] == int(which)]
        later = [r for r in live if r["id"] > int(which) and r["tensor"] == (targets[0]["tensor"] if targets else None)]
        if later:
            raise ValueError(f"Change {which} has later changes to the same tensor ({', '.join(str(r['id']) for r in later)}); undo those first.")
    if not targets:
        return []
    done = []
    with open(path, "r+b") as fh:
        for r in targets:
            fh.seek(r["start"])
            cur = fh.read(r["bytes"])
            if _sha(cur) != r["sha_after"]:
                raise ValueError(f"Change {r['id']}: the file no longer holds what it wrote (edited elsewhere?). Stopped; nothing more undone.")
            with open(os.path.join(_dir(path), "undo", f"{r['id']}.bin"), "rb") as u:
                old = u.read()
            if _sha(old) != r["sha_before"]:
                raise ValueError(f"Change {r['id']}: its saved bytes are damaged. Stopped.")
            redo_name = f"{r['id']}.redo.bin"
            _write_backup(_dir(path), redo_name, cur)
            redo_path = _undo_path(_dir(path), redo_name)
            pending = dict(r, operation="undo", redo=redo_name,
                           sha_before=r["sha_after"], sha_after=r["sha_before"])
            _write_pending(os.path.join(_dir(path), "pending.json"), pending)
            fh.seek(r["start"])
            fh.write(old)
            fh.flush()
            os.fsync(fh.fileno())
            r["undone"] = True
            done.append(r["id"])
            _rewrite(path, rows)
            _remove(os.path.join(_dir(path), "pending.json"))
            _fsync_dir(_dir(path))
            try:
                _remove(redo_path)
            except FileNotFoundError:
                pass
            _fsync_dir(os.path.join(_dir(path), "undo"))
    return done


def pristine(path, progress=None):
    """True if the vessel is byte-for-byte the model it was copied from (hashes the whole file)."""
    with open(os.path.join(check_vessel(path), "vessel.json"), encoding="utf-8") as fh:
        meta = json.load(fh)
    return file_sha(path, progress) == meta["sha256"]


