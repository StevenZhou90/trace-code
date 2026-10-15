"""Evaluate a candidate Verilog file on one task's hidden tests.

    python3 -m stc.evaluate --dataset DIR --task TASK_ID --candidate FILE.v [--timeout S] [--report OUT.json]

Prints a JSON report and exits 0 only on status "pass". The candidate must define module dut with the
task's exact ports. Statuses: pass, fail, compile_error, interface_error, sim_error, timeout, rejected.
"""
import argparse
import json
import os
import sys

from . import sim
from .models import check_stream


def load_record(dataset, task_id):
    with open(os.path.join(dataset, "records.jsonl")) as f:
        for line in f:
            rec = json.loads(line)
            if rec["task_id"] == task_id:
                return rec
    raise SystemExit("task %s not in %s/records.jsonl" % (task_id, dataset))


def evaluate(dataset, rec, text, timeout=sim.DEFAULT_TIMEOUT):
    with open(os.path.join(dataset, rec["private_tests_path"])) as f:
        hidden = json.load(f)
    res = sim.simulate(rec["interface"], text, hidden["stimulus"], hidden["expected"], timeout)
    report = {"task_id": rec["task_id"], "status": res["status"], "stage": res["stage"],
              "hidden_rows": len(hidden["stimulus"]), "failing_rows": res["failing_rows"],
              "mismatches": res["mismatches"], "problems": res["problems"], "log": res["log"]}
    if rec["family"] == "handshake" and res["outputs"] is not None:
        report["protocol_problems"] = check_stream(hidden["stimulus"], res["outputs"])
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--task", required=True)
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--timeout", type=float, default=sim.DEFAULT_TIMEOUT)
    ap.add_argument("--report")
    a = ap.parse_args(argv)
    with open(a.candidate) as f:
        text = f.read()
    report = evaluate(a.dataset, load_record(a.dataset, a.task), text, a.timeout)
    out = json.dumps(report, indent=1, sort_keys=True)
    if a.report:
        with open(a.report, "w") as f:
            f.write(out + "\n")
    print(out)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
