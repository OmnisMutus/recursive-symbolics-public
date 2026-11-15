"""athanor: Transactional GGUF model inspection and crash-safe byte-level vessel journal (pure stdlib).

Allows inspecting local GGUF model files (v2/v3) and mutating tensors only on isolated copies ('vessels'),
recording pre-mutation undo binaries, pending recovery markers, and atomic SHA-256 checksums for rollback.

Read-only GGUF format: GGUF v2/v3 as specified by llama.cpp (ggml/docs/gguf.md). Block sizes are those
of the official `gguf` package (GGML_QUANT_SIZES); the tests check this reader against that package's own reader.
"""
import glob
import json
import os
import re
import struct

# ggml type id -> (name, elements per block, bytes per block)
GGML_TYPES = {0: ("F32", 1, 4), 1: ("F16", 1, 2), 2: ("Q4_0", 32, 18), 3: ("Q4_1", 32, 20), 6: ("Q5_0", 32, 22),
              7: ("Q5_1", 32, 24), 8: ("Q8_0", 32, 34), 9: ("Q8_1", 32, 40), 10: ("Q2_K", 256, 84),
              11: ("Q3_K", 256, 110), 12: ("Q4_K", 256, 144), 13: ("Q5_K", 256, 176), 14: ("Q6_K", 256, 210),
              15: ("Q8_K", 256, 292), 16: ("IQ2_XXS", 256, 66), 17: ("IQ2_XS", 256, 74), 18: ("IQ3_XXS", 256, 98),
              19: ("IQ1_S", 256, 50), 20: ("IQ4_NL", 32, 18), 21: ("IQ3_S", 256, 110), 22: ("IQ2_S", 256, 82),
              23: ("IQ4_XS", 256, 136), 24: ("I8", 1, 1), 25: ("I16", 1, 2), 26: ("I32", 1, 4), 27: ("I64", 1, 8),
              28: ("F64", 1, 8), 29: ("IQ1_M", 256, 56), 30: ("BF16", 1, 2), 34: ("TQ1_0", 256, 54),
              35: ("TQ2_0", 256, 66), 39: ("MXFP4", 32, 17), 40: ("NVFP4", 64, 36), 41: ("Q1_0", 128, 18)}
_SCALAR = {0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i", 6: "<f", 7: "<?", 10: "<Q", 11: "<q", 12: "<d"}
STRING, ARRAY = 8, 9
MAX_STRING_BYTES = 16 * 1024 * 1024


class _Reader:
    def __init__(self, fh):
        self.fh = fh
        self.size = os.fstat(fh.fileno()).st_size

    def raw(self, n):
        b = self.fh.read(n)
        if len(b) != n:
            raise ValueError("File ends early: not a complete GGUF file.")
        return b

    def num(self, fmt):
        return struct.unpack(fmt, self.raw(struct.calcsize(fmt)))[0]

    def string(self):
        n = self.num("<Q")
        if n > MAX_STRING_BYTES:
            raise ValueError(f"GGUF string exceeds the maximum of {MAX_STRING_BYTES} bytes.")
        if n > self.size - self.fh.tell():
            raise ValueError("GGUF string extends past the end of the file.")
        return self.raw(n).decode("utf-8", errors="replace")

    def value(self, t, preview):
        if t in _SCALAR:
            return self.num(_SCALAR[t])
        if t == STRING:
            return self.string()
        if t == ARRAY:
            et, n = self.num("<I"), self.num("<Q")
            if et in _SCALAR and et != 7:
                size = struct.calcsize(_SCALAR[et])
                head = [self.num(_SCALAR[et]) for _ in range(min(n, preview))]
                self.fh.seek((n - len(head)) * size, 1)
                return {"array_of": _type_name(et), "length": n, "first": head}
            head = [self.value(et, preview) for _ in range(min(n, preview))]
            for _ in range(n - len(head)):
                self.value(et, 0)
            return {"array_of": _type_name(et), "length": n, "first": head}
        raise ValueError(f"Unknown metadata value type {t}.")


def _type_name(t):
    return {0: "uint8", 1: "int8", 2: "uint16", 3: "int16", 4: "uint32", 5: "int32", 6: "float32", 7: "bool",
            8: "string", 9: "array", 10: "uint64", 11: "int64", 12: "float64"}.get(t, str(t))


_CACHE = {}


def read(path, preview=3):
    """Header, metadata (arrays shortened to their first `preview` items) and tensor table of a GGUF file."""
    size = os.path.getsize(path)
    key = (os.path.abspath(path), size, os.path.getmtime(path), preview)
    if key in _CACHE:
        return _CACHE[key]
    with open(path, "rb") as fh:                      # read only, always
        r = _Reader(fh)
        if r.raw(4) != b"GGUF":
            raise ValueError("Not a GGUF file (no GGUF magic at the start).")
        version = r.num("<I")
        if version not in (2, 3):
            raise ValueError(f"GGUF version {version} isn't supported (2 or 3).")
        n_tensors, n_kv = r.num("<Q"), r.num("<Q")
        kv = {}
        for _ in range(n_kv):
            k = r.string()
            kv[k] = r.value(r.num("<I"), preview)
        tensors = []
        for _ in range(n_tensors):
            name = r.string()
            dims = [r.num("<Q") for _ in range(r.num("<I"))]
            t, off = r.num("<I"), r.num("<Q")
            n = 1
            for d in dims:
                n *= d
            tname, blk, bsz = GGML_TYPES.get(t, (f"type{t}", None, None))
            tensors.append({"name": name, "shape": dims, "type": tname, "elements": n, "offset": off,
                            "bytes": (n // blk) * bsz if blk else None})
        align = kv.get("general.alignment", 32)
        if not isinstance(align, int) or isinstance(align, bool) or align <= 0:
            raise ValueError("Invalid GGUF tensor alignment.")
        here = fh.tell()
        data_start = here + (-here % align)
    out = {"path": path, "file_bytes": size, "version": version, "alignment": align, "data_start": data_start,
           "metadata": kv, "tensors": tensors}
    _CACHE[key] = out
    return out


def validate_edit_layout(info):
    """Fail closed unless every tensor has a known, aligned, in-file, non-overlapping extent."""
    size = os.path.getsize(info["path"])
    align, data_start = info["alignment"], info["data_start"]
    if not isinstance(align, int) or isinstance(align, bool) or align <= 0 or data_start % align:
        raise ValueError("Invalid GGUF tensor alignment; edits are refused.")
    if size != info["file_bytes"] or data_start < 0 or data_start > size:
        raise ValueError("GGUF tensor data starts outside the current file; edits are refused.")
    by_name = {spec[0]: spec[1:] for spec in GGML_TYPES.values()}
    extents = []
    for tensor in info["tensors"]:
        spec = by_name.get(tensor["type"])
        if spec is None or tensor["bytes"] is None:
            raise ValueError(f"Tensor {tensor['name']} has an unknown-size type; edits are refused.")
        block, block_bytes = spec
        elements = tensor["elements"]
        if elements <= 0 or elements % block:
            raise ValueError(f"Tensor {tensor['name']} has an invalid extent; edits are refused.")
        expected = (elements // block) * block_bytes
        offset = tensor["offset"]
        if tensor["bytes"] != expected or offset < 0 or offset % align:
            raise ValueError(f"Tensor {tensor['name']} has a misaligned or invalid extent; edits are refused.")
        start, end = data_start + offset, data_start + offset + expected
        if end > size:
            raise ValueError(f"Tensor {tensor['name']} extends outside the file; edits are refused.")
        extents.append((start, end, tensor["name"]))
    extents.sort()
    for previous, current in zip(extents, extents[1:]):
        if current[0] < previous[1]:
            raise ValueError(f"Tensors {previous[2]} and {current[2]} overlap; edits are refused.")


def _gb(n):
    return f"{n / 1e9:.2f} GB" if n >= 1e9 else f"{n / 1e6:.2f} MB" if n >= 1e6 else f"{n / 1e3:.1f} KB"


def _count(n):
    return f"{n / 1e9:.2f} billion" if n >= 1e9 else f"{n / 1e6:.2f} million" if n >= 1e6 else f"{n:,}"


def summary(info):
    kv, ts = info["metadata"], info["tensors"]
    arch = kv.get("general.architecture", "?")
    g = lambda k, d=None: kv.get(f"{arch}.{k}", d)
    by_type = {}
    for t in ts:
        e = by_type.setdefault(t["type"], {"tensors": 0, "parameters": 0, "bytes": 0})
        e["tensors"] += 1
        e["parameters"] += t["elements"]
        e["bytes"] += t["bytes"] or 0
    params = sum(t["elements"] for t in ts)
    data = sum(t["bytes"] or 0 for t in ts)
    parts = {}
    for t in ts:
        m = re.match(r"blk\.\d+\.(.+?)(?:\.weight|\.bias|_blocks|_scales)?$", t["name"])
        key = m.group(1) if m else t["name"].split(".")[0]
        parts[key] = parts.get(key, 0) + t["elements"]
    tok = kv.get("tokenizer.ggml.tokens")
    tmpl = kv.get("tokenizer.chat_template")
    out = {
        "name": kv.get("general.name"), "architecture": arch, "gguf_version": info["version"],
        "file_size": _gb(info["file_bytes"]), "parameters": f"{_count(params)} ({params:,})",
        "bits_per_weight": round(8 * data / params, 2) if params else None,
        "layers": g("block_count"), "context_length": g("context_length"), "embedding_length": g("embedding_length"),
        "attention_heads": g("attention.head_count"), "kv_heads": g("attention.head_count_kv"),
        "experts": g("expert_count"), "experts_used_per_token": g("expert_used_count"),
        "sliding_window": g("attention.sliding_window"), "rope_freq_base": g("rope.freq_base"),
        "vocabulary": tok["length"] if isinstance(tok, dict) else None,
        "tokenizer": kv.get("tokenizer.ggml.model"),
        "chat_template": (f"{len(tmpl)} characters" if isinstance(tmpl, str) else None),
        "quantization": {k: {"tensors": v["tensors"], "share_of_parameters": f"{100 * v['parameters'] / params:.1f}%",
                             "size": _gb(v["bytes"])} for k, v in sorted(by_type.items(), key=lambda kv_: -kv_[1]["bytes"])},
        "largest_parts": {k: f"{_count(v)} parameters" for k, v in sorted(parts.items(), key=lambda x: -x[1])[:6]},
        "tensors": len(ts), "check": ("tensor sizes add up to the file" if info["data_start"] + data <= info["file_bytes"]
                                      else "tensor sizes run past the end of the file"),
    }
    if out["experts"] and out["experts_used_per_token"]:
        out["note"] = (f"Mixture of experts: each token uses {out['experts_used_per_token']} of {out['experts']} expert "
                       "networks per layer, so far fewer weights work per token than the total.")
    return {k: v for k, v in out.items() if v is not None}


# ---------- finding a model in Ollama's store ----------
def ollama_dir():
    return os.environ.get("OLLAMA_MODELS") or os.path.join(os.path.expanduser("~"), ".ollama", "models")


def find_ollama(model, models_dir=None):
    """Path of the GGUF blob behind an Ollama model name like 'gpt-oss:20b', from Ollama's manifests."""
    d = models_dir or ollama_dir()
    name, _, tag = model.partition(":")
    tag = tag or "latest"
    if "/" not in name:
        name = f"library/{name}"
    cands = [os.path.join(d, "manifests", "registry.ollama.ai", *name.split("/"), tag)]
    cands += glob.glob(os.path.join(d, "manifests", "*", *name.split("/"), tag))
    for m in cands:
        if os.path.isfile(m):
            with open(m, encoding="utf-8") as fh:
                man = json.load(fh)
            for layer in man.get("layers", []):
                if layer.get("mediaType") == "application/vnd.ollama.image.model":
                    blob = os.path.join(d, "blobs", layer["digest"].replace(":", "-"))
                    if os.path.isfile(blob):
                        return blob
            raise FileNotFoundError(f"The manifest for {model} names no model file that exists in {d}\\blobs.")
    raise FileNotFoundError(f"No Ollama model {model} in {d}. (Set OLLAMA_MODELS if Ollama keeps models elsewhere.)")


def tensors(info, pattern="", limit=40):
    rx = re.compile(pattern) if pattern else None
    rows = [t for t in info["tensors"] if not rx or rx.search(t["name"])]
    return {"matching": len(rows), "tensors": [{k: t[k] for k in ("name", "shape", "type", "bytes")} for t in rows[:limit]]}



def inspect(model_or_path, what="summary", pattern="", models_dir=None):
    """`model_or_path`: an Ollama name like 'gpt-oss:20b' or a path to a .gguf file."""
    path = model_or_path if os.path.isfile(model_or_path) else find_ollama(model_or_path, models_dir)
    info = read(path)
    if what == "tensors":
        return {"file": path, **tensors(info, pattern)}
    if what == "metadata":
        kv = {k: v for k, v in info["metadata"].items() if not pattern or re.search(pattern, k)}
        return {"file": path, "metadata": kv}
    return {"file": path, **summary(info), "read_only": "the file was only read, never written"}


def tensor(info, name):
    """One tensor's entry, with its absolute byte range in the file."""
    for t in info["tensors"]:
        if t["name"] == name:
            if t["bytes"] is None:
                raise ValueError(f"Tensor {name} has an unknown-size type {t['type']}.")
            start = info["data_start"] + t["offset"]
            return dict(t, start=start, end=start + t["bytes"])
    near = [t["name"] for t in info["tensors"] if name.split(".")[-2:] == t["name"].split(".")[-2:]][:3]
    raise KeyError(f"No tensor {name}." + (f" Similar: {', '.join(near)}" if near else ""))


# ==========================================================================
# TRANSACTIONAL VESSEL & UNDO JOURNAL
# ==========================================================================

"""The sandbox and its journal. athanor only ever writes to a copy it made itself (a 'vessel'), never to
Ollama's own files. Every write saves the old bytes first, with hashes, so each change can be undone exactly.

A vessel is <name>.gguf with a <name>.athanor/ folder beside it: vessel.json (where it came from), journal.jsonl
(one line per change) and undo/<id>.bin (the bytes before that change)."""
import datetime as dt
import hashlib
import json
import os
import tempfile



def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _replace_durable(source, destination):
    """Atomically replace a same-directory file and request write-through on Windows."""
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
            os.remove(tmp)
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
            os.remove(tmp)
        except FileNotFoundError:
            pass
        raise


def _forms(path):
    """The path as given and as the file system resolves it (symlinks, junctions), normalised for comparison."""
    return {os.path.abspath(path).replace("\\", "/").casefold(), os.path.realpath(path).replace("\\", "/").casefold()}


def is_ollama_blob(path):
    stores = _forms(ollama_dir())
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
    src = source if os.path.isfile(source) else find_ollama(source, models_dir)
    if os.path.exists(dest):
        raise FileExistsError(f"{dest} already exists; choose another name or remove it yourself.")
    if is_ollama_blob(dest):
        raise PermissionError("The vessel can't be inside Ollama's model store.")
    read(src)                                           # refuse anything that isn't a readable GGUF
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
        os.replace(stage_path, dest)
    except BaseException:
        try:
            os.close(stage_fd)
        except OSError:
            pass
        try:
            os.remove(stage_path)
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
    """Complete or roll back an interrupted write or undo using its durable pending marker."""
    d = _dir(path)
    mark = os.path.join(d, "pending.json")
    if not os.path.exists(mark):
        return
    with open(mark, encoding="utf-8") as fh:
        rec = json.load(fh)
    if not isinstance(rec, dict) or type(rec.get("id")) is not int or rec["id"] < 1:
        raise ValueError("The pending change record has an invalid id. Stopped.")
    start, count = rec.get("start"), rec.get("bytes")
    if type(start) is not int or type(count) is not int or start < 0 or count <= 0 or start + count > os.path.getsize(path):
        raise ValueError("The pending change record has an invalid byte range. Stopped.")
    operation = rec.get("operation", "write")
    if operation not in ("write", "undo"):
        raise ValueError("The pending change record has an unknown operation. Stopped.")
    undo_path = redo_path = None
    if operation == "undo":
        expected_redo = f"{rec['id']}.redo.bin"
        if rec.get("redo") != expected_redo:
            raise ValueError("Unsafe undo recovery path.")
        redo_path = _undo_path(d, expected_redo)
    else:
        undo_path = _undo_path(d, f"{rec['id']}.bin")
    info = read(path)
    validate_edit_layout(info)
    end = start + count
    if not any(info["data_start"] + t["offset"] <= start and
               end <= info["data_start"] + t["offset"] + t["bytes"] for t in info["tensors"]):
        raise ValueError("The pending change range is not inside one known tensor. Stopped.")
    with open(path, "rb") as fh:
        fh.seek(start)
        cur = _sha(fh.read(count))
    if cur == rec["sha_after"]:
        rows = _repair_tail(d)
        if operation == "undo":
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
    elif cur == rec["sha_before"]:
        pass
    elif operation == "undo":
        assert redo_path is not None
        with open(redo_path, "rb") as fh:
            original = fh.read()
        if len(original) != count or _sha(original) != rec["sha_before"]:
            raise ValueError(f"Undo {rec['id']} recovery bytes are damaged. Stopped.")
        with open(path, "r+b") as fh:
            fh.seek(start)
            fh.write(original)
            fh.flush()
            os.fsync(fh.fileno())
    else:
        assert undo_path is not None
        with open(undo_path, "rb") as fh:
            original = fh.read()
        if len(original) != count or _sha(original) != rec["sha_before"]:
            raise ValueError(f"Change {rec['id']} recovery bytes are damaged. Stopped.")
        with open(path, "r+b") as fh:
            fh.seek(start)
            fh.write(original)
            fh.flush()
            os.fsync(fh.fileno())
    os.remove(mark)
    if operation == "undo":
        assert redo_path is not None
        try:
            os.remove(redo_path)
        except FileNotFoundError:
            pass
    _fsync_dir(d)


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
    info = info or read(path)
    validate_edit_layout(info)
    end = start + len(new)
    owner = next((t for t in info["tensors"] if info["data_start"] + t["offset"] <= start
                  and end <= info["data_start"] + t["offset"] + t["bytes"]), None)
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
    os.remove(os.path.join(d, "pending.json"))
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
            os.remove(tmp)
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
            os.remove(os.path.join(_dir(path), "pending.json"))
            _fsync_dir(_dir(path))
            try:
                os.remove(redo_path)
            except FileNotFoundError:
                pass
            _fsync_dir(os.path.join(_dir(path), "undo"))
    return done


def pristine(path, progress=None):
    """True if the vessel is byte-for-byte the model it was copied from (hashes the whole file)."""
    with open(os.path.join(check_vessel(path), "vessel.json"), encoding="utf-8") as fh:
        meta = json.load(fh)
    return file_sha(path, progress) == meta["sha256"]


