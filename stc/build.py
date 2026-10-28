"""Build a dataset: synthetic tasks for all five families plus ingested local modules.

    python3 -m stc.build --out DIR [--seed N] [--small] [--wide] [--variants N] [--ingest fixtures/ingest]

--wide adds each family's WIDE groups (more parameter values and structural options) for training
data. The original groups keep their names, so they keep their splits.

Layout under DIR (all paths in records are relative to DIR):
  public/<task>/interface.json, trace.json   model input: interface + observed trace
  target/<task>/reference.v                  training target (reference RTL, module renamed to dut)
  private/<task>/hidden.json                 grader only: hidden stimulus and expected outputs
  logs/<task>/reference.log                  reference compile/simulation log (bounded)
  records.jsonl  rejects.jsonl  summary.json
"""
import argparse
import json
import os
import random
import sys

from . import GENERATOR_VERSION, dedup, ingest, sim
from .families import FAMILIES
from .models import MODELS

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_INGEST = os.path.join(HERE, "fixtures", "ingest")
HIDDEN_RANDOM_ROWS = 200
TIMING = ("Row k: inputs are applied at the falling clock edge, outputs are sampled 1 time unit before the "
          "next rising edge, then the rising edge updates state. So outputs in row k depend on the state "
          "before that edge and on the inputs of row k. Values are unsigned integers of the port width; "
          "\"x\" marks an output with an unknown bit.")
TIMING_NO_CLOCK = "This block has no clock: row k is one input vector and the outputs it produces."
TIMING_RESET = {True: "Reset rst is synchronous, active high, and wins over every other input.",
                "not checked": "Reset rst is active high; whether it is synchronous was not checked."}


def write_json(path, obj, indent=1):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=indent, sort_keys=True)
        f.write("\n")


def write_trace(path, tr):
    """Trace JSON with one row per line, so it can be read by hand."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write('{"signals": [\n')
        f.write(",\n".join("  " + json.dumps(s, sort_keys=True) for s in tr["signals"]))
        f.write('\n],\n"rows": [\n')
        f.write(",\n".join("  " + json.dumps(r) for r in tr["rows"]))
        f.write("\n]}\n")


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def interface_for(ports, synchronous):
    names = {p["name"] for p in ports}
    timing = TIMING if "clk" in names else TIMING_NO_CLOCK
    if "rst" in names:
        timing += " " + TIMING_RESET[synchronous]
    return {"module": "dut", "ports": ports, "clock": "clk" if "clk" in names else None,
            "reset": {"name": "rst", "active": "high", "synchronous": synchronous} if "rst" in names else None,
            "timing": timing}


def trace(iface, rows, outs):
    ins, ous = sim.stim_inputs(iface), sim.outputs(iface)
    return {"signals": [dict(p) for p in ins + ous],
            "rows": [[r[p["name"]] for p in ins] + list(o) for r, o in zip(rows, outs)]}


def generic_rows(iface, rng, n):
    """Random stimulus for ingested modules: rst high for 2 rows, then rarely; other inputs uniform."""
    rows = []
    for k in range(n):
        row = {}
        for p in sim.stim_inputs(iface):
            if p["name"] == "rst":
                row["rst"] = 1 if k < 2 else int(rng.random() < 0.05)
            else:
                row[p["name"]] = rng.randrange(1 << p["width"])
        rows.append(row)
    return rows


def make_task(out, base, version):
    """Simulate the reference on visible and hidden stimulus, write the files, return the record or a reject.
    base: task_id, family, params, design_group, split, seed, iface, ref, origin, license, source text,
    visible, hidden, model (expected-row function or None)."""
    tid, iface = base["task_id"], base["iface"]
    vis = sim.simulate(iface, base["ref"], base["visible"], base["model"](base["visible"]) if base["model"] else None)
    hid_expected = base["model"](base["hidden"]) if base["model"] else None
    hid = sim.simulate(iface, base["ref"], base["hidden"], hid_expected)
    log = "== visible: %s\n%s\n== hidden: %s\n%s" % (vis["status"], vis["log"], hid["status"], hid["log"])
    write_text(os.path.join(out, "logs", tid, "reference.log"), log)
    if vis["status"] != "pass" or hid["status"] != "pass":
        return None, {"task_id": tid, "file": base.get("file"), "reason": "reference_%s_%s" % (vis["status"], hid["status"]),
                      "mismatches": (vis["mismatches"] + hid["mismatches"])[:5]}
    if hid_expected is None:  # ingested: the reference itself is the oracle; its x outputs are don't-care
        hid_expected = [[None if v == "x" else v for v in row] for row in hid["outputs"]]
    write_json(os.path.join(out, "public", tid, "interface.json"), iface)
    write_trace(os.path.join(out, "public", tid, "trace.json"), trace(iface, base["visible"], vis["outputs"]))
    write_text(os.path.join(out, "target", tid, "reference.v"), base["ref"])
    write_json(os.path.join(out, "private", tid, "hidden.json"),
               {"task_id": tid, "stimulus": base["hidden"], "expected": hid_expected,
                "corner_rows": base["corner_rows"], "random_rows": len(base["hidden"]) - base["corner_rows"]},
               indent=None)
    src = base["source"]
    record = {
        "task_id": tid, "family": base["family"], "origin": base["origin"], "license": base["license"],
        "source_sha256": dedup.sha256(src), "norm_sha256": dedup.sha256(dedup.normalize(src)),
        "generator_version": GENERATOR_VERSION, "params": base["params"], "seed": base["seed"],
        "design_group": base["design_group"], "split": base["split"], "interface": iface,
        "public_dir": "public/%s" % tid, "public_trace_path": "public/%s/trace.json" % tid,
        "reference_rtl_path": "target/%s/reference.v" % tid, "private_tests_path": "private/%s/hidden.json" % tid,
        "reference_log_path": "logs/%s/reference.log" % tid,
        "simulator": "icarus", "simulator_version": version,
        "reference_status": {"visible": vis["status"], "hidden": hid["status"]},
        "model_check_status": "agree" if base["model"] else "none",
        "visible_rows": len(base["visible"]), "hidden_rows": len(base["hidden"]),
    }
    return record, None


def build(out, seed=0, small=False, ingest_dir=DEFAULT_INGEST, wide=False, variants=None):
    if os.path.exists(out) and os.listdir(out):
        raise SystemExit("output folder %s is not empty" % out)
    version = sim.simulator_version()
    seen = dedup.Seen()
    variants = variants or (1 if small else 3)

    # 1. Design groups and their splits come first, before any seed variant exists.
    groups = []
    for fname, fam in FAMILIES.items():
        for p in fam.GROUPS + (fam.WIDE if wide else []):
            gid = "%s:%s" % (fname, json.dumps(p, sort_keys=True))
            dup = seen.check(fam.rtl(p), "synthetic/" + gid)
            assert dup is None, dup
            groups.append((fname, fam, p, gid, dedup.split_for(gid)))
    accepted, rejects = ingest.ingest(ingest_dir, seen) if ingest_dir else ([], [])

    # 2. Variants: same design, different visible and hidden stimulus seeds. They share the group's split.
    bases = []
    for fname, fam, p, gid, split in groups:
        for v in range(variants):
            tseed = int(dedup.sha256("%d:%s:%d" % (seed, gid, v))[:12], 16)
            vis = fam.random_rows(p, random.Random("%d:visible" % tseed), fam.visible_len(p))
            corners = fam.corners(p)
            hid = corners + fam.random_rows(p, random.Random("%d:hidden" % tseed), HIDDEN_RANDOM_ROWS)
            ref = fam.rtl(p)
            bases.append({"task_id": "t" + dedup.sha256("task:%d:%s:%d" % (seed, gid, v))[:10], "family": fname,
                          "params": p, "design_group": gid, "split": split, "seed": tseed,
                          "iface": interface_for(fam.ports(p), True), "ref": ref, "source": ref,
                          "origin": "synthetic", "license": "project-owned", "visible": vis, "hidden": hid,
                          "corner_rows": len(corners),
                          "model": (lambda rows, m=MODELS[fname], p=p: m(p, rows))})
    for item in accepted:
        gid = "ingest:" + dedup.sha256(dedup.normalize(item["text"]))[:16]
        tseed = int(dedup.sha256("%d:%s" % (seed, gid))[:12], 16)
        iface = interface_for(item["interface"]["ports"], "not checked")
        zeros = {p["name"]: 0 for p in sim.stim_inputs(iface)}
        ones = {p["name"]: (1 << p["width"]) - 1 for p in sim.stim_inputs(iface)}
        if iface["reset"]:  # reset first, then all-zero and all-one inputs with reset low
            ones["rst"] = 0
            hidden_corners = [dict(zeros, rst=1)] * 2 + [zeros] * 4 + [ones] * 4
        else:
            hidden_corners = [zeros] * 4 + [ones] * 4
        hid = hidden_corners + generic_rows(iface, random.Random("%d:hidden" % tseed), HIDDEN_RANDOM_ROWS)
        bases.append({"task_id": "t" + dedup.sha256("task:%d:%s" % (seed, gid))[:10], "family": "ingested",
                      "params": {}, "design_group": gid, "split": dedup.split_for(gid), "seed": tseed,
                      "iface": iface, "ref": ingest.rename_module(item["text"]), "source": item["text"],
                      "origin": item["origin"] + ": " + item["file"], "license": item["license"], "file": item["file"],
                      "visible": generic_rows(iface, random.Random("%d:visible" % tseed), 96), "hidden": hid,
                      "corner_rows": len(hidden_corners), "model": None})

    # 3. Simulate and write. Exact duplicate tasks (same reference and same visible trace) are dropped.
    records, seen_tasks = [], set()
    for base in bases:
        rec, rej = make_task(out, base, version)
        if rej:
            rejects.append(rej)
            continue
        with open(os.path.join(out, rec["public_trace_path"])) as f:
            key = (rec["norm_sha256"], dedup.sha256(f.read()))
        if key in seen_tasks:
            rejects.append({"task_id": rec["task_id"], "design_group": rec["design_group"], "reason": "duplicate_task"})
            continue
        seen_tasks.add(key)
        records.append(rec)

    with open(os.path.join(out, "records.jsonl"), "w") as f:
        f.writelines(json.dumps(r, sort_keys=True) + "\n" for r in records)
    with open(os.path.join(out, "rejects.jsonl"), "w") as f:
        f.writelines(json.dumps(r, sort_keys=True) + "\n" for r in rejects)
    counts = {}
    for r in records:
        c = counts.setdefault(r["family"], {"tasks": 0, "groups": set(), "train": 0, "val": 0, "test": 0})
        c["tasks"] += 1
        c["groups"].add(r["design_group"])
        c[r["split"]] += 1
    for c in counts.values():
        c["groups"] = len(c["groups"])
    summary = {"seed": seed, "small": small, "variants_per_group": variants, "generator_version": GENERATOR_VERSION,
               **({"wide": True} if wide else {}),
               "simulator_version": version, "tasks": len(records), "rejects": len(rejects), "by_family": counts}
    write_json(os.path.join(out, "summary.json"), summary)
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--small", action="store_true", help="one seed variant per design group")
    ap.add_argument("--wide", action="store_true", help="add the wide training groups of every family")
    ap.add_argument("--variants", type=int, help="seed variants per design group (default 3, or 1 with --small)")
    ap.add_argument("--ingest", default=DEFAULT_INGEST, help="folder with .v files and SOURCES.json ('' to skip)")
    a = ap.parse_args(argv)
    s = build(a.out, a.seed, a.small, a.ingest, a.wide, a.variants)
    print(json.dumps(s, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
