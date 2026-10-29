"""One-off: paired comparison of two systems on the same tasks (exact two-sided McNemar test)."""
import json, os, sys
from math import comb
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scores") + "/"  # reports/lora/scores
def passes(files):
    out = {}
    for f in files.split(","):
        for t in json.load(open(R + f))["tasks"]:
            out[t["task_id"]] = t["status"] == "pass"
    return out
def mcnemar(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)
for line in sys.argv[1:]:
    name, a, o = line.split("|")
    A, O = passes(a), passes(o)
    ids = sorted(set(A) & set(O))
    b = sum(A[i] and not O[i] for i in ids)
    c = sum(O[i] and not A[i] for i in ids)
    print("%-34s ours %d/%d (%.1f%%)  frontier %d/%d (%.1f%%)  ours-only %d  frontier-only %d  p=%.2g" % (
        name, sum(A[i] for i in ids), len(ids), 100 * sum(A[i] for i in ids) / len(ids),
        sum(O[i] for i in ids), len(ids), 100 * sum(O[i] for i in ids) / len(ids), b, c, mcnemar(b, c)))
