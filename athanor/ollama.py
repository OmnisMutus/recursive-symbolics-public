"""Load a vessel into Ollama as its own model (e.g. 'athanor-gptoss'), so it can be tested like any other model.

The variant keeps everything Ollama knows about the original model (chat template, tool-call parser, parameters)
by taking `ollama show --modelfile ORIGINAL` and changing only the FROM line to the vessel. Note: `ollama create`
imports a copy of the file, so after every change to the vessel it has to be created again."""
import os
import re
import shutil
import subprocess


def modelfile_for(original_modelfile, vessel_path, params=None):
    """The original Modelfile with its FROM line pointing at the vessel (and optional PARAMETER lines)."""
    lines, done = [], False
    for line in original_modelfile.splitlines():
        if re.match(r"^\s*FROM\s+", line, re.I):
            if not done:
                lines.append(f"FROM {os.path.abspath(vessel_path)}")
                done = True
            continue
        if params and re.match(r"^\s*PARAMETER\s+(\S+)", line, re.I) and \
                re.match(r"^\s*PARAMETER\s+(\S+)", line, re.I).group(1) in params:
            continue
        lines.append(line)
    if not done:
        raise ValueError("The original Modelfile has no FROM line.")
    for k, v in (params or {}).items():
        lines.append(f"PARAMETER {k} {v}")
    return "\n".join(lines) + "\n"


def _ollama():
    exe = shutil.which("ollama")
    if not exe:
        raise FileNotFoundError("The ollama command isn't on PATH. Is Ollama installed?")
    return exe


def create(vessel_path, name, original, params=None, run=subprocess.run):
    show = run([_ollama(), "show", "--modelfile", original], capture_output=True, text=True, encoding="utf-8")
    if show.returncode != 0:
        raise RuntimeError(f"ollama show failed: {show.stderr.strip()}")
    mf = modelfile_for(show.stdout, vessel_path, params)
    path = os.path.splitext(os.path.abspath(vessel_path))[0] + ".Modelfile"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(mf)
    made = run([_ollama(), "create", name, "-f", path], capture_output=True, text=True, encoding="utf-8")
    if made.returncode != 0:
        raise RuntimeError(f"ollama create failed: {made.stderr.strip() or made.stdout.strip()}")
    return {"model": name, "modelfile": path, "test_with": f"ollama run {name}"}
