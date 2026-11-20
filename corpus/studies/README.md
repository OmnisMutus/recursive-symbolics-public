# corpus/studies/

The learning path through the corpus. Two documents, in this order:

1. **[master_study_and_onboarding_manual.md](master_study_and_onboarding_manual.md)**: setup from a fresh clone,
   the honest current test status, and the curriculum: five engineering modules and a sixth on the
   philosophical layer and the meta-tooling that checks it.
2. **[EXERCISES.md](EXERCISES.md)**: the workbook. Each module has concrete tasks and a way to check your own
   answer before you look at what the code does. Module 6 includes a sandbox practicum: predict a `/eval` result
   from `engines/standalone_rca_sandbox.py` before running it, check the gamma cap by hand, and trace the
   correspondence ledger's honesty guard yourself.

For a plain-language overview first, read [`../docs/eli5_architecture_guide.md`](../docs/eli5_architecture_guide.md).

## Check the status yourself

The manual states how many engines are VERIFIED. Do not take that from a document: the count changed several
times while the corpus was being built, as engines that existed on disk turned up unregistered and as tests were
written for the rest. Run it, from `corpus/`:

```bash
python test_all_engines.py
```

`../../STANDARD.md` says what VERIFIED, RAN_ONLY, FAILED and MISSING mean.

The manual replaced an older separate syllabus and Week 1 guide, which had drifted into saying different things;
they are no longer in the repository.
