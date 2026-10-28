"""Grade generated candidates on the hidden tests and summarize them.

    python3 -m stc.score --dataset DIR --candidates candidates.jsonl --out scores.json [--jobs N]

candidates.jsonl has one {"task_id", "family", "verilog"} per line (extra fields are ignored). Each
candidate is graded with stc.evaluate, the same harness as the self-check. "compiled" means the
candidate got past the compiler: its status is not compile_error or rejected. An empty answer counts
as compile_error. The summary is by split and family; a few failures are kept as examples.
"""
import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

from .evaluate import evaluate

NOT_COMPILED = ("compile_error", "rejected")
EXAMPLES = 8


def grade(job):
    dataset, rec, text = job
    if not text.strip():
        return {"task_id": rec["task_id"], "status": "compile_error", "problems": ["empty answer"],
                "failing_rows": 0, "hidden_rows": 0, "mismatches": [], "log": ""}
    return evaluate(dataset, rec, text)


def summarize(rows):
    out = {}
    for r in rows:
        for key in ("all", r["split"], "%s/%s" % (r["split"], r["family"])):
            s = out.setdefault(key, {"tasks": 0, "compiled": 0, "passed": 0, "statuses": {}})
            s["tasks"] += 1
            s["compiled"] += int(r["status"] not in NOT_COMPILED)
            s["passed"] += int(r["status"] == "pass")
            s["statuses"][r["status"]] = s["statuses"].get(r["status"], 0) + 1
    for s in out.values():
        s["compile_rate"] = round(s["compiled"] / s["tasks"], 4)
        s["pass_rate"] = round(s["passed"] / s["tasks"], 4)
    return dict(sorted(out.items()))


def score(dataset, candidates, jobs=os.cpu_count()):
    with open(os.path.join(dataset, "records.jsonl")) as f:
        records = {r["task_id"]: r for r in map(json.loads, f)}
    with open(candidates) as f:
        cands = [json.loads(l) for l in f if l.strip()]
    work = [(dataset, records[c["task_id"]], c.get("verilog") or "") for c in cands]
    with ProcessPoolExecutor(jobs) as pool:
        reports = list(pool.map(grade, work, chunksize=4))
    rows, examples = [], []
    for c, (_, rec, text), rep in zip(cands, work, reports):
        rows.append({"task_id": rec["task_id"], "family": rec["family"], "split": rec["split"],
                     "design_group": rec["design_group"], "status": rep["status"],
                     "failing_rows": rep["failing_rows"], "hidden_rows": rep["hidden_rows"]})
        if rep["status"] != "pass" and len(examples) < EXAMPLES:
            examples.append({"task_id": rec["task_id"], "family": rec["family"], "status": rep["status"],
                             "first_mismatch": rep["mismatches"][0] if rep["mismatches"] else None,
                             "problems": rep.get("problems"), "log": rep["log"][:1500], "verilog": text[:3000]})
    return {"candidates": os.path.abspath(candidates), "summary": summarize(rows), "tasks": rows,
            "failure_examples": examples}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--jobs", type=int, default=os.cpu_count())
    a = ap.parse_args(argv)
    res = score(a.dataset, a.candidates, a.jobs)
    with open(a.out, "w") as f:
        json.dump(res, f, indent=1, sort_keys=True)
        f.write("\n")
    for key, s in res["summary"].items():
        print("%-22s tasks %4d   compiled %5.1f%%   passed %5.1f%%" % (key, s["tasks"], 100 * s["compile_rate"],
                                                                   100 * s["pass_rate"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
