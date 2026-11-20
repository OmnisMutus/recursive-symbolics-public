# corpus/engines/

The engineering layer: practice engines covering OOP, machine learning, networking, graphics, low-level code and
reinforcement learning, plus the studies and recorded results that go with some of them. Most need NumPy.

The list in [`../test_all_engines.py`](../test_all_engines.py) is the only source of truth for which files count
as the 24 engines and whether each is VERIFIED. Run it from `corpus/`:

```bash
python test_all_engines.py
```

## What is here

| Area | Files |
|---|---|
| OOP and composition | `inheritance_upcasting_engine.py`, `briah_composition_engine.py` |
| Machine learning and statistics | `knn_project.py`, `stat_learning_suite.py`, `doc2vec_cluster_engine.py`, `real_ridge_benchmark_vs_sklearn.py` (checked against a real scikit-learn) |
| Networking | `dht_rca_node.py` (Kademlia), `p2p_swarm_mesh_engine.py`, `grpc_web_bridge.py`, `graphql_mesh_snapshot_engine.py`, `nestjs_vue_cli_simulator.py` |
| Graphics and terminal UI | `opengl_3d_scene_simulator.py`, `terminal_dashboard_deck.py` |
| Low level and safety | `c_low_level_simulator.py`, `ctypes_math_accelerator.py`, `safe_memory_boundary_engine.py`, `hello_world_repo_simulator.py` (Git's SHA-1 commit hashing) |
| Reinforcement learning | `ddpg_quadcopter_rca_engine.py`, `sephirotic_reward_engine.py`, `ddpg_dynamic_geburah_gamma.py`, and the `ddpg_*_study.py` convergence studies with their `*_results.json` |
| The symbolic layer | `recursive_attractor_engine.py`, `standalone_rca_sandbox.py`, `qualia_emotion_classifier.py`, `glyph_emotion_codex.py`, `self_polishing_transmuter.py` |
| Benchmarks | `computational_kabbalah_honest_benchmark.py`, `strict_honest_benchmark_suite.py`, `reconstructed_frameworks_comparison.py` |

## Read these with care

- **`benchmark_simulation_vs_current.py` is retracted.** Its comparison was fabricated, and its docstring explains
  how. It is kept so the retraction stays visible.
- **`ddpg_goal_conditioned_convergence_results_PRE_REWARD_FIX.json`** is the result from before a reward bug was
  fixed, kept beside the corrected one on purpose.
- **Networking engines** open sockets on `127.0.0.1` only, to talk to themselves in their demos and tests.
- **`standalone_rca_sandbox.py`** writes `rca_memory.json` here as it runs. That file is git-ignored.

The tests for these engines are in [`../tests/`](../tests/README.md); the reports and hand verifications are in
[`../docs/`](../docs/README_DOCS.md).
