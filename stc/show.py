"""Print a task's public trace as a text table for manual inspection.

    python3 -m stc.show --dataset DIR --task TASK_ID [--rows N]
"""
import argparse
import json
import os
import sys


def table(trace, rows=None):
    sig = trace["signals"]
    n_in = sum(1 for s in sig if s["dir"] == "input")
    head = ["cycle"] + [s["name"] for s in sig[:n_in]] + ["|"] + [s["name"] for s in sig[n_in:]]
    body = []
    for k, r in enumerate(trace["rows"][:rows]):
        cells = [str(k)] + [str(v) for v in r[:n_in]] + ["|"] + [str(v) for v in r[n_in:]]
        body.append(cells)
    widths = [max(len(c[i]) for c in [head] + body) for i in range(len(head))]
    return "\n".join(" ".join(c.rjust(w) for c, w in zip(line, widths)) for line in [head] + body) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--task", required=True)
    ap.add_argument("--rows", type=int)
    a = ap.parse_args(argv)
    pub = os.path.join(a.dataset, "public", a.task)
    with open(os.path.join(pub, "interface.json")) as f:
        iface = json.load(f)
    with open(os.path.join(pub, "trace.json")) as f:
        trace = json.load(f)
    print(iface["timing"])
    print()
    sys.stdout.write(table(trace, a.rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
