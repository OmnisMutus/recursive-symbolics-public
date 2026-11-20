# tests/athanor_tests/fixtures/

The independent ground truth for the athanor tests. Neither file was produced by the code it checks.

| File | What it is |
|---|---|
| `mini_oss.gguf` | A small model shaped like gpt-oss (F32 router, BF16 attention, F16 norms, MXFP4 experts quantized from real numbers), written by the official `gguf` package. Its metadata holds only generic GGUF keys. |
| `mini_oss_expected.npz` | That same package's own decoding of every tensor in it, and its BF16 rounding of `attn_q` scaled by 0.9. |

Do not regenerate these with athanor itself: a reference produced by the code under test can only ever agree with
it.
