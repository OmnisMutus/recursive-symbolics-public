"""tests/test_athanor.py
Unit tests and ground-truth verification for engines/athanor.py per STANDARD.md.

Ground truth:
1. GGUF v3 binary format specification (magic header, endianness, tensor descriptor table, 32-byte alignment).
2. Independent SHA-256 digest computation using standard hashlib.sha256 on raw file bytes.
3. Raw file-slice comparison verifying byte-level accuracy before and after durable rollback.
"""

from __future__ import annotations

import hashlib
import io
import os
import shutil
import struct
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if os.path.join(ROOT, "engines") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "engines"))

import athanor


def make_synthetic_gguf(num_elements: int = 16, fill_byte: bytes = b"A") -> bytes:
    """Constructs a deterministic, valid in-memory GGUF v3 file with one 1D I8 tensor."""
    buf = io.BytesIO()
    buf.write(b"GGUF")
    buf.write(struct.pack("<I", 3))  # version 3
    buf.write(struct.pack("<Q", 1))  # n_tensors = 1
    buf.write(struct.pack("<Q", 0))  # n_kv = 0

    name = b"blk.0.weight"
    buf.write(struct.pack("<Q", len(name)))
    buf.write(name)
    buf.write(struct.pack("<I", 1))  # 1 dimension
    buf.write(struct.pack("<Q", num_elements))
    buf.write(struct.pack("<I", 24))  # Type 24 is I8 (1 byte per element)
    buf.write(struct.pack("<Q", 0))  # offset 0 within tensor data payload

    # 32-byte alignment padding per GGUF specification
    pad = (32 - (buf.tell() % 32)) % 32
    buf.write(b"\x00" * pad)

    # Tensor payload
    buf.write(fill_byte * num_elements)
    return buf.getvalue()


class TestAthanorHeaderAndReader(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_invalid_magic_raises_value_error(self):
        bad_path = os.path.join(self.tmpdir, "corrupt.gguf")
        with open(bad_path, "wb") as fh:
            fh.write(b"NOT_A_GGUF_MAGIC_HEADER")
        with self.assertRaises(ValueError) as ctx:
            athanor.read(bad_path)
        self.assertIn("Not a GGUF file", str(ctx.exception))

    def test_unsupported_version_raises_value_error(self):
        bad_path = os.path.join(self.tmpdir, "v99.gguf")
        buf = io.BytesIO()
        buf.write(b"GGUF")
        buf.write(struct.pack("<I", 99))  # Unsupported version
        buf.write(struct.pack("<Q", 0))
        buf.write(struct.pack("<Q", 0))
        with open(bad_path, "wb") as fh:
            fh.write(buf.getvalue())
        with self.assertRaises(ValueError) as ctx:
            athanor.read(bad_path)
        self.assertIn("isn't supported", str(ctx.exception))

    def test_synthetic_gguf_parses_cleanly(self):
        path = os.path.join(self.tmpdir, "model.gguf")
        raw = make_synthetic_gguf(32, b"X")
        with open(path, "wb") as fh:
            fh.write(raw)

        info = athanor.read(path)
        self.assertEqual(info["version"], 3)
        self.assertEqual(len(info["tensors"]), 1)
        t = athanor.tensor(info, "blk.0.weight")
        self.assertEqual(t["name"], "blk.0.weight")
        self.assertEqual(t["bytes"], 32)
        self.assertEqual(t["end"] - t["start"], 32)


class TestAthanorVesselWorkflow(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.src = os.path.join(self.tmpdir, "source_model.gguf")
        self.dst = os.path.join(self.tmpdir, "vessel_model.gguf")
        self.raw_data = make_synthetic_gguf(16, b"A")
        with open(self.src, "wb") as fh:
            fh.write(self.raw_data)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_vessel_creation_and_independent_sha256_ground_truth(self):
        meta = athanor.create(self.src, self.dst)
        expected_sha = hashlib.sha256(self.raw_data).hexdigest()
        self.assertEqual(meta["sha256"], expected_sha)
        self.assertEqual(athanor.file_sha(self.dst), expected_sha)
        self.assertTrue(athanor.pristine(self.dst))

    def test_write_and_atomic_undo_restores_exact_bytes(self):
        athanor.create(self.src, self.dst)
        info = athanor.read(self.dst)
        t = athanor.tensor(info, "blk.0.weight")

        # Edit 4 bytes within the tensor range
        edit_payload = b"ZZZZ"
        athanor.write(self.dst, t["start"], edit_payload, "test patch")

        # Verify vessel is no longer pristine
        self.assertFalse(athanor.pristine(self.dst))

        # Ground truth byte inspection
        with open(self.dst, "rb") as fh:
            fh.seek(t["start"])
            actual_patched = fh.read(4)
        self.assertEqual(actual_patched, edit_payload)

        # Rollback via undo
        athanor.undo(self.dst)

        # Verify pristine restored
        self.assertTrue(athanor.pristine(self.dst))
        with open(self.dst, "rb") as fh:
            fh.seek(t["start"])
            restored = fh.read(4)
        self.assertEqual(restored, b"AAAA")

    def test_write_outside_tensor_bounds_is_rejected(self):
        athanor.create(self.src, self.dst)
        info = athanor.read(self.dst)
        t = athanor.tensor(info, "blk.0.weight")

        # Attempting to write past tensor end
        with self.assertRaises(PermissionError):
            athanor.write(self.dst, t["end"] + 1, b"X", "out of bounds write")

        # Attempting to write into header space (before data_start)
        with self.assertRaises(PermissionError):
            athanor.write(self.dst, 0, b"X", "header overwrite attempt")

    def test_recover_pending_before_write_and_repair_torn_journal(self):
        import json as _json
        athanor.create(self.src, self.dst)
        d = athanor.check_vessel(self.dst)
        info = athanor.read(self.dst)
        t = athanor.tensor(info, "blk.0.weight")

        # 1. Simulate crash after pending.json written, before vessel bytes changed
        with open(self.dst, "rb") as fh:
            fh.seek(t["start"])
            old = fh.read(4)
        rec = {
            "id": 1, "time": "2026-01-01T00:00:00", "what": "interrupted",
            "tensor": t["name"], "start": t["start"], "bytes": 4,
            "sha_before": hashlib.sha256(old).hexdigest(),
            "sha_after": hashlib.sha256(b"ZZZZ").hexdigest(), "undone": False,
        }
        with open(os.path.join(d, "1.bin"), "wb") as fh:
            fh.write(old)
        with open(os.path.join(d, "pending.json"), "w", encoding="utf-8") as fh:
            _json.dump(rec, fh)

        athanor.check_vessel(self.dst)
        self.assertFalse(os.path.exists(os.path.join(d, "pending.json")))
        self.assertTrue(athanor.pristine(self.dst))

        # 2. Simulate crash after vessel bytes updated, with a torn trailing journal line
        with open(self.dst, "r+b") as fh:
            fh.seek(t["start"])
            fh.write(b"ZZZZ")
        with open(os.path.join(d, "journal.jsonl"), "a", encoding="utf-8") as fh:
            fh.write('{"id": 999, "torn": ')
        with open(os.path.join(d, "pending.json"), "w", encoding="utf-8") as fh:
            _json.dump(rec, fh)

        athanor.check_vessel(self.dst)
        rows = athanor.journal(self.dst)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], 1)
        self.assertIn("recovered", rows[0]["what"])


if __name__ == "__main__":
    unittest.main()
