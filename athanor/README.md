# athanor/

Look inside a local GGUF model and change it, **on a copy**, with every change journaled and undoable. It was
written for and tested against a mixture-of-experts model (`gpt-oss:20b`), and reads any GGUF v2/v3 file.

The point is to answer "why does the model behave like this?" by experiment rather than by guess: switch one
expert off, or scale one tensor, then measure the same behaviour again with the same test, then undo.

Inspired by [jade-guff-hacker](https://github.com/lucky-edgelord/jade-guff-hacker) (ideas only; written from the
GGUF specification, no code taken: that repository has no licence).

## The rules it keeps

- It **never** writes to Ollama's own files. It makes a copy (a *vessel*) and works only on that. A file inside
  Ollama's model store is refused even if it looks like a vessel, or is reached through a symlink or junction
  (the path is checked as given and as the file system resolves it).
- Only tensor data is ever written; the header and metadata never.
- Every change saves the old bytes first, with SHA-256 hashes. `undo` puts them back exactly, and refuses if the
  bytes were changed some other way.
- A change is marked as pending before the model is touched. If the program is interrupted, the next command
  finishes the record (new bytes in place) or drops it (old bytes still there); partial writes (neither old
  nor new bytes) are rolled back from the verified undo backup, and recovery stops if that backup itself is
  damaged. A journal line torn by the interruption is cut and rewritten whole; damage anywhere else in the
  journal stops everything instead of being guessed at.
- `pristine` checks the whole vessel is byte-for-byte the original again.

## The modules

| File | What it does | Needs |
|---|---|---|
| `gguf.py` | Reads a GGUF file: header, metadata, tensor table. Finds the file behind an Ollama model name. Read only. | standard library |
| `workshop.py` | The vessel and its journal: `create`, `write`, `undo`, `journal`, `pristine`, crash recovery. | standard library |
| `codec.py` | Decodes and re-encodes tensor data: F32, F16, BF16, and MXFP4 (blocks of 32 weights sharing one exponent byte). | NumPy |
| `edits.py` | The changes you can make, all through `workshop.write`: router bias (expert on, off, more, less) and scaling. | NumPy |
| `ollama.py` | Loads a vessel into Ollama as its own model, so it can be tested like any other. | the `ollama` command |
| `cli.py`, `__main__.py` | The command line below. | |

## Commands

Run from the repository root: `python -m athanor <command> ...`

| Command | Does |
|---|---|
| `inspect gpt-oss:20b` | Summary: parameters, layers, experts, quantization (read only) |
| `inspect gptoss --tensors blk.12.` | Tensors matching a pattern |
| `vessel gpt-oss:20b gptoss` | Copy the model to `vessels/gptoss.gguf` in a repository checkout, `~/.athanor/vessels/gptoss.gguf` when pip-installed, or `$ATHANOR_VESSELS/gptoss.gguf` if set (git-ignored: a copy is the size of the model), checked against Ollama's checksum |
| `values gptoss blk.0.ffn_gate_inp.bias` | A tensor's numbers: first values, mean, min, max, zeros |
| `bias gptoss 12 5 --off` | Switch expert 5 of layer 12 off (router bias -10000: never chosen) |
| `bias gptoss 12 5 --add 0.5` | Make it fire more (or `--add -0.5` less, `--set 0`) |
| `off gptoss "12:5,7 13:0"` | Several experts off at once |
| `scale gptoss blk.12.attn_output.weight 0.9` | Scale a tensor (F32, F16, BF16: any factor) |
| `scale gptoss blk.12.ffn_down_exps.weight 0.5 --expert 5` | Scale one expert (MXFP4: powers of two, or 0) |
| `journal gptoss` | Every change, active or undone |
| `undo gptoss` / `undo gptoss 3` / `undo gptoss all` | Undo the last, one by id, or everything |
| `pristine gptoss` | Check the vessel is the original again |
| `ollama gptoss athanor-gptoss` | Load the vessel into Ollama as its own model |

## An experiment

```text
python -m athanor vessel gpt-oss:20b gptoss        once
python -m athanor off gptoss "12:5"                switch one expert off
python -m athanor ollama gptoss athanor-gptoss     Ollama imports the changed copy
  ...run your own evaluation against athanor-gptoss, and the same one against the original...
python -m athanor undo gptoss                      back to the original
```

`ollama create` imports a fresh copy every time, so run `ollama` again after each change. Remove the variant with
`ollama rm athanor-gptoss`.

## Tests

**Status: passes this repository's mutation gate.** On 2026-11-20, `python -B -m symbolics.mutate` killed 166 of
171 mutants across `gguf.py`, `codec.py`, `edits.py` and `workshop.py`, against both test files below. The other 5
are equivalent (they cannot change behaviour), and each is listed with its reason in
[`../architecture/mutation_guards.json`](../architecture/mutation_guards.json). The first run killed 96 of 171; the
tests that closed the gap are in the classes ending in `Gaps` and `Boundaries`.

From the repository root:

```bash
python -m unittest tests.athanor_tests.test_athanor tests.athanor_tests.test_review_regressions
python tests/athanor_tests/breakit.py
```

Ground truth: a small gpt-oss-shaped model written by the official `gguf` package, and that package's own decoding
of every tensor (MXFP4, BF16, F16, F32) and its BF16 rounding. `breakit.py` plants 13 bugs, one at a time, in a
scratch copy and exits 0 only if every one is caught.

Two tests create symlinks. Windows does not allow that without extra rights, so there they are skipped, and the
planted bug they guard (a link into Ollama's store judged by the path given, not the file reached) is reported as
missed: 12 of 13. On Linux, as in CI, they run.

Without NumPy, `test_athanor.py` reports itself as skipped; `test_review_regressions.py` still runs.

This package replaces the earlier single-file `engines/athanor.py`, which covered the same reading and journal
functions without the codec, the edits or the command line.
