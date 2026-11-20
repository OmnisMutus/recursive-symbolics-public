# engines/

Standalone engines that sit beside the core. Each can be run on its own. They are not part of the `symbolics`
package, so the core's no-network rule is not checked here, but none of these files opens a network connection.

| File | What it does | Tests |
|---|---|---|
| `sovereign_wrapper.py` | Sits between a model and a person. Before the person sees a reply, it withholds sentences that state as fact what the person is experiencing, softens commands into options, and adds a note that other readings exist when a forceful reply offers only one path. The original and every change are returned beside the result. It matches written patterns, so a diagnosis in an unlisted shape passes through. | `tests/test_sovereign_wrapper.py` |
| `safe_memory_boundary_engine.py` | Checked 32-bit integer arithmetic: refuses an allocation whose size would overflow. | `tests/test_safe_memory_boundary_engine.py` |
| `recursive_attractor_engine.py` | A testable version of the framework's fixed-point and attractor formalism; raises `AbyssException` on non-finite or divergent trajectories. Needs NumPy: without it, importing it raises a clear `ImportError`. | `tests/test_recursive_attractor_engine.py` |
| `standalone_rca_sandbox.py` | An interactive text sandbox: scores text against the Sephirot keyword centroids and answers slash commands such as `/eval <text>` and `/memory`. | `tests/test_standalone_rca_sandbox.py` |
| `engine_composition_loop.py` | Wires the attractor engine and the sandbox together, so one engine's output becomes the other's input. A measurement script. Needs NumPy, through the attractor engine. | `tests/test_engine_composition_loop.py` |

Run one:

```bash
python engines/standalone_rca_sandbox.py
```

**Generated file.** The sandbox writes its learned weights to `engines/rca_memory.json` as it runs. That file is
git-ignored and never committed.

The practice versions of several of these, with their studies and recorded results, are in `corpus/engines/`.

The GGUF model workshop that used to be `athanor.py` here is now its own package, [`../athanor/`](../athanor/README.md).
