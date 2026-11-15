# Contributing to Recursive Symbolics

Thank you for your interest in contributing to `recursive-symbolics`.

This repository operates under strict epistemic standards and automated conformance checks. Before submitting a pull request, please review the requirements below.

---

## 1. Licensing & Inbound-Equals-Outbound (Section G.2)

By contributing to this repository, you agree to the inbound-equals-outbound licensing model specified in **Section G.2 of LICENSE.md**:

- **License Grant:** Anything you deliberately submit for inclusion in the Work is licensed under the RCA Sephirotic Sovereignty License 1.1, including the reciprocal patent grant in Section G.1.
- **Copyright Retention:** No contributor gives up their copyright; you confirm you own or have the full legal right to submit the material you provide.
- **No CLA Overhead:** No separate Contributor License Agreement (CLA) or paperwork is required beyond opening a pull request.

---

## 2. The Verification Contract (STANDARD.md)

Every pull request that modifies or introduces code must adhere to [STANDARD.md](STANDARD.md):

1. **Independent Ground Truth:** Never write a test that checks whether an implementation returns whatever its own code computes. Tests must check output against an independent library, an external published test vector, or an independently computed algorithm that shares zero helper code with the implementation under test.
2. **Boundary & Edge Testing:** Tests must explicitly exercise empty inputs, exact boundaries, one-step past boundaries (off-by-one checks), and type confusion (such as `bool` values passed where `int` is expected).
3. **Prove Tests Can Fail (Mutation Testing):** Demonstrate that your test suite fails when a realistic bug is introduced (e.g. changing `>=` to `>`, removing a bounds guard, or altering a hash constant).
4. **Honest Status Categories:**
   - **`VERIFIED`**: Has an independent ground-truth test file, covers edge cases, has demonstrated break-it mutation failure, and currently passes.
   - **`RAN_ONLY`**: Executes without crashing, but lacks an independent correctness proof. Never describe `RAN_ONLY` code as "working" or "passing."
   - **`FAILED`**: A test failed, timed out, or threw an error.

---

## 3. Offline & AST Conformance Rules (symbolics/)

The core governance package (`symbolics/`) is offline-enforced and statically audited:

- **Article 9 (Zero Network Access):** No module in `symbolics/` may import networking or socket libraries (`socket`, `http`, `urllib`, `requests`, `aiohttp`, etc.). This is verified via AST inspection in `python -m symbolics.conformance`.
- **Zero Third-Party Dependencies:** `symbolics/` must run strictly on the Python standard library.
- **Article 6 (Agency Budget):** Directive strength must never exceed `GAMMA_MAX = 0.85`.
- **Article 5.1(D) & Article 8:** Requests targeting or diagnosing third parties without consent are refused structurally, and symbolic coordinates (`Address`) may never be used to score, rank, or gate human beings.

---

## 4. Pre-Submission Checklist

Before opening a pull request, ensure your diff contains no personal session logs or local paths (Article 9) and verify that all five automated gates pass locally:

```bash
# 1. Run the quickstart demos
python examples/quickstart.py

# 2. Run the offline AST conformance checks (Articles 5.1(D), 6, 8, 9)
python -m symbolics.conformance

# 3. Check architecture index and intent drift
python -m symbolics.layers

# 4. Check for leaked home-folder paths or private identifiers
python -m symbolics.outgoing

# 5. Run the complete unit test suite
python -m unittest discover -s tests -v
```

All five commands must exit with code `0`.
