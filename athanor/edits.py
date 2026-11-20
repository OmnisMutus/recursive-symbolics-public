"""What athanor can change, all through workshop.write (journaled, undoable, vessel only).

Router bias (gpt-oss and other mixture-of-experts models): each layer's router scores the experts with
ffn_gate_inp (weight + bias, plain F32) and the top few run. Adding to one expert's bias makes it fire more, and a
large negative bias switches it off. Scaling: any F32/F16/BF16 tensor by any factor; MXFP4 by powers of two or zero;
optionally one expert's slice of a 3-D expert tensor."""
import struct

import numpy as np

from . import codec, gguf, workshop

OFF = -1.0e4                          # far below any real router score: the expert is never in the top few


def _layer_bias(info, layer):
    return gguf.tensor(info, f"blk.{int(layer)}.ffn_gate_inp.bias")


def router_bias(path, layer, expert, add=None, set_to=None, off=False):
    info = gguf.read(path)
    t = _layer_bias(info, layer)
    n = t["shape"][0]
    if not 0 <= int(expert) < n:
        raise ValueError(f"Layer {layer} has experts 0 to {n - 1}.")
    if t["type"] != "F32":
        raise ValueError(f"{t['name']} is {t['type']}, expected F32.")
    pos = t["start"] + 4 * int(expert)
    with open(path, "rb") as fh:
        fh.seek(pos)
        cur = struct.unpack("<f", fh.read(4))[0]
    new = OFF if off else (float(set_to) if set_to is not None else cur + float(add or 0))
    if not np.isfinite(new) or abs(new) > 1e6:
        raise ValueError("Bias out of range.")
    what = f"layer {layer} expert {expert}: router bias {cur:g} -> {new:g}" + (" (off)" if off else "")
    rec = workshop.write(path, pos, struct.pack("<f", new), what, info)
    return {"layer": int(layer), "expert": int(expert), "before": cur, "after": new, "journal_id": rec and rec["id"]}


def experts_off(path, experts_by_layer):
    return [router_bias(path, l, e, off=True) for l, es in experts_by_layer.items() for e in es]


def scale(path, name, factor, expert=None):
    """Multiply a tensor (or one expert's slice of it) by `factor`."""
    info = gguf.read(path)
    t = gguf.tensor(info, name)
    kind = t["type"]
    if kind not in codec.SIZES:
        raise ValueError(f"{name} is {kind}; athanor edits F32, F16, BF16 and MXFP4.")
    factor = float(factor)
    if not np.isfinite(factor) or (factor != 0 and not 1e-4 <= abs(factor) <= 1e4):
        raise ValueError("Factor must be 0 or between 0.0001 and 10000 in size.")
    start, size = t["start"], t["bytes"]
    if expert is not None:
        if len(t["shape"]) < 2:
            raise ValueError(f"{name} has no experts.")
        n_exp = t["shape"][-1]
        if not 0 <= int(expert) < n_exp:
            raise ValueError(f"{name} has experts 0 to {n_exp - 1}.")
        size = size // n_exp                     # the last dimension is the expert: its slice is contiguous
        start += int(expert) * size
    with open(path, "rb") as fh:
        fh.seek(start)
        raw = fh.read(size)
    new, notes = codec.scaled(raw, kind, factor)
    what = f"{name}{'' if expert is None else f' expert {expert}'} x {factor:g}"
    rec = workshop.write(path, start, new, what, info)
    return {"tensor": name, "expert": expert, "factor": factor, "type": kind, "bytes": size,
            "journal_id": rec and rec["id"], **notes}


def values(path, name, expert=None, count=8):
    """A look at a tensor's numbers: first values and simple statistics."""
    info = gguf.read(path)
    t = gguf.tensor(info, name)
    start, size = t["start"], t["bytes"]
    if expert is not None:
        size //= t["shape"][-1]
        start += int(expert) * size
    with open(path, "rb") as fh:
        fh.seek(start)
        v = codec.decode(fh.read(size), t["type"])
    return {"tensor": name, "expert": expert, "type": t["type"], "count": int(v.size),
            "first": [round(float(x), 6) for x in v[:count]], "mean": float(v.mean()), "abs_mean": float(np.abs(v).mean()),
            "min": float(v.min()), "max": float(v.max()), "zeros": int((v == 0).sum())}
