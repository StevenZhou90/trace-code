"""Export a built dataset as prompt and answer files for fine-tuning and generation.

    python3 -m stc.export --dataset DIR --out DIR

One example is one task: the prompt holds the ports, the timing rule and the visible trace table (the
public files only); the answer is the reference Verilog (module dut). Hidden tests never enter a prompt.
Ingested tasks are left out, since they have no independent model.

Files written to --out:
  train.jsonl, val.jsonl              {"task_id", "family", "prompt", "completion"}
  eval_<split>.jsonl                  {"task_id", "family", "prompt"} for split val and test
  eval_<split>_notrace.jsonl          control: the same prompt with the trace removed
  eval_<split>_wrongtrace.jsonl       control: the trace of another design group with the same ports
                                      (tasks with no such partner are left out of this file)
  manifest.json                       counts and prompt sizes
"""
import argparse
import json
import os
import random
import sys

from .families import FAMILIES
from .show import table

INSTRUCTION = "Write a synthesizable Verilog module named dut that reproduces the behavior shown in the trace."
TRACE_NOTE = ('Trace: one row per cycle. Inputs are left of "|", outputs are right of it. Values are unsigned '
              'integers; x means the output is unknown.')
NO_TRACE = "No trace is given for this task."
ANSWER_RULE = "Answer with only the Verilog code."


def port_lines(iface):
    out = []
    for p in iface["ports"]:
        rng = "[%d:0] " % (p["width"] - 1) if p["width"] > 1 else ""
        out.append("  %-6s %s%s" % (p["dir"], rng, p["name"]))
    return "\n".join(out)


def prompt(iface, trace):
    parts = [INSTRUCTION, "Ports, in declaration order:\n" + port_lines(iface), "Timing: " + iface["timing"]]
    parts.append(TRACE_NOTE + "\n" + table(trace).rstrip() if trace else NO_TRACE)
    parts.append(ANSWER_RULE)
    return "\n\n".join(parts)


def load(dataset, rec, name):
    with open(os.path.join(dataset, rec["public_dir"], name)) as f:
        return json.load(f)


def write_jsonl(path, rows):
    with open(path, "w") as f:
        f.writelines(json.dumps(r, sort_keys=True) + "\n" for r in rows)
    return len(rows)


def export(dataset, out):
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(dataset, "records.jsonl")) as f:
        records = [json.loads(l) for l in f if json.loads(l)["family"] in FAMILIES]
    ports_key = lambda rec: json.dumps(rec["interface"]["ports"], sort_keys=True)
    by_ports = {}
    for rec in records:
        by_ports.setdefault(ports_key(rec), []).append(rec)

    counts, sizes = {}, []
    for split in ("train", "val", "test"):
        recs = [r for r in records if r["split"] == split]
        if split in ("train", "val"):
            rows = []
            for rec in recs:
                with open(os.path.join(dataset, rec["reference_rtl_path"])) as f:
                    ref = f.read()
                p = prompt(load(dataset, rec, "interface.json"), load(dataset, rec, "trace.json"))
                sizes.append(len(p) + len(ref))
                rows.append({"task_id": rec["task_id"], "family": rec["family"], "prompt": p, "completion": ref})
            counts[split] = write_jsonl(os.path.join(out, split + ".jsonl"), rows)
        if split == "train":
            continue
        plain, notrace, wrong = [], [], []
        for rec in recs:
            iface = load(dataset, rec, "interface.json")
            base = {"task_id": rec["task_id"], "family": rec["family"]}
            plain.append(dict(base, prompt=prompt(iface, load(dataset, rec, "trace.json"))))
            notrace.append(dict(base, prompt=prompt(iface, None)))
            # Same ports, different design: only the behavior in the trace is wrong. Fixed choice per task.
            partners = sorted((r for r in by_ports[ports_key(rec)] if r["design_group"] != rec["design_group"]),
                              key=lambda r: r["task_id"])
            if partners:
                other = random.Random(rec["task_id"]).choice(partners)
                wrong.append(dict(base, prompt=prompt(iface, load(dataset, other, "trace.json")),
                                  trace_from=other["task_id"]))
        counts["eval_" + split] = write_jsonl(os.path.join(out, "eval_%s.jsonl" % split), plain)
        counts["eval_%s_notrace" % split] = write_jsonl(os.path.join(out, "eval_%s_notrace.jsonl" % split), notrace)
        counts["eval_%s_wrongtrace" % split] = write_jsonl(os.path.join(out, "eval_%s_wrongtrace.jsonl" % split), wrong)

    groups = {s: sorted({r["design_group"] for r in records if r["split"] == s}) for s in ("train", "val", "test")}
    sizes.sort()
    manifest = {"dataset": os.path.abspath(dataset), "files": counts,
                "design_groups": {s: len(g) for s, g in groups.items()},
                "families_by_split": {s: sorted({r["family"] for r in records if r["split"] == s})
                                      for s in ("train", "val", "test")},
                "train_val_example_chars": {"median": sizes[len(sizes) // 2], "max": sizes[-1]}}
    with open(os.path.join(out, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
        f.write("\n")
    return manifest


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    print(json.dumps(export(a.dataset, a.out), indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
