"""Break-it check: plant each bug below in a scratch copy of athanor and confirm the named test catches it.
Run from the repository root: py -3 tests/athanor_tests/breakit.py   (exit code 0 only if every bug is caught).
Only athanor/ and tests/athanor_tests/ are copied, never the rest of the repository."""
import os
import shutil
import subprocess
import sys
import tempfile

TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(TESTS))
BUGS = [
    ("MXFP4 nibbles read in the wrong order", "athanor/codec.py",
     "np.concatenate([qs & 0x0F, qs >> 4], axis=1)", "np.concatenate([qs >> 4, qs & 0x0F], axis=1)",
     "test_athanor.TestDecode.test_matches_the_official_decoder"),
    ("BF16 truncated instead of rounded", "athanor/codec.py",
     "rounded = ((u + 0x7FFF + ((u >> 16) & 1)) >> 16)", "rounded = (u >> 16)",
     "test_athanor.TestDecode.test_bf16_rounding_matches"),
    ("Expert slice off by one", "athanor/edits.py",
     "its slice is contiguous\n        start += int(expert) * size",
     "its slice is contiguous\n        start += (int(expert) + 1) * size",
     "test_athanor.TestScale.test_one_expert_only"),
    ("Undo doesn't check the bytes are still its own", "athanor/workshop.py",
     'if _sha(cur) != r["sha_after"]:', "if False:",
     "test_athanor.TestJournal.test_undo_order_and_tampering"),
    ("Ollama's own files not recognised", "athanor/workshop.py",
     "stores = _forms(gguf.ollama_dir())\n    return any(", "stores = _forms(gguf.ollama_dir())\n    return False and any(",
     "test_athanor.TestJournal.test_refusals"),
    ("Writes allowed outside tensor data", "athanor/workshop.py",
     "    if owner is None:\n", "    if False:\n",
     "test_athanor.TestJournal.test_refusals"),
    ("Variant keeps Ollama's original file", "athanor/ollama.py",
     'lines.append(f"FROM {os.path.abspath(vessel_path)}")', "lines.append(line)",
     "test_athanor.TestOllama.test_only_from_changes"),
    ("Copy not checked against Ollama's checksum", "athanor/workshop.py",
     "if expect and expect != digest:", "if False:",
     "test_athanor.TestVessel.test_damaged_copy_not_kept"),
    ("A link into Ollama's store judged by the path given, not the file reached", "athanor/workshop.py",
     'os.path.realpath(path).replace("\\\\", "/").casefold()}', 'os.path.abspath(path).replace("\\\\", "/").casefold()}',
     "test_athanor.TestLinksAndInterruptions.test_link_into_ollamas_store_refused"),
    ("Interrupted change never recovered", "athanor/workshop.py",
     "    _recover(path)\n", "",
     "test_athanor.TestLinksAndInterruptions.test_interrupted_change_is_journaled_on_next_use"),
    # The policy changed on 2026-11-08: a partly-written change is rolled back from the undo backup instead of
    # stopping. What has to be planted now is the check that makes the rollback safe, not the old refusal.
    ("Rollback bytes used without checking them against sha_before", "athanor/workshop.py",
     "    if len(original) != count or _sha(original) != rec[\"sha_before\"]:\n"
     "        raise ValueError(f\"{label} {rec['id']} recovery bytes are damaged. Stopped.\")",
     "    if False:\n"
     "        raise ValueError(f\"{label} {rec['id']} recovery bytes are damaged. Stopped.\")",
     "test_athanor.TestLinksAndInterruptions.test_a_damaged_backup_still_stops"),
    ("Torn last journal line left in place", "athanor/workshop.py",
     "                fh.truncate(keep)\n", "                pass\n",
     "test_athanor.TestLinksAndInterruptions.test_torn_last_journal_line_is_repaired"),
    ("Damage inside the journal cut away as if torn", "athanor/workshop.py",
     "            if any(x.strip() for x in lines[k + 1:]):", "            if False:",
     "test_athanor.TestLinksAndInterruptions.test_damage_inside_the_journal_is_not_guessed"),
]


def main():
    caught = 0
    for name, rel, find, repl, test in BUGS:
        tmp = tempfile.mkdtemp()
        try:
            dst = os.path.join(tmp, "a")
            skip = shutil.ignore_patterns("__pycache__")
            shutil.copytree(os.path.join(ROOT, "athanor"), os.path.join(dst, "athanor"), ignore=skip)
            shutil.copytree(TESTS, os.path.join(dst, "tests", "athanor_tests"), ignore=skip)
            p = os.path.join(dst, rel)
            src = open(p, encoding="utf-8").read()
            if src.count(find) != 1:
                print(f"  ?      {name}: bug site found {src.count(find)} times; update this list")
                continue
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(src.replace(find, repl))
            r = subprocess.run([sys.executable, "-m", "unittest", test], cwd=os.path.join(dst, "tests", "athanor_tests"),
                               capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=dst))
            ok = r.returncode != 0
            caught += ok
            print(f"  {'caught' if ok else 'MISSED'}  {name}  ({test.split('.')[-1]})")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    print(f"{caught} of {len(BUGS)} planted bugs caught.")
    return 0 if caught == len(BUGS) else 1


if __name__ == "__main__":
    sys.exit(main())
