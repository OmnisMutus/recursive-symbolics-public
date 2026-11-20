"""athanor: look inside a local model and change it, on a copy, with every change journaled and undoable."""
import argparse
import json
import os
import sys

from . import edits, gguf, ollama, workshop

HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VESSELS = os.path.join(HOME, "vessels")


def _bar(done, total):
    print(f"\r  {done / 1e9:6.2f} / {total / 1e9:.2f} GB", end="", flush=True)


def _vessel(name):
    p = name if name.lower().endswith(".gguf") else os.path.join(VESSELS, name + ".gguf")
    return p


def _experts(spec):
    """'12:5,7 13:0' -> {12: [5, 7], 13: [0]}"""
    out = {}
    for part in spec.split():
        layer, _, es = part.partition(":")
        out[int(layer)] = [int(e) for e in es.split(",") if e != ""]
    return out


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
    ap = argparse.ArgumentParser(prog="athanor", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("inspect", help="summary of a model (Ollama name, vessel name or .gguf)")
    p.add_argument("model")
    p.add_argument("--tensors", metavar="PATTERN")
    p.add_argument("--meta", metavar="PATTERN")
    p = sub.add_parser("vessel", help="copy an Ollama model into a vessel you can change")
    p.add_argument("model", help="e.g. gpt-oss:20b")
    p.add_argument("name", help="vessel name, e.g. gptoss")
    p.add_argument("--no-verify", action="store_true")
    p = sub.add_parser("values", help="look at a tensor's numbers")
    p.add_argument("vessel"); p.add_argument("tensor"); p.add_argument("--expert", type=int)
    p = sub.add_parser("bias", help="change one expert's router bias")
    p.add_argument("vessel"); p.add_argument("layer", type=int); p.add_argument("expert", type=int)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--add", type=float); g.add_argument("--set", type=float); g.add_argument("--off", action="store_true")
    p = sub.add_parser("off", help="switch experts off, e.g. athanor off gptoss \"12:5,7 13:0\"")
    p.add_argument("vessel"); p.add_argument("spec")
    p = sub.add_parser("scale", help="multiply a tensor (or one expert of it) by a factor")
    p.add_argument("vessel"); p.add_argument("tensor"); p.add_argument("factor", type=float)
    p.add_argument("--expert", type=int)
    p = sub.add_parser("journal", help="list the changes made to a vessel")
    p.add_argument("vessel")
    p = sub.add_parser("undo", help="undo the last change, a change by id, or all")
    p.add_argument("vessel"); p.add_argument("which", nargs="?", default="last")
    p = sub.add_parser("pristine", help="check the vessel is byte-for-byte the original again (hashes 14 GB)")
    p.add_argument("vessel")
    p = sub.add_parser("ollama", help="load the vessel into Ollama as its own model, so it can be tested like any other model")
    p.add_argument("vessel"); p.add_argument("name", help="e.g. athanor-gptoss")
    p.add_argument("--original", default=None, help="the Ollama model it was copied from (default: from vessel.json)")
    a = ap.parse_args(argv)
    try:
        out = run(a)
    except (ValueError, KeyError, PermissionError, FileNotFoundError, FileExistsError, RuntimeError) as e:
        print(f"athanor: {e}", file=sys.stderr)
        return 1
    if out is not None:
        print(out if isinstance(out, str) else json.dumps(out, ensure_ascii=False, indent=1))
    return 0


def run(a):
    if a.cmd == "inspect":
        src = _vessel(a.model) if os.path.isfile(_vessel(a.model)) else a.model
        what = "tensors" if a.tensors is not None else "metadata" if a.meta is not None else "summary"
        return gguf.inspect(src, what, a.tensors or a.meta or "")
    if a.cmd == "vessel":
        dest = _vessel(a.name)
        print(f"Copying {a.model} to {dest} (checked against Ollama's checksum)...")
        meta = workshop.create(a.model, dest, verify=not a.no_verify, progress=_bar)
        print()
        return {"vessel": dest, **meta, "next": f"athanor ollama {a.name} athanor-{a.name}"}
    v = _vessel(a.vessel)
    if a.cmd == "values":
        return edits.values(v, a.tensor, a.expert)
    if a.cmd == "bias":
        return edits.router_bias(v, a.layer, a.expert, add=a.add, set_to=a.set, off=a.off)
    if a.cmd == "off":
        return edits.experts_off(v, _experts(a.spec))
    if a.cmd == "scale":
        return edits.scale(v, a.tensor, a.factor, a.expert)
    if a.cmd == "journal":
        rows = workshop.journal(v)
        return "\n".join(f"{'undone' if r['undone'] else 'active':>6}  #{r['id']}  {r['time']}  {r['what']}" for r in rows) \
            or "No changes: the vessel is as copied."
    if a.cmd == "undo":
        done = workshop.undo(v, a.which)
        return f"Undone: {', '.join('#' + str(i) for i in done)}" if done else "Nothing to undo."
    if a.cmd == "pristine":
        ok = workshop.pristine(v, progress=_bar)
        print()
        return "Byte-for-byte the original." if ok else "Differs from the original."
    if a.cmd == "ollama":
        with open(os.path.join(workshop.check_vessel(v), "vessel.json"), encoding="utf-8") as fh:
            original = a.original or json.load(fh)["source"]
        print(f"Creating Ollama model {a.name} from {v} (Ollama imports a copy; this takes a minute)...")
        return ollama.create(v, a.name, original)


if __name__ == "__main__":
    sys.exit(main())
