"""Run Claude Code headless on the hard-tier tasks on Modal, then grade the answers locally.

    modal run modal/run_agent.py --tasks all [--model claude-opus-5-5] [--max-turns 200]
    STC_TASKS=hard2 modal run modal/run_agent.py --tasks all        # tier 2 (out/hard2)

Only each task's public/ folder is sent to Modal. The container returns answer.v and the transcript.
Hidden tests and references stay on this machine; grading uses stc.sim against private/hidden.json.
Uses the Modal secret "anthropic-secret" (override with STC_ANTHROPIC_SECRET=<name>).
"""
import datetime
import json
import os
import pathlib
import subprocess
import sys
import time

import modal

ROOT = pathlib.Path(__file__).resolve().parent.parent
TASKS_DIR = ROOT / "out" / os.environ.get("STC_TASKS", "hard")   # STC_TASKS=hard2 for tier 2
app = modal.App("trace-code-hard-eval")
SECRET_NAME = os.environ.get("STC_ANTHROPIC_SECRET", "anthropic-secret")

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("iverilog", "curl", "ca-certificates", "procps")
    .run_commands("curl -fsSL https://claude.ai/install.sh | bash",
                  "ln -sf /root/.local/bin/claude /usr/local/bin/claude", "claude --version")
    .env({"IS_SANDBOX": "1", "DISABLE_AUTOUPDATER": "1", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"})
)

PROMPT = "Read TASK.md in this folder and complete the task. Work autonomously until answer.v is final."


@app.function(image=image, secrets=[modal.Secret.from_name(SECRET_NAME)], timeout=4 * 60 * 60, cpu=2.0,
              memory=4096, max_containers=8)
def run_one(task: str, files: dict, model: str, max_turns: int, agent_timeout: int) -> dict:
    ws = pathlib.Path("/work")
    for rel, data in files.items():
        p = ws / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    cmd = ["claude", "-p", PROMPT, "--output-format", "stream-json", "--verbose", "--max-turns", str(max_turns),
           "--dangerously-skip-permissions", "--model", model, "--disallowedTools", "WebFetch,WebSearch"]
    t0 = time.time()
    timed_out = False
    try:
        r = subprocess.run(cmd, cwd=ws, capture_output=True, text=True, timeout=agent_timeout,
                           env=dict(os.environ, HOME="/root"))
        transcript = r.stdout
    except subprocess.TimeoutExpired as e:
        timed_out = True
        transcript = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
    result = {}
    for line in transcript.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "result":
            result = ev
    ans = ws / "answer.v"
    return {"task": task, "model": model, "answer": ans.read_text() if ans.exists() else None,
            "transcript": transcript, "timed_out": timed_out, "wall_s": round(time.time() - t0, 1),
            "cost_usd": result.get("total_cost_usd"), "num_turns": result.get("num_turns"),
            "subtype": result.get("subtype"), "final_text": (result.get("result") or "")[-2000:]}


def grade(task, answer):
    sys.path.insert(0, str(ROOT))
    from stc import sim
    priv = TASKS_DIR / task / "private"
    iface = json.loads((priv / "iface.json").read_text())
    hidden = json.loads((priv / "hidden.json").read_text())
    if not answer:
        return {"status": "no_answer"}
    res = sim.simulate(iface, answer, hidden["stimulus"], hidden["expected"], timeout=60)
    checked = sum(1 for row in hidden["expected"] if any(v is not None for v in row))
    return {"status": res["status"], "failing_rows": res["failing_rows"], "checked_rows": checked,
            "first_mismatch": res["mismatches"][0] if res["mismatches"] else None,
            "problems": res["problems"], "log": res["log"][-1500:] if res["status"] != "pass" else ""}


@app.local_entrypoint()
def main(tasks: str = "all", model: str = "claude-opus-5-5", max_turns: int = 200, agent_timeout: int = 10800,
         tag: str = ""):
    names = sorted(p.name for p in TASKS_DIR.iterdir() if (p / "public").is_dir()) if tasks == "all" else tasks.split(",")
    jobs = []
    for t in names:
        pub = TASKS_DIR / t / "public"
        files = {str(p.relative_to(pub)): p.read_bytes() for p in pub.rglob("*") if p.is_file()}
        jobs.append((t, files, model, max_turns, agent_timeout))
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + (f"-{tag}" if tag else "")
    outdir = ROOT / "results" / "hard" / ts
    outdir.mkdir(parents=True, exist_ok=True)
    print(f"{len(jobs)} runs with {model} -> {outdir}")
    summary = []
    for r in run_one.starmap(jobs, order_outputs=False, return_exceptions=True):
        if isinstance(r, Exception):
            print("RUN RAISED:", repr(r)[:400])
            continue
        (outdir / f"{r['task']}.transcript.jsonl").write_text(r.pop("transcript") or "")
        if r["answer"]:
            (outdir / f"{r['task']}.answer.v").write_text(r["answer"])
        r["grade"] = grade(r["task"], r["answer"])
        g = r["grade"]
        print(f"{r['task']:18s} {g['status']:16s} failing_rows={g.get('failing_rows')}/{g.get('checked_rows')} "
              f"turns={r['num_turns']} cost=${r['cost_usd'] or 0:.2f} wall={r['wall_s']}s timeout={r['timed_out']}")
        summary.append({k: v for k, v in r.items() if k != "answer"})
    (outdir / "results.json").write_text(json.dumps(summary, indent=1))
    print(f"total cost ${sum((s.get('cost_usd') or 0) for s in summary):.2f}")
