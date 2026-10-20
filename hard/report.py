"""Collect everything needed to write a report on the hard-tier agent runs into one folder.

    python3 -m hard.report --out reports/hard

Copies, without any hidden tests or reference RTL:
  runs/<run>/            results.json, each answer.v and transcript from results/hard/<run>/
  tasks/<set>/<task>/    TASK.md and verify.json (build checks: reference vs model, bug kill and
                         visibility, capture sample count; capture tasks also list the channel map)
  summary.csv, summary.md   one row per agent run
Task sets: out/hard (tier 1), out/hard2-run1 (tier 2 as first run), out/hard2 (tier 2 after the
receiver length fix).
"""
import argparse
import csv
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASK_SETS = {"tier1": "out/hard", "tier2-run1": "out/hard2-run1", "tier2": "out/hard2"}
# Which task set each run was made against.
RUN_SET = {"20261015-164800-opus55-light": "tier1", "20261015-172337-opus55-cpu-capture": "tier1",
           "20261015-191454-opus55-tier2": "tier2-run1", "20261015-201329-opus55-tier2-crcrx-fixed": "tier2"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="reports/hard")
    a = ap.parse_args(argv)
    out = os.path.join(ROOT, a.out)
    for name, rel in TASK_SETS.items():
        src = os.path.join(ROOT, rel)
        if not os.path.isdir(src):
            sys.exit("missing %s: rebuild it with python3 -m hard.build" % rel)
        for task in sorted(os.listdir(src)):
            dst = os.path.join(out, "tasks", name, task)
            os.makedirs(dst, exist_ok=True)
            shutil.copy(os.path.join(src, task, "public", "TASK.md"), dst)
            shutil.copy(os.path.join(src, task, "private", "verify.json"), dst)
    rows = []
    for run, tset in RUN_SET.items():
        src = os.path.join(ROOT, "results", "hard", run)
        dst = os.path.join(out, "runs", run)
        os.makedirs(dst, exist_ok=True)
        for f in sorted(os.listdir(src)):
            shutil.copy(os.path.join(src, f), dst)
        for r in json.load(open(os.path.join(src, "results.json"))):
            g = r["grade"]
            v = json.load(open(os.path.join(ROOT, TASK_SETS[tset], r["task"], "private", "verify.json")))
            rows.append({"run": run, "task_set": tset, "task": r["task"], "model": r["model"], "status": g["status"],
                         "failing_rows": g.get("failing_rows"), "checked_rows": g.get("checked_rows"),
                         "reported_turns": r["num_turns"], "cost_usd": round(r["cost_usd"] or 0, 2),
                         "wall_min": round(r["wall_s"] / 60, 1), "bugs_checked": len(v["bugs"]),
                         "visible_rows": v["visible_rows"], "capture_samples": v.get("capture_samples", "")})
    with open(os.path.join(out, "summary.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    cols = ["task_set", "task", "status", "failing_rows", "checked_rows", "reported_turns", "cost_usd", "wall_min",
            "bugs_checked", "capture_samples"]
    md = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    md += ["| " + " | ".join(str(r[c]) for c in cols) + " |" for r in rows]
    total = sum(r["cost_usd"] for r in rows)
    md.append("")
    md.append("%d runs, %d pass, reported cost $%.2f (a cancelled first cpu_capture run is not counted)." % (
        len(rows), sum(r["status"] == "pass" for r in rows), total))
    with open(os.path.join(out, "summary.md"), "w") as f:
        f.write("\n".join(md) + "\n")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
