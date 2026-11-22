# examples/

Reference implementations of the interfaces in `symbolics/interfaces.py`, using only the standard library. Read
these first if you want to plug your own parser, rules or storage into the framework.

| File | What it shows |
|---|---|
| `quickstart.py` | The whole framework end to end, in four demos (below). Start here. |
| `algebra_simplifier.py` | A `SymbolicBackend` and `RuleEngine` for algebra: rewrites an expression step by step until it stops changing, and checks the result by evaluating both forms on sample values. |
| `propositional_reducer.py` | The same for propositional logic, checked against the full truth table. |

## Run it

```bash
python examples/quickstart.py
```

It prints four demos:

1. **Algebra simplifier:** `(x + 0) * 1 + y - y + --x` reduced to `2 * x`, each step with the rule used, recorded
   in a hash-chained log whose integrity is checked.
2. **Propositional reducer:** a formula reduced to its simplest form and checked across every truth assignment.
3. **The address and lens seam:** a cipher solved exactly, and an address that stays the same whichever lens
   reads it.
4. **The ethics gate and conformance:** a directive sentence measured against the 0.85 cap and rewritten as an
   offer, then the Conformance Suite run.

## Writing your own

Copy one of the two reducers, swap in your own rules, and keep the pattern: bounded depth, a measure that must
go down (or stay level) at every step, cycle detection, and an independent check of the final answer. Then add a
test file under `tests/`. `docs/ASSEMBLY_GUIDE.md` has the templates.
