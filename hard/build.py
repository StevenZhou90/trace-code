"""Build the hard-tier tasks and verify them before any agent sees them.

    python3 -m hard.build --out out/hard [--seed 0]

Per task, under OUT/<task>/:
  public/   what the agent gets: TASK.md, the observation, tools/ (a harness copy to run its own answer)
  private/  grader only: hidden.json (stimulus + expected), iface.json, reference.v, verify.json

Checks, all must hold for a task to be written:
  1. the reference RTL agrees with the independent Python model on visible and hidden stimulus;
  2. every listed bug fails the hidden tests;
  3. every listed bug is distinguishable from the reference on the visible observation alone (on the
     rows the agent can interpret: after the first reset that the observation shows), so no bug is
     caught only by behavior the agent never saw;
  4. capture tasks: a channel-level wrapper around the reference passes the channel-level hidden tests.
"""
import argparse
import json
import os
import random
import re
import shutil
import sys

from stc import sim
from . import capture
from .designs import DESIGNS

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASKS = [("handshake", "capture"), ("bucket", "clean"), ("lock", "clean"), ("lock", "capture"),
         ("cpu", "clean"), ("cpu", "capture")]
VISIBLE_ROWS = {"handshake": 500, "bucket": 600, "lock": 1200, "cpu": 900}

CLEAN_TASK = """# Task

You are given an observation of {describe}: its ports (`interface.json`) and a cycle-by-cycle trace of
every port (`trace.json`, one row per clock cycle, signal order in `signals`; the timing rule is in
`interface.json`). You cannot run or probe the real device. Nothing else is known about it.

Write synthesizable Verilog in `answer.v`: a module named `dut` with exactly the ports in
`interface.json`, that behaves like the device for any input sequence.

Grading: your module runs on long hidden input sequences you have not seen, with the same timing rule.
Every output is compared with the real device on every cycle after the first reset. Outputs before the
first reset are not checked. Partial credit does not exist: one wrong output on one cycle is a fail.

Tools here: `python3`, `iverilog`, and `tools/run_candidate.py`, which simulates your `answer.v` on input
rows you choose using the grader's own testbench:

    python3 tools/run_candidate.py answer.v my_stimulus.json

`my_stimulus.json` is a list of objects, one per cycle, mapping each input name (not the clock) to an
integer. It prints one line per cycle with your outputs.

Be meticulous: the hidden tests exercise corner cases. When you are done, leave `answer.v` in this folder.
"""

CAPTURE_TASK = """# Task

You are given a logic analyzer capture of {describe}.

- `capture.csv`: one row per sample, every 4 ns. Column `t_ns`, then one column per channel (0 or 1).
- `channels.json`: the channels and their direction (`input` = driven into the device, `output` =
  driven by the device).

Nothing else is known. Which channel is the clock, whether there is a reset and its polarity, how
channels group into multi-bit values and in which bit order, and what the device does are all for you
to work out. The capture starts some time after power-on, the clock has jitter, and some samples are
corrupted by single-sample glitches. You cannot run or probe the real device.

Write synthesizable Verilog in `answer.v`: a module named `dut` with one 1-bit port per channel, named
exactly as in `channels.json` (`ch00`, `ch01`, ...), with the given directions.

Grading: a clean clock drives the device's clock channel. Each cycle, the other inputs change at the
falling edge and every output is sampled 1 ns before the next rising edge. Your outputs are compared with
the real device on long hidden input sequences, on every cycle after the first reset. One wrong output
bit on one cycle is a fail.

Tools here: `python3`, `iverilog`, and `tools/run_candidate.py`, which simulates your `answer.v` on input
rows you choose using the grader's own testbench:

    python3 tools/run_candidate.py answer.v my_stimulus.json --clock chNN

`my_stimulus.json` is a list of objects, one per cycle, mapping every input channel except the clock to
0 or 1. It prints one line per cycle with your outputs.

Be meticulous: the hidden tests exercise corner cases. When you are done, leave `answer.v` in this folder.
"""

RUN_CANDIDATE = '''"""Simulate answer.v on your own stimulus with the grader's testbench and timing.

    python3 tools/run_candidate.py answer.v stim.json [--clock CHANNEL]
"""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stc import sim

here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ap = argparse.ArgumentParser()
ap.add_argument("answer"); ap.add_argument("stim"); ap.add_argument("--clock")
a = ap.parse_args()
if os.path.exists(os.path.join(here, "interface.json")):
    iface = json.load(open(os.path.join(here, "interface.json")))
else:
    chans = json.load(open(os.path.join(here, "channels.json")))
    if not a.clock:
        sys.exit("capture task: pass --clock CHANNEL")
    iface = {"module": "dut", "clock": a.clock,
             "ports": [{"name": c["name"], "dir": c["dir"], "width": 1, "signed": False} for c in chans]}
rows = json.load(open(a.stim))
res = sim.simulate(iface, open(a.answer).read(), rows, None, timeout=60)
if res["status"] != "pass":
    print(json.dumps({k: res[k] for k in ("status", "stage", "problems", "log")}, indent=1)); sys.exit(1)
names = [p["name"] for p in iface["ports"] if p["dir"] == "output"]
for k, row in enumerate(res["outputs"]):
    print(k, json.dumps(dict(zip(names, row))))
'''


def iface_of(d):
    return {"module": "dut", "ports": d["ports"], "clock": d["clock"]}


def first_reset(rows, reset):
    name, level = reset
    return next(k for k, r in enumerate(rows) if r[name] == level)


def distinguishable(ref_out, bug_out, start):
    return any(a != b for a, b in zip(ref_out[start:], bug_out[start:]))


def wrapper(ref, ports, chans):
    """Channel-level dut around the reference (renamed ref_core), used to check the capture grading path."""
    core = re.sub(r"\bmodule\s+dut\b", "module ref_core", ref, count=1)
    decl = ",\n".join("    %s wire %s" % (d, ch) for ch, _, _, d in chans)
    wires, conns = [], []
    for p in ports:
        bits = {b: ch for ch, name, b, d in chans if name == p["name"]}
        expr = "{%s}" % ", ".join(bits[b] for b in range(p["width"] - 1, -1, -1)) if p["width"] > 1 else bits[0]
        if p["dir"] == "output":
            wires.append("    wire [%d:0] w_%s;" % (p["width"] - 1, p["name"]))
            for b, ch in bits.items():
                wires.append("    assign %s = w_%s[%d];" % (ch, p["name"], b))
            conns.append(".%s(w_%s)" % (p["name"], p["name"]))
        else:
            conns.append(".%s(%s)" % (p["name"], expr))
    return core + "\nmodule dut (\n%s\n);\n%s\n    ref_core u (%s);\nendmodule\n" % (decl, "\n".join(wires), ", ".join(conns))


def force_resets(rows, reset, positions):
    name, level = reset
    rows = [dict(r) for r in rows]
    for p in positions:
        for k in (p, p + 1):
            rows[k][name] = level
    return rows


def build_task(out, dname, mode, seed):
    d = DESIGNS[dname]
    tid = "%s_%s" % (dname, mode)
    rng = random.Random("%d:%s" % (seed, tid))
    iface = iface_of(d)
    ref = d["rtl"]()
    n = VISIBLE_ROWS[dname]
    vis = d["visible"](random.Random("%d:%s:visible" % (seed, tid)), n)
    window = (0, n)
    if mode == "capture":
        window = (40, n - 15)                         # the first reset is not in the capture
        vis = force_resets(vis, d["reset"], [n // 3, (2 * n) // 3])
    hid = d["hidden"](random.Random("%d:%s:hidden" % (seed, tid)))
    report = {"task": tid, "visible_rows": n, "window": window, "hidden_rows": len(hid), "bugs": {}}

    vis_exp, hid_exp = d["model"](vis), d["model"](hid)
    rv = sim.simulate(iface, ref, vis, vis_exp)
    rh = sim.simulate(iface, ref, hid, hid_exp)
    report["reference_vs_model"] = {"visible": rv["status"], "hidden": rh["status"]}
    assert rv["status"] == "pass" and rh["status"] == "pass", (tid, rv["mismatches"][:2], rh["mismatches"][:2])

    # The agent can only interpret rows after the first reset it can see.
    seen = vis[window[0]:]
    start = window[0] + first_reset(seen, d["reset"])
    for bug in d["bugs"]:
        bh = sim.simulate(iface, d["rtl"](bug), hid, hid_exp)
        bv = sim.simulate(iface, d["rtl"](bug), vis)
        ok_vis = bv["outputs"] is not None and distinguishable(rv["outputs"][:window[1]], bv["outputs"][:window[1]], start)
        report["bugs"][bug] = {"hidden": bh["status"], "hidden_failing_rows": bh["failing_rows"],
                               "visible_distinguishable": ok_vis}
        assert bh["status"] == "fail", (tid, bug, bh["status"])
        assert ok_vis, (tid, bug, "not visible in the observation")

    pub, priv = os.path.join(out, tid, "public"), os.path.join(out, tid, "private")
    os.makedirs(os.path.join(pub, "tools", "stc"), exist_ok=True)
    os.makedirs(priv, exist_ok=True)
    for f in ("sim.py", "verilog.py"):
        shutil.copy(os.path.join(HERE, "stc", f), os.path.join(pub, "tools", "stc", f))
    with open(os.path.join(pub, "tools", "stc", "__init__.py"), "w") as f:
        f.write("")
    with open(os.path.join(pub, "tools", "run_candidate.py"), "w") as f:
        f.write(RUN_CANDIDATE)

    if mode == "clean":
        names_in = [p for p in d["ports"] if p["dir"] == "input" and p["name"] != d["clock"]]
        names_out = [p for p in d["ports"] if p["dir"] == "output"]
        pub_iface = {"module": "dut", "ports": d["ports"], "clock": d["clock"],
                     "reset": {"name": d["reset"][0], "active": "high" if d["reset"][1] else "low", "synchronous": True},
                     "timing": "Row k: inputs are applied at the falling clock edge, outputs are sampled 1 time unit "
                               "before the next rising edge, then the rising edge updates state. Values are unsigned "
                               "integers; \"x\" marks an unknown output before the first reset."}
        tr = {"signals": names_in + names_out,
              "rows": [[r[p["name"]] for p in names_in] + list(o) for r, o in zip(vis, rv["outputs"])]}
        with open(os.path.join(pub, "interface.json"), "w") as f:
            json.dump(pub_iface, f, indent=1)
        with open(os.path.join(pub, "trace.json"), "w") as f:
            f.write('{"signals": %s,\n"rows": [\n%s\n]}\n' % (json.dumps(tr["signals"]),
                                                            ",\n".join(json.dumps(r) for r in tr["rows"])))
        with open(os.path.join(pub, "TASK.md"), "w") as f:
            f.write(CLEAN_TASK.format(describe=d["describe"]))
        grade_iface, hid_stim, hid_expect = iface, hid, hid_exp
    else:
        chans, csv = capture.render(d["ports"], d["clock"], vis, rv["outputs"], rng, window[0], window[1])
        with open(os.path.join(pub, "capture.csv"), "w") as f:
            f.write(csv)
        with open(os.path.join(pub, "channels.json"), "w") as f:
            json.dump([{"name": c, "dir": dr} for c, _, _, dr in chans], f, indent=1)
        with open(os.path.join(pub, "TASK.md"), "w") as f:
            f.write(CAPTURE_TASK.format(describe=d["describe"]))
        clock_ch = next(c for c, name, _, _ in chans if name == d["clock"])
        grade_iface = {"module": "dut", "clock": clock_ch,
                       "ports": [{"name": c, "dir": dr, "width": 1, "signed": False} for c, _, _, dr in chans]}
        hid_stim, hid_expect = capture.to_channel_rows(chans, d["ports"], hid, hid_exp)
        wrap = wrapper(ref, d["ports"], chans)
        rw = sim.simulate(grade_iface, wrap, hid_stim, hid_expect)
        report["channel_wrapper_vs_model"] = rw["status"]
        assert rw["status"] == "pass", (tid, rw["status"], rw["problems"], rw["mismatches"][:2])
        report["capture_samples"] = csv.count("\n") - 1
        report["channels"] = [{"channel": c, "port": name, "bit": b} for c, name, b, _ in chans]
        with open(os.path.join(priv, "reference_channels.v"), "w") as f:
            f.write(wrap)
    with open(os.path.join(priv, "hidden.json"), "w") as f:
        json.dump({"stimulus": hid_stim, "expected": hid_expect}, f)
    with open(os.path.join(priv, "iface.json"), "w") as f:
        json.dump(grade_iface, f, indent=1)
    with open(os.path.join(priv, "reference.v"), "w") as f:
        f.write(ref)
    with open(os.path.join(priv, "verify.json"), "w") as f:
        json.dump(report, f, indent=1)
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--only", help="comma-separated task ids")
    a = ap.parse_args(argv)
    for dname, mode in TASKS:
        tid = "%s_%s" % (dname, mode)
        if a.only and tid not in a.only.split(","):
            continue
        r = build_task(a.out, dname, mode, a.seed)
        bugs = r["bugs"]
        print("%-18s ref=%s/%s bugs fail hidden %d/%d, visible-distinguishable %d/%d%s" % (
            tid, r["reference_vs_model"]["visible"], r["reference_vs_model"]["hidden"],
            sum(b["hidden"] == "fail" for b in bugs.values()), len(bugs),
            sum(b["visible_distinguishable"] for b in bugs.values()), len(bugs),
            ("  capture %d samples, wrapper %s" % (r["capture_samples"], r["channel_wrapper_vs_model"]))
            if "capture_samples" in r else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
