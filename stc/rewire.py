"""Fix the pin wiring of a level C candidate by search against the visible trace (public data only).

    python3 -m stc.rewire --dataset DIR --samples samples.jsonl --out picked.jsonl [--top 4] [--budget 800]

At level C (stc/blind.py) a candidate often has the right design but ties the anonymous pins to the
wrong bus bits. Its wiring is the lines that bind pins to internal signals:
    wire [3:0] d0 = {p07, p17, p08, p18};    wire rst = p03;    assign p00 = q[1];
The search keeps the design and changes only those bindings:
  1. Outputs. An output pin does not feed back into the design, so each output pin can be scored
     against each output expression on its own: n simulations with the expressions rotated over the
     n output pins give every (pin, expression) mismatch count; then pins are matched to expressions.
  2. Inputs. Hill climbing over swaps of two input pins, keeping a swap when the visible mismatch
     count goes down, within a simulation budget.
Two phases per task: every distinct sampled candidate gets a quick search (--screen simulations),
then the --top best of them get the full --budget. The pick per task is a candidate that reproduces the
whole visible trace, else the one with the fewest mismatching cells. Hidden tests are never used; grade the picks with stc.score --level C.
"""
import argparse
import hashlib
import json
import os
import random
import re
import sys
from concurrent.futures import ProcessPoolExecutor

from . import blind, sim
from .verify import visible

IN_LINE = re.compile(r"^(\s*wire\s*(?:\[[^\]]*\]\s*)?\w+\s*=\s*)(\{[^}]*\}|p\d+)(\s*;.*)$")
OUT_LINE = re.compile(r"^(\s*assign\s+)(p\d+)(\s*=\s*)([^;]+)(;.*)$")


def parse(text):
    """(lines, input slots [(line, position)], input pins per slot, output lines {pin: line}, exprs)."""
    lines = text.split("\n")
    slots, pins, outs = [], [], {}
    for i, line in enumerate(lines):
        m = IN_LINE.match(line)
        if m:
            names = re.findall(r"p\d+", m.group(2))
            for k, n in enumerate(names):
                slots.append((i, k))
                pins.append(n)
            continue
        m = OUT_LINE.match(line)
        if m:
            outs[m.group(2)] = i
    return lines, slots, pins, outs


def render(lines, slots, pins, outs, out_expr):
    """Text with input slot pins and output expressions replaced."""
    new = lines[:]
    by_line = {}
    for (i, k), p in zip(slots, pins):
        by_line.setdefault(i, {})[k] = p
    for i, repl in by_line.items():
        m = IN_LINE.match(lines[i])
        names = iter(repl[k] for k in sorted(repl))
        rhs = re.sub(r"p\d+", lambda _: next(names), m.group(2))
        new[i] = m.group(1) + rhs + m.group(3)
    for pin, i in outs.items():
        m = OUT_LINE.match(lines[i])
        new[i] = m.group(1) + pin + m.group(3) + out_expr[pin] + m.group(5)
    return "\n".join(new)


class Task:
    def __init__(self, dataset, rec):
        self.view = blind.make_view(rec["interface"], rec["task_id"], "C")
        self.iface = {"module": "dut", "ports": blind.view_ports(rec["interface"], self.view),
                      "clock": rec["interface"].get("clock")}
        rows, _ = visible(dataset, rec)
        with open(os.path.join(dataset, rec["public_trace_path"])) as f:
            vt = blind.view_trace(json.load(f), self.view)
        n_in = sum(1 for s in vt["signals"] if s["dir"] == "input")
        self.out_names = [s["name"] for s in vt["signals"][n_in:]]
        in_names = [s["name"] for s in vt["signals"][:n_in]]
        self.rows = [dict(zip(in_names, r[:n_in])) for r in vt["rows"]]
        self.expected = [[None if v == "x" else v for v in r[n_in:]] for r in vt["rows"]]
        self.sims = 0

    def run(self, text):
        """Per output pin: number of visible rows where it mismatches; None if the design did not run."""
        self.sims += 1
        res = sim.simulate(self.iface, text, self.rows, None)
        if res["status"] != "pass" or res["outputs"] is None:
            return None
        order = [p["name"] for p in sim.outputs(self.iface)]
        bad = {n: 0 for n in order}
        for exp, act in zip(self.expected, res["outputs"]):
            act = dict(zip(order, act))
            for n, e in zip(self.out_names, exp):
                if e is not None and act[n] != e:
                    bad[n] += 1
        return bad


def match_outputs(task, lines, slots, pins, outs, out_expr):
    """Best output expression per output pin, from len(outs) rotated simulations. None if a run fails."""
    names = sorted(outs)
    exprs = [out_expr[n] for n in names]  # by position: two pins may carry the same expression
    cost = {}
    for s in range(len(names)):
        trial = {n: exprs[(j + s) % len(names)] for j, n in enumerate(names)}
        bad = task.run(render(lines, slots, pins, outs, trial))
        if bad is None:
            return None
        for j, n in enumerate(names):
            cost[(n, (j + s) % len(names))] = bad[n]
    # Greedy matching on the cost table: cheapest (pin, expression) pairs first, each used once.
    best, used_p, used_e, total = {}, set(), set(), 0
    for (n, e), c in sorted(cost.items(), key=lambda kv: (kv[1], kv[0])):
        if n not in used_p and e not in used_e:
            best[n] = exprs[e]
            used_p.add(n)
            used_e.add(e)
            total += c
    return best, total


def repair(job):
    dataset, rec, text, budget, seed = job
    task = Task(dataset, rec)
    lines, slots, pins, outs = parse(text)
    outs = {p: i for p, i in outs.items() if p in task.out_names}  # ignore drives of pins that do not exist
    expr_of = {pin: OUT_LINE.match(lines[i]).group(4).strip() for pin, i in outs.items()}
    if not outs:
        return {"text": text, "mismatch": None, "sims": 0}
    got = match_outputs(task, lines, slots, pins, outs, expr_of)
    if got is None:
        return {"text": text, "mismatch": None, "sims": task.sims}
    out_expr, total = got
    rng = random.Random(seed)
    pairs = [(a, b) for a in range(len(pins)) for b in range(a + 1, len(pins))]

    def climb(pins, out_expr, total):
        improved = True
        while total and improved and task.sims < budget:
            improved = False
            rng.shuffle(pairs)
            for a, b in pairs:
                if task.sims >= budget:
                    break
                trial = pins[:]
                trial[a], trial[b] = trial[b], trial[a]
                bad = task.run(render(lines, slots, trial, outs, out_expr))
                if bad is None:
                    continue
                t = sum(bad.values())
                if t < total:
                    pins, total, improved = trial, t, True
                    regot = match_outputs(task, lines, slots, pins, outs, out_expr)
                    if regot:
                        out_expr, total = regot
                    if not total:
                        break
        return pins, out_expr, total

    best = climb(pins, out_expr, total)
    # Restarts: shake the best wiring with a few random swaps and climb again, keeping the best.
    while best[2] and pairs and task.sims < budget:
        start = best[0][:]
        for _ in range(rng.randint(2, 4)):
            a, b = rng.choice(pairs)
            start[a], start[b] = start[b], start[a]
        got = match_outputs(task, lines, slots, start, outs, best[1])
        if got is None:
            continue
        cand = climb(start, *got)
        if cand[2] < best[2]:
            best = cand
    pins, out_expr, total = best
    return {"text": render(lines, slots, pins, outs, out_expr), "mismatch": total, "sims": task.sims}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--samples", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--top", type=int, default=4, help="screened candidates per task that get the full budget")
    ap.add_argument("--budget", type=int, default=800, help="simulations per candidate in the full search")
    ap.add_argument("--screen", type=int, default=40, help="simulations per candidate in the quick screen")
    ap.add_argument("--k", type=int, default=None, help="use only the first k samples of each task")
    ap.add_argument("--jobs", type=int, default=os.cpu_count())
    a = ap.parse_args(argv)
    with open(os.path.join(a.dataset, "records.jsonl")) as f:
        records = {r["task_id"]: r for r in map(json.loads, f)}
    by_task = {}
    with open(a.samples) as f:
        for c in map(json.loads, f):
            by_task.setdefault(c["task_id"], []).append(c)
    groups = {}
    for tid, cs in sorted(by_task.items()):
        cs = sorted(cs, key=lambda c: c.get("sample", 0))[:a.k] if a.k else cs
        # Most frequent distinct candidates first: the model's own vote on the design.
        counts = {}
        for c in cs:
            text = c.get("verilog") or ""
            if text.strip():
                h = hashlib.sha256(text.encode()).hexdigest()
                counts.setdefault(h, [0, text])[0] += 1
        groups[tid] = (cs[0]["family"], sorted(counts.items(), key=lambda kv: -kv[1][0]))

    def run_phase(entries, budget):
        jobs = [(a.dataset, records[tid], text, budget, h) for tid, h, n, text in entries]
        with ProcessPoolExecutor(a.jobs) as pool:
            return list(pool.map(repair, jobs, chunksize=1))

    # Phase 1: quick screen of every distinct candidate. Phase 2: full search on the best few.
    entries = [(tid, h, n, text) for tid, (fam, cands) in groups.items() for h, (n, text) in cands]
    screened = run_phase(entries, a.screen)
    rank = lambda r, n: (r["mismatch"] is None, r["mismatch"] if r["mismatch"] is not None else 0, -n)
    finalists = []
    for tid in groups:
        mine = sorted((rank(r, e[2]), e, r) for e, r in zip(entries, screened) if e[0] == tid)
        finalists += [(e, r) for _, e, r in mine[:a.top]]
    full = run_phase([e for e, r in finalists if r["mismatch"]], a.budget)
    full = iter(full)
    owners, results = [], []
    for e, r in finalists:
        owners.append((e[0], groups[e[0]][0], e[2]))
        results.append(next(full) if r["mismatch"] else r)
    results_sims = sum(r["sims"] for r in screened)
    best = {}
    for (tid, fam, n), r in zip(owners, results):
        key = rank(r, n)
        if tid not in best or key < best[tid][0]:
            best[tid] = (key, {"task_id": tid, "family": fam, "verilog": r["text"],
                               "visible_mismatch": r["mismatch"], "sims": r["sims"]})
    with open(a.out, "w") as f:
        for tid in sorted(best):
            f.write(json.dumps(best[tid][1]) + "\n")
    picked = [b[1] for b in best.values()]
    print(json.dumps({"tasks": len(picked), "consistent": sum(p["visible_mismatch"] == 0 for p in picked),
                      "candidates": len(entries), "sims": results_sims + sum(r["sims"] for r in results)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
