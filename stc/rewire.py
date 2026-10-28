"""Fix the pin wiring of a level C candidate by search against the visible trace (public data only).

    python3 -m stc.rewire --dataset DIR --samples samples.jsonl --out picked.jsonl [--top 4] [--budget 800]

At level C (stc/blind.py) a candidate often has the right design but ties the anonymous pins to the
wrong bus bits. Its wiring is the lines that bind pins to internal signals:
    wire [3:0] d0 = {p07, p17, p08, p18};    wire rst = p03;    assign p00 = q[1];
The search keeps the design's structure and changes only its bindings and constants:
  1. Outputs. An output pin does not feed back into the design, and every output expression shows up
     on exactly one pin, so one simulation gives the value of every expression on every visible row.
     Each output pin is then matched to the expression that best equals its column.
  2. Inputs. Hill climbing over swaps of two input pins, keeping a swap when the visible mismatch
     count (after output matching) goes down, with random restarts, within a simulation budget.
  3. Constants. If the trace is still not reproduced, each decimal literal N'dV in the design body
     (a wrap limit, a reset value, a pattern state) is tried at other values, keeping improvements.
  4. State targets. In a state machine written with named states (localparam S0 = ..., S1 = ...),
     each state named on the right of a "?" (a next-state choice) is tried as each other state.
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

    def values(self, text):
        """{output pin: [value per visible row]}, or None if the design did not run."""
        self.sims += 1
        res = sim.simulate(self.iface, text, self.rows, None)
        if res["status"] != "pass" or res["outputs"] is None:
            return None
        order = [p["name"] for p in sim.outputs(self.iface)]
        return {n: [row[i] for row in res["outputs"]] for i, n in enumerate(order)}

    def column(self, pin):
        j = self.out_names.index(pin)
        return [r[j] for r in self.expected]


def match_outputs(task, lines, slots, pins, outs, out_expr):
    """(best expression per output pin, total mismatching cells) from one simulation, or None."""
    names = sorted(outs)
    vals = task.values(render(lines, slots, pins, outs, out_expr))
    if vals is None:
        return None
    exprs = [(out_expr[n], vals[n]) for n in names]  # every expression, as seen on its current pin
    others = [n for n in task.out_names if n not in outs]  # output pins the candidate does not drive
    cost = {}
    for n in names:
        want = task.column(n)
        for e, (_, got) in enumerate(exprs):
            cost[(n, e)] = sum(1 for w, g in zip(want, got) if w is not None and w != g)
    # Greedy matching on the cost table: cheapest (pin, expression) pairs first, each used once.
    best, used_p, used_e, total = {}, set(), set(), 0
    for (n, e), c in sorted(cost.items(), key=lambda kv: (kv[1], kv[0])):
        if n not in used_p and e not in used_e:
            best[n] = exprs[e][0]
            used_p.add(n)
            used_e.add(e)
            total += c
    for n in others:
        total += sum(1 for w, g in zip(task.column(n), vals[n]) if w is not None and w != g)
    return best, total


LITERAL = re.compile(r"\b(\d+)'d(\d+)\b")


def constant_search(task, lines, slots, pins, outs, out_expr, total, budget):
    """Try other values for each decimal literal outside the wiring lines; keep improvements."""
    wiring = {i for i, _ in slots} | set(outs.values())
    body = [i for i, l in enumerate(lines) if i not in wiring and not l.lstrip().startswith(("input", "output", "module"))]
    # A site is (line, index of the literal within the line), so earlier edits on the line do not shift it.
    sites = [(i, k, int(m.group(1)), int(m.group(2))) for i in body for k, m in enumerate(LITERAL.finditer(lines[i]))]
    for i, k, width, value in sites[:8]:
        if not total or task.sims >= budget or width > 10:
            break
        top = (1 << width) - 1
        tries = sorted(range(top + 1), key=lambda v: abs(v - value))[1:]  # nearest values first
        for v in tries:
            if task.sims >= budget:
                break
            line = lines[i]
            m = list(LITERAL.finditer(line))[k]
            trial_lines = lines[:]
            trial_lines[i] = line[:m.start()] + "%d'd%d" % (width, v) + line[m.end():]
            got = match_outputs(task, trial_lines, slots, pins, outs, out_expr)
            if got and got[1] < total:
                lines, (out_expr, total) = trial_lines, got
                if not total:
                    break
    return lines, out_expr, total


STATE_DECL = re.compile(r"\b([A-Za-z_]\w*)\s*=\s*\d+'[db]\d+")


def state_search(task, lines, slots, pins, outs, out_expr, total, budget):
    """Try every other declared state at each next-state choice; keep improvements, several passes."""
    names = sorted({n for l in lines if "localparam" in l for n in STATE_DECL.findall(l)})
    if len(names) < 2:
        return lines, out_expr, total
    word = re.compile(r"\b(%s)\b" % "|".join(map(re.escape, names)))
    improved = True
    while total and improved and task.sims < budget:
        improved = False
        sites = [(i, k) for i, l in enumerate(lines) if "?" in l and "localparam" not in l
                 for k, m in enumerate(word.finditer(l[l.index("?"):]))]
        for i, k in sites:
            if not total or task.sims >= budget:
                break
            line = lines[i]
            q = line.index("?")
            m = list(word.finditer(line[q:]))[k]
            for other in names:
                if other == m.group(1) or task.sims >= budget:
                    continue
                trial = lines[:]
                trial[i] = line[:q + m.start()] + other + line[q + m.end():]
                got = match_outputs(task, trial, slots, pins, outs, out_expr)
                if got and got[1] < total:
                    lines, (out_expr, total), improved = trial, got, True
                    break
    return lines, out_expr, total


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
                got = match_outputs(task, lines, slots, trial, outs, out_expr)
                if got and got[1] < total:
                    pins, (out_expr, total), improved = trial, got, True
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
    if total:  # wiring alone did not reproduce the trace: search the design's constants, then rewire
        lines, out_expr, total = constant_search(task, lines, slots, pins, outs, out_expr, total, budget * 2)
        lines, out_expr, total = state_search(task, lines, slots, pins, outs, out_expr, total, budget * 3)
        if total and task.sims < budget * 3:
            pins, out_expr, total = climb(pins, out_expr, total)
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
