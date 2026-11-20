"""Reading GGUF model files (read only): a look inside a GGUF model file (the format Ollama and llama.cpp use): header, metadata, tensor table,
sizes by quantization type, and a plain summary. The file is only ever opened for reading.

Format: GGUF v2/v3 as specified by llama.cpp (ggml/docs/gguf.md). Block sizes are those of the official `gguf`
package (GGML_QUANT_SIZES); the tests check this reader against that package's own reader."""
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
