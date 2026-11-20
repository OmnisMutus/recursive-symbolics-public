# corpus/ledgers/

The meta layer: the tool that keeps the engineering layer and the philosophical layer honest with each other.

A **correspondence ledger** takes claims, such as "this engine's reward shaping follows the Chesed / Geburah
balance", and sorts each one into:

- **VERIFIED**: a real test backs it.
- **FAILED**: a real test contradicts it.
- **UNTESTABLE**: nobody can check it, and that is stated instead of hidden.

A ledger in which every claim is UNTESTABLE refuses to report success.

| File | What it is |
|---|---|
| `correspondence_ledger.py` | The generic framework. The core package's `symbolics/ledger.py` is the same framework, carried into `symbolics/`; it does not import this file. |
| `sephirotic_correspondence_ledger.py` | Worked example: the Sephirotic reward engine. |
| `attractor_correspondence_ledger.py` | Worked example: the recursive attractor engine. |
| `rca_sandbox_gamma_correspondence_ledger.py` | Worked example: the sandbox's gamma cap. |
| `ddpg_correspondence_ledger.py` | Worked example: the DDPG quadcopter controller. |
| `glyph_emotion_correspondence_ledger.py` | Worked example: the 100-emotion codex. |
| `correspondence_ledger_history.py` | Run history: how long since each claim was last checked. |
| `correspondence_ledger_run_history.json` | That history, as recorded. |
| `correspondence_ledger_target_staleness.py` | Marks a claim stale when the code it points at has changed since. |

Run every ledger at once, from `corpus/`:

```bash
python run_all_correspondence_ledgers.py
```

The spec is [`../docs/correspondence_ledger_meta_tool_spec.md`](../docs/correspondence_ledger_meta_tool_spec.md).
Study Module 6 in [`../studies/EXERCISES.md`](../studies/EXERCISES.md) teaches it hands-on.
