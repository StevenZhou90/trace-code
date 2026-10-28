"""Single-shot frontier baseline: send each eval prompt to a Claude model through the Claude Code CLI,
with every tool disabled and one turn, so the model answers from the prompt alone.

    python3 baselines/claude_cli.py --eval eval_test.jsonl --dataset data/wide --model claude-opus-5-5 \
        --out candidates.jsonl [--one-per-group] [--jobs 4]

Uses the same system message as train/lora.py. Writes {"task_id", "family", "verilog", "raw",
"cost_usd", "seconds"} per line, the format stc.score reads. Tasks already in --out are skipped, so an
interrupted run can be resumed.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

SYSTEM = ("You are an expert hardware engineer. Given a cycle-by-cycle trace of a hardware block, "
          "write synthesizable Verilog for a module named dut that reproduces it.")
NO_TOOLS = "Bash,Read,Write,Edit,Glob,Grep,WebFetch,WebSearch,Task,Agent,NotebookEdit,TodoWrite,Skill"
FENCE = re.compile(r"```(?:verilog|systemverilog|v)?\s*\n(.*?)```", re.S)


def extract(raw):
    """Same rule as train/generate.py: first code fence if any, first `module` to last `endmodule`."""
    m = FENCE.search(raw)
    text = m.group(1) if m else raw
    start, end = text.find("module"), text.rfind("endmodule")
    return text[start:end + len("endmodule")] + "\n" if 0 <= start < end else ""


def ask(model, prompt, cwd, timeout):
    cmd = ["claude", "-p", "--model", model, "--no-session-persistence", "--output-format", "json",
           "--max-turns", "1", "--disallowedTools", NO_TOOLS, "--system-prompt", SYSTEM]
    try:
        p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, cwd=cwd, timeout=timeout)
        d = json.loads(p.stdout)
        return d.get("result") or "", d.get("total_cost_usd") or 0.0, (d.get("duration_ms") or 0) / 1000
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        return "", 0.0, float(timeout) if isinstance(e, subprocess.TimeoutExpired) else 0.0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--eval", required=True)
    ap.add_argument("--dataset", required=True, help="built dataset, for design groups")
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--one-per-group", action="store_true", help="only the first task of each design group")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--timeout", type=float, default=600)
    a = ap.parse_args(argv)

    with open(os.path.join(a.dataset, "records.jsonl")) as f:
        group = {r["task_id"]: r["design_group"] for r in map(json.loads, f)}
    with open(a.eval) as f:
        rows = [json.loads(l) for l in f if l.strip()]
    if a.one_per_group:
        firsts = {}
        for r in sorted(rows, key=lambda r: r["task_id"]):
            firsts.setdefault(group[r["task_id"]], r)
        rows = sorted(firsts.values(), key=lambda r: r["task_id"])
    done = set()
    if os.path.exists(a.out):
        with open(a.out) as f:
            done = {json.loads(l)["task_id"] for l in f if l.strip()}
    todo = [r for r in rows if r["task_id"] not in done]
    cwd = tempfile.mkdtemp(prefix="stc-baseline-")  # empty folder: nothing for the CLI to pick up

    def one(r):
        raw, cost, secs = ask(a.model, r["prompt"], cwd, a.timeout)
        return {"task_id": r["task_id"], "family": r["family"], "verilog": extract(raw), "raw": raw,
                "cost_usd": cost, "seconds": secs}

    total = 0.0
    with ThreadPoolExecutor(a.jobs) as pool, open(a.out, "a") as f:
        for k, rec in enumerate(pool.map(one, todo), 1):
            f.write(json.dumps(rec) + "\n")
            f.flush()
            total += rec["cost_usd"]
            print("%d/%d %s %s $%.3f (total $%.2f)" % (k, len(todo), rec["task_id"], rec["family"],
                                                      rec["cost_usd"], total), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
