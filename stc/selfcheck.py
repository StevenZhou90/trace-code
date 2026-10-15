"""Check the testbenches themselves: references must pass, deliberate bugs must fail, and broken
candidates must get the right failure status.

    python3 -m stc.selfcheck --dataset DIR [--out DIR/selfcheck.json]

For every synthetic task: the reference (expect pass) and every bug from the family (expect fail). Each bug is also run on the visible trace stimulus alone, to show how many bugs the
public trace would have missed without the hidden corner cases (reported, not an expectation). For the first task of every family, six broken candidates made from the reference:
syntax error, renamed port, runtime $fatal, early $finish, endless loop, forbidden system task.
Exits 0 only if every result matched its expectation.
"""
import argparse
import json
import os
import re
import sys

from . import sim
from .evaluate import evaluate
from .families import FAMILIES
from .models import MODELS

BROKEN_TIMEOUT = 3.0  # the endless-loop candidate is killed after this many seconds


def broken_candidates(ref, iface):
    """(name, expected status, text). Each is the reference with one deliberate defect."""
    out_name = sim.outputs(iface)[0]["name"]
    end = ref.rindex("endmodule")
    add = lambda code: ref[:end] + code + "\n" + ref[end:]
    return [
        ("syntax_error", "compile_error", ref[:end] + "endmodul\n"),
        ("renamed_port", "interface_error", re.sub(r"\b%s\b" % out_name, out_name + "_o", ref)),
        ("runtime_fatal", "sim_error", add('    initial #3 $fatal(1, "deliberate runtime error");')),
        ("early_finish", "sim_error", add("    initial #25 $finish;")),
        ("endless_loop", "timeout", add("    initial begin : spin integer i; i = 0; while (1) i = i + 1; end")),
        ("forbidden_task", "rejected", add('    initial $system("echo should never run");')),
    ]


def selfcheck(dataset):
    with open(os.path.join(dataset, "records.jsonl")) as f:
        records = [json.loads(l) for l in f]
    synthetic = [r for r in records if r["family"] in FAMILIES]
    first_of_family = {}
    for r in synthetic:
        first_of_family.setdefault(r["family"], r)
    results = []

    def visible_status(rec, text):
        with open(os.path.join(dataset, rec["public_trace_path"])) as f:
            tr = json.load(f)
        n_in = sum(1 for s in tr["signals"] if s["dir"] == "input")
        rows = [dict(zip([s["name"] for s in tr["signals"][:n_in]], r[:n_in])) for r in tr["rows"]]
        return sim.simulate(rec["interface"], text, rows, MODELS[rec["family"]](rec["params"], rows))["status"]

    def run(rec, kind, name, expected, text, timeout=sim.DEFAULT_TIMEOUT):
        rep = evaluate(dataset, rec, text, timeout)
        results.append({"visible_only_status": visible_status(rec, text) if kind == "mutant" else None,"family": rec["family"], "design_group": rec["design_group"], "task_id": rec["task_id"],
                        "kind": kind, "candidate": name, "expected": expected, "status": rep["status"],
                        "ok": rep["status"] == expected, "failing_rows": rep["failing_rows"],
                        "first_mismatch": rep["mismatches"][0] if rep["mismatches"] else None,
                        "problems": rep["problems"], "protocol_problems": rep.get("protocol_problems")})

    for rec in synthetic:
        fam = FAMILIES[rec["family"]]
        with open(os.path.join(dataset, rec["reference_rtl_path"])) as f:
            ref = f.read()
        run(rec, "reference", "reference", "pass", ref)
        for bug in fam.bugs(rec["params"]):
            run(rec, "mutant", bug, "fail", fam.rtl(rec["params"], bug))
    for fname, rec in first_of_family.items():
        with open(os.path.join(dataset, rec["reference_rtl_path"])) as f:
            ref = f.read()
        for name, expected, text in broken_candidates(ref, rec["interface"]):
            run(rec, "broken", name, expected, text, BROKEN_TIMEOUT if expected == "timeout" else sim.DEFAULT_TIMEOUT)

    summary = {}
    for r in results:
        s = summary.setdefault(r["family"], {"references_pass": 0, "references": 0, "mutants_killed": 0,
                                             "mutants": 0, "broken_classified": 0, "broken": 0,
                                             "mutants_caught_by_visible_trace_alone": 0})
        key = {"reference": ("references_pass", "references"), "mutant": ("mutants_killed", "mutants"),
               "broken": ("broken_classified", "broken")}[r["kind"]]
        s[key[1]] += 1
        s[key[0]] += int(r["ok"])
        s["mutants_caught_by_visible_trace_alone"] += int(r["visible_only_status"] == "fail")
    return {"simulator_version": sim.simulator_version(), "ok": all(r["ok"] for r in results),
            "summary": summary, "results": results}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    res = selfcheck(a.dataset)
    with open(a.out or os.path.join(a.dataset, "selfcheck.json"), "w") as f:
        json.dump(res, f, indent=1, sort_keys=True)
        f.write("\n")
    for fam, s in res["summary"].items():
        print("%-10s references %d/%d pass   mutants %d/%d fail (visible trace alone: %d)   broken candidates %d/%d "
              "classified" % (fam, s["references_pass"], s["references"], s["mutants_killed"], s["mutants"],
                              s["mutants_caught_by_visible_trace_alone"], s["broken_classified"], s["broken"]))
    for r in res["results"]:
        if not r["ok"]:
            print("UNEXPECTED", r["family"], r["candidate"], "expected", r["expected"], "got", r["status"])
    print("all expectations met" if res["ok"] else "SOME EXPECTATIONS FAILED")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
