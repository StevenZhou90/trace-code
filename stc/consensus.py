"""Pick one candidate per task by behavioral vote among the candidates that fit the visible trace.

    python3 -m stc.consensus --dataset DIR --samples samples.jsonl --out picked.jsonl [--level A|B|C] [--probe 256]

A visible trace often leaves part of the behavior open, so several different designs reproduce it.
Picking the first consistent sample is then a coin toss. Here every distinct candidate is simulated on
the visible stimulus followed by --probe extra rows of random inputs. The candidates that reproduce the
visible outputs are grouped by their outputs on the extra rows, so candidates that behave the same land
in one group even when their code differs. Each candidate votes with its "votes" field (default 1: one
sample), and the pick is the most voted candidate of the most voted group.

The extra inputs use only the public trace: each input bit is 1 with the frequency it has in the visible
stimulus, independently, so a rarely asserted pin such as a reset stays rare. Nothing about which pin is
which is used, so this is fair at every level. Hidden tests are never used; grade with stc.score.
If no candidate fits the visible trace, the pick is the one with the fewest mismatching rows.
"""
import argparse
import hashlib
import json
import os
import random
import sys
from concurrent.futures import ProcessPoolExecutor

from . import blind, sim
from .verify import visible


def probe_rows(iface, rows, n, seed):
    """n random input rows; every input bit is 1 with its frequency in the visible rows."""
    rng = random.Random(seed)
    ins = [p for p in iface["ports"] if p["dir"] == "input" and p["name"] in rows[0]]
    freq = {(p["name"], b): sum((r[p["name"]] >> b) & 1 for r in rows) / len(rows)
            for p in ins for b in range(p["width"])}
    return [{p["name"]: sum(int(rng.random() < freq[(p["name"], b)]) << b for b in range(p["width"]))
             for p in ins} for _ in range(n)]


def run(job):
    iface, text, rows, expected = job
    if not text.strip():
        return None
    res = sim.simulate(iface, text, rows, None)
    if res["status"] != "pass" or res["outputs"] is None:
        return None
    seen = res["outputs"][:len(expected)]
    wrong = sum(1 for e, a in zip(expected, seen) if any(x is not None and x != y for x, y in zip(e, a)))
    return wrong, json.dumps(res["outputs"][len(expected):])


def pick(dataset, samples, level="A", probe=256, jobs=os.cpu_count()):
    with open(os.path.join(dataset, "records.jsonl")) as f:
        records = {r["task_id"]: r for r in map(json.loads, f)}
    cands = {}  # (task, hash) -> [votes, wrapped text, original line]
    with open(samples) as f:
        for c in map(json.loads, f):
            rec, text = records[c["task_id"]], c.get("verilog") or ""
            if level != "A" and text.strip():
                text = blind.wrap_candidate(rec["interface"], blind.make_view(rec["interface"], rec["task_id"], level),
                                            text)
            key = (c["task_id"], hashlib.sha256(text.encode()).hexdigest())
            entry = cands.setdefault(key, [0, text, c])
            entry[0] += c.get("votes", 1)
    stim = {}
    for tid in {t for t, _ in cands}:
        rows, expected = visible(dataset, records[tid])
        stim[tid] = (rows + probe_rows(records[tid]["interface"], rows, probe, tid), expected)
    keys = list(cands)
    work = [(records[t]["interface"], cands[(t, h)][1], *stim[t]) for t, h in keys]
    with ProcessPoolExecutor(jobs) as pool:
        results = dict(zip(keys, pool.map(run, work, chunksize=4)))

    picked, stats = [], {"tasks": 0, "with_consistent": 0, "distinct_candidates": len(keys), "groups": 0}
    for tid in sorted(stim):
        mine = [(cands[k][0], cands[k][2], results[k]) for k in keys if k[0] == tid]
        fits = [m for m in mine if m[2] is not None and m[2][0] == 0]
        stats["tasks"] += 1
        if fits:
            groups = {}
            for votes, c, (_, sig) in fits:
                g = groups.setdefault(sig, [0, []])
                g[0] += votes
                g[1].append((votes, c))
            weight, members = max(groups.values(), key=lambda g: g[0])
            best = max(members, key=lambda m: m[0])[1]
            stats["with_consistent"] += 1
            stats["groups"] += len(groups)
            picked.append(dict(best, consistent=True, group_votes=weight, total_votes=sum(g[0] for g in groups.values()),
                               behaviors=len(groups)))
        else:
            ran = [m for m in mine if m[2] is not None]
            best = min(ran, key=lambda m: (m[2][0], -m[0]))[1] if ran else mine[0][1]
            picked.append(dict(best, consistent=False))
    return picked, stats


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--samples", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--level", default="A", choices="ABC")
    ap.add_argument("--probe", type=int, default=256, help="extra random input rows for the behavioral vote")
    ap.add_argument("--jobs", type=int, default=os.cpu_count())
    a = ap.parse_args(argv)
    picked, stats = pick(a.dataset, a.samples, a.level, a.probe, a.jobs)
    with open(a.out, "w") as f:
        f.writelines(json.dumps(p) + "\n" for p in picked)
    print(json.dumps(stats))
    return 0


if __name__ == "__main__":
    sys.exit(main())
