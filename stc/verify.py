"""Pick one candidate per task by simulating samples on the task's visible trace (public data only).

    python3 -m stc.verify --dataset DIR --samples samples.jsonl --out picked.jsonl [--level A|B|C] [--k N]

samples.jsonl holds several {"task_id", "family", "sample", "verilog"} lines per task. Each distinct
candidate text is simulated on the visible stimulus of the public trace and compared with the visible
outputs ("x" outputs are don't-care). The pick is the lowest-numbered sample that reproduces the whole
visible trace; if none does, the one with the fewest mismatching rows. Hidden tests are never used, so
this is a fair test-time search; grade the picks afterwards with stc.score. --k uses only the first k
samples of each task, to measure how the result grows with the number of samples.
"""
import argparse
import hashlib
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

from . import blind, sim


def visible(dataset, rec):
    with open(os.path.join(dataset, rec["public_trace_path"])) as f:
        tr = json.load(f)
    n_in = sum(1 for s in tr["signals"] if s["dir"] == "input")
    names = [s["name"] for s in tr["signals"][:n_in]]
    rows = [dict(zip(names, r[:n_in])) for r in tr["rows"]]
    expected = [[None if v == "x" else v for v in r[n_in:]] for r in tr["rows"]]
    return rows, expected


def check(job):
    dataset, rec, text = job
    if not text.strip():
        return {"status": "compile_error", "failing_rows": None}
    rows, expected = visible(dataset, rec)
    res = sim.simulate(rec["interface"], text, rows, expected)
    return {"status": res["status"], "failing_rows": res["failing_rows"] if res["status"] in ("pass", "fail") else None}


def pick(dataset, samples, level="A", k=None, jobs=os.cpu_count()):
    with open(os.path.join(dataset, "records.jsonl")) as f:
        records = {r["task_id"]: r for r in map(json.loads, f)}
    with open(samples) as f:
        cands = [json.loads(l) for l in f if l.strip()]
    by_task = {}
    for c in cands:
        by_task.setdefault(c["task_id"], []).append(c)
    for tid in by_task:
        by_task[tid].sort(key=lambda c: c.get("sample", 0))
        by_task[tid] = by_task[tid][:k] if k else by_task[tid]

    def wrapped(c):
        rec, text = records[c["task_id"]], c.get("verilog") or ""
        if level != "A" and text.strip():
            text = blind.wrap_candidate(rec["interface"], blind.make_view(rec["interface"], rec["task_id"], level), text)
        return text

    jobs_by_key = {}
    for tid, cs in by_task.items():
        for c in cs:
            text = wrapped(c)
            jobs_by_key.setdefault((tid, hashlib.sha256(text.encode()).hexdigest()), (dataset, records[tid], text))
    keys = list(jobs_by_key)
    with ProcessPoolExecutor(jobs) as pool:
        results = dict(zip(keys, pool.map(check, [jobs_by_key[k] for k in keys], chunksize=8)))

    picked, stats = [], {"tasks": 0, "with_consistent_sample": 0, "distinct_candidates": len(keys)}
    for tid, cs in sorted(by_task.items()):
        scored = []
        for c in cs:
            r = results[(tid, hashlib.sha256(wrapped(c).encode()).hexdigest())]
            rank = 0 if r["status"] == "pass" else (1, r["failing_rows"]) if r["failing_rows"] is not None else (2,)
            scored.append(((rank,) if rank == 0 else rank, c.get("sample", 0), c, r))
        best = min(scored, key=lambda s: (s[0], s[1]))
        stats["tasks"] += 1
        stats["with_consistent_sample"] += int(best[3]["status"] == "pass")
        picked.append(dict(best[2], visible_status=best[3]["status"], samples_checked=len(cs),
                           consistent_samples=sum(1 for s in scored if s[3]["status"] == "pass")))
    return picked, stats


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--samples", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--level", default="A", choices="ABC")
    ap.add_argument("--k", type=int, default=None)
    ap.add_argument("--jobs", type=int, default=os.cpu_count())
    a = ap.parse_args(argv)
    picked, stats = pick(a.dataset, a.samples, a.level, a.k, a.jobs)
    with open(a.out, "w") as f:
        f.writelines(json.dumps(p) + "\n" for p in picked)
    print(json.dumps(stats))
    return 0


if __name__ == "__main__":
    sys.exit(main())
