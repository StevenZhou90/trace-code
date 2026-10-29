"""One-off: group-level comparison (mean pass per design group) with an exact two-sided sign test."""
import json, os, sys
from math import comb
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scores") + "/"  # reports/lora/scores
def by_group(f):
    g = {}
    for t in json.load(open(R + f))["tasks"]:
        g.setdefault(t["design_group"], []).append(t["status"] == "pass")
    return {k: sum(v) / len(v) for k, v in g.items()}
for line in sys.argv[1:]:
    name, a, o = line.split("|")
    A, O = by_group(a), by_group(o)
    ks = sorted(set(A) & set(O))
    w = sum(A[k] > O[k] for k in ks); l = sum(A[k] < O[k] for k in ks); n = w + l
    p = min(1.0, 2 * sum(comb(n, i) for i in range(min(w, l) + 1)) / 2 ** n) if n else 1.0
    print("%-30s groups %d  ours better %d  frontier better %d  p=%.2g" % (name, len(ks), w, l, p))
