"""Decode and re-encode tensor data. MXFP4 follows ggml (and the gguf package): blocks of 32 weights = 1 byte E8M0
exponent + 16 bytes of 4-bit E2M1 codes (element j in the low nibble of byte j, element j+16 in the high nibble);
value = kvalue[code] * 2**(e - 128) for e >= 2 (the 'half' convention: kvalues are doubled E2M1 values)."""
import numpy as np

MXFP4_K = np.array([0, 1, 2, 3, 4, 6, 8, 12, 0, -1, -2, -3, -4, -6, -8, -12], dtype=np.float32)
SIZES = {"F32": (1, 4), "F16": (1, 2), "BF16": (1, 2), "MXFP4": (32, 17)}


def e8m0_half(e):
    e = np.asarray(e, dtype=np.uint32)
    bits = np.where(e < 2, np.uint32(0x00200000) << e, (e - 1) << np.uint32(23)).astype(np.uint32)
    return bits.view(np.float32)


def decode(raw, kind):
    """bytes -> float32 array (flat, element order as stored)."""
    b = np.frombuffer(raw, dtype=np.uint8)
    if kind == "F32":
        return b.view("<f4").astype(np.float32)
    if kind == "F16":
        return b.view("<f2").astype(np.float32)
    if kind == "BF16":
        return (b.view("<u2").astype(np.uint32) << 16).view(np.float32)
    if kind == "MXFP4":
        blk = b.reshape(-1, 17)
        d = e8m0_half(blk[:, 0]).reshape(-1, 1)
        qs = blk[:, 1:]
        codes = np.concatenate([qs & 0x0F, qs >> 4], axis=1)
        return (d * MXFP4_K[codes]).reshape(-1).astype(np.float32)
    raise ValueError(f"Decoding {kind} isn't supported (F32, F16, BF16, MXFP4).")


def bf16_from_f32(x):
    """float32 -> bfloat16 bits, round to nearest even (as PyTorch and ggml do); NaN kept quiet."""
    u = np.asarray(x, dtype=np.float32).view(np.uint32).astype(np.uint64)
    rounded = ((u + 0x7FFF + ((u >> 16) & 1)) >> 16).astype(np.uint16)
    nan = np.isnan(np.asarray(x, dtype=np.float32))
    return np.where(nan, ((u >> 16) | 0x40).astype(np.uint16), rounded)


def scaled(raw, kind, factor):
    """Bytes of the same tensor data multiplied by `factor`. Exact for F32/F16/BF16 up to their rounding; MXFP4 only
    for powers of two (the shared exponent moves; the 4-bit codes stay). Returns (new bytes, notes)."""
    notes = {}
    if kind in ("F32", "F16", "BF16"):
        v = decode(raw, kind) * np.float32(factor)
        if not np.all(np.isfinite(v)):
            raise ValueError("That factor makes some weights infinite; refused.")
        if kind == "F32":
            return v.astype("<f4").tobytes(), notes
        if kind == "F16":
            if np.abs(v).max() > 65504:
                raise ValueError("That factor overflows half precision (above 65504); refused.")
            return v.astype("<f2").tobytes(), notes
        return bf16_from_f32(v).astype("<u2").tobytes(), notes
    if kind == "MXFP4":
        if factor == 0:
            b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 17).copy()
            b[:, 1:] = 0                                   # all codes 0 -> all weights exactly 0
            return b.tobytes(), {"zeroed_blocks": int(b.shape[0])}
        k = np.log2(abs(factor))
        if factor < 0 or abs(k - round(k)) > 1e-12:
            raise ValueError("MXFP4 weights can only be scaled by a power of two (0.25, 0.5, 2, 4...) or zeroed.")
        k = int(round(k))
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 17).copy()
        e = b[:, 0].astype(np.int32)
        live = e >= 2
        ne = e + k
        if np.any(live & ((ne < 2) | (ne > 254))):
            raise ValueError("Some blocks would leave the exponent range; use a smaller power of two.")
        b[live, 0] = ne[live].astype(np.uint8)
        notes["blocks_moved"] = int(live.sum())
        if (~live).any():
            notes["blocks_left_as_is"] = int((~live).sum())   # tiny subnormal-scale blocks
        return b.tobytes(), notes
    raise ValueError(f"Scaling {kind} isn't supported.")
