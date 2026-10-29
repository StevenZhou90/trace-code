"""One-off: grade candidates for the VerilogEval waveform-only problems with our own tests.

    python3 ve_check.py TASKS_JSON samples.jsonl [more.jsonl ...]

The problems (prompt waveforms) come from VerilogEval; their testbenches are not run. Each reference
is rewritten here as a Python model from the problem's reference design, and graded on our own
stimulus: every input combination plus 400 random rows for the combinational ones, 400 random rows for
the clocked ones. These circuits have no reset, so a clocked output counts only once the model's state
is determined by the inputs seen. The pick per task is the most frequent distinct candidate that
reproduces the visible waveform; the first sample is also graded.
"""
import itertools
import json
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))  # repository root
from stc import sim  # noqa: E402

COMB = {
    "Prob083_mt2015_q4b": lambda r: [1 - (r["x"] ^ r["y"])],
    "Prob090_circuit1": lambda r: [r["a"] & r["b"]],
    "Prob103_circuit2": lambda r: [(1 - r["a"]) ^ r["b"] ^ r["c"] ^ r["d"]],
    "Prob102_circuit3": lambda r: [(r["a"] | r["b"]) & (r["c"] | r["d"])],
    "Prob101_circuit4": lambda r: [r["c"] | r["b"]],
    "Prob130_circuit5": lambda r: [{0: r["b"], 1: r["e"], 2: r["a"], 3: r["d"]}.get(r["c"], 15)],
    "Prob126_circuit6": lambda r: [[4658, 44768, 10196, 23054, 8294, 25806, 50470, 12057][r["a"]]],
}


def seq(tid, rows):
    """Expected outputs per row (None while the state is unknown) for the clocked problems."""
    out, s = [], None
    for r in rows:
        if tid == "Prob098_circuit7":
            out.append([s])
            s = 1 - r["a"]
        elif tid == "Prob117_circuit9":
            out.append([s])
            s = 4 if r["a"] else (None if s is None else (0 if s == 6 else s + 1))
        elif tid == "Prob147_circuit10":
            out.append([None if s is None else r["a"] ^ r["b"] ^ s, s])
            if r["a"] == r["b"]:
                s = r["a"]
            elif s is not None:
                s = int(r["a"] + r["b"] + s >= 2)
    return out


def tests(tid, iface, rng):
    ins = [p for p in iface["ports"] if p["dir"] == "input" and p["name"] != iface["clock"]]
    rows = []
    if tid in COMB:
        if sum(p["width"] for p in ins) <= 12:
            rows = [dict(zip([p["name"] for p in ins], v))
                    for v in itertools.product(*[range(1 << p["width"]) for p in ins])]
    rows += [{p["name"]: rng.randrange(1 << p["width"]) for p in ins} for _ in range(400)]
    return rows, ([COMB[tid](r) for r in rows] if tid in COMB else seq(tid, rows))


def main():
    tasks_path, *files = sys.argv[1:]
    tasks = json.load(open(tasks_path))
    cands = {}
    for path in files:
        for l in open(path):
            c = json.loads(l)
            cands.setdefault(c["task_id"], []).append(c.get("verilog") or "")
    first_n = pick_n = 0
    for tid in sorted(tasks):
        t = tasks[tid]
        rows, expected = tests(tid, t["interface"], random.Random(tid))
        ok = lambda text: bool(text.strip()) and sim.simulate(t["interface"], text, rows, expected)["status"] == "pass"
        cs = cands.get(tid, [""])
        counts = {}
        for text in cs:
            if text.strip():
                counts[text] = counts.get(text, 0) + 1
        fits = [x for x in counts if sim.simulate(t["interface"], x, t["rows"], t["expected"])["status"] == "pass"]
        pick = max(fits or counts or [""], key=lambda x: counts.get(x, 0))
        f, p = ok(cs[0]), ok(pick)
        first_n += f
        pick_n += p
        print("%-22s samples %3d  fit %3d  first %s  picked %s" % (tid, len(cs), len(fits), "pass" if f else "fail",
                                                                   "pass" if p else "fail"))
    print("first sample %d/%d   picked %d/%d" % (first_n, len(tasks), pick_n, len(tasks)))


if __name__ == "__main__":
    main()
