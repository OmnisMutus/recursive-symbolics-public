# corpus/tools/

The framework's symbolic tooling, each tool with an independent correctness test beside it (`test_<tool>.py`).
Run all the tool tests, from this folder:

```bash
python test_all_tools.py
```

## The tools

| Area | Files |
|---|---|
| Symbol lookup and reading | `lookup.py`, `symbolic_debugger.py`, `debugger.py`, `glossary_generator.py` |
| The Delta operator and agency | `delta_operator.py` (gamma), `agency_budget.py` |
| Intention to steps | `ritual_compiler.py` (an A* search from an intention to concrete steps), with two sample outputs: `ritual_test.md`, `ritual_create_a_new_community_garden.md` |
| Translation between traditions | `transcompiler.py` |
| Sorting | `sephirotic_sorting.py`, checked against Python's own `sorted()` |
| Telemetry | `simulate_telemetry.py` (synthetic data), `telemetry_service.py` (a local receiver), `telemetry_analyzer.py`, `feedback_ingester.py` (strips personal data before anything is pooled) |
| Model sandbox | `rca_llm_sandbox.py` |
| Audio | `embed_audio_signature.py`, with `145hz_carrier.wav` |
| Other | `scan_anomaly.py`, `add_meta.py` (a one-off JSON migration) |

Data the tools read: `symbolic_api.json`, `symbolic_schema.json`, `hermetic_qabalah.json`,
`tradition_mappings.json`, `sovereignty_config.json`. `global_attractor_report.json` is a recorded output.
Copies of the first tables are also in [`../data/`](../data/README.md); `tradition_mappings.json` differs between
the two folders.

## What reaches outside your machine

- `scan_anomaly.py` fetches web pages from the URL you give it. It is the only file in the corpus that contacts
  another machine.
- `rca_llm_sandbox.py` talks to a local Ollama server at `localhost:11434`.
- `telemetry_service.py` listens on `127.0.0.1` only.

## Generated files

`community_dataset.jsonl` (written by the telemetry and feedback tools) and `trace-log.txt` are written when the
tools run. Both are git-ignored and never committed.
