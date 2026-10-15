"""Compile and simulate one design on one stimulus with Icarus Verilog, then classify the result.

Every run happens in a fresh temporary directory that is deleted afterwards. The design text is only
ever written to a file and passed to iverilog as a file argument; it is never put into a shell command.

Timing convention (one rule for every family, see README):
  cycle k: inputs for row k are driven at the falling edge (t = 10k), outputs are sampled at t = 10k + 4,
  one time unit before the rising edge at t = 10k + 5, which commits state. So row k holds in_k and
  out_k = g(state_k, in_k). Inputs never change near a rising edge and outputs are never read on an edge,
  which keeps the testbench free of races.
"""
import os
import shutil
import signal
import subprocess
import tempfile
import threading

from . import verilog

LOG_LIMIT = 8000          # bytes kept from any tool output
MAX_MISMATCHES = 20       # failing rows kept in a report
DEFAULT_TIMEOUT = 10.0    # wall-clock seconds per tool run
STATUSES = ("pass", "fail", "compile_error", "interface_error", "sim_error", "timeout", "rejected")


def simulator_version():
    r = subprocess.run(["iverilog", "-V"], capture_output=True, text=True)
    return (r.stdout or r.stderr).splitlines()[0].strip()


def run_bounded(cmd, cwd, timeout):
    """Run cmd, keep at most LOG_LIMIT bytes of combined output, kill the whole process group on timeout.
    Returns (returncode or None on timeout, log text)."""
    with subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          stdin=subprocess.DEVNULL, start_new_session=True) as proc:
        kept = bytearray()

        def drain():  # read everything so the child never blocks on a full pipe, but keep only the head
            for chunk in iter(lambda: proc.stdout.read(4096), b""):
                if len(kept) < LOG_LIMIT:
                    kept.extend(chunk[:LOG_LIMIT - len(kept)])

        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        try:
            rc = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            rc = None
        reader.join(timeout=2)
    return rc, kept.decode("utf-8", "replace")


def stim_inputs(iface):
    return [p for p in iface["ports"] if p["dir"] == "input" and p["name"] != iface.get("clock")]


def outputs(iface):
    return [p for p in iface["ports"] if p["dir"] == "output"]


def _decl(p, kind):
    rng = "[%d:0] " % (p["width"] - 1) if p["width"] > 1 else ""
    return "%s %s%s%s;" % (kind, "signed " if p.get("signed") else "", rng, p["name"])


def testbench(iface, n_rows):
    """Testbench text for this interface. Stimulus comes from stim.hex (inputs packed in port order, first
    input in the most significant bits); one line of hex outputs per row goes to out.txt, then DONE."""
    ins, outs = stim_inputs(iface), outputs(iface)
    total = max(1, sum(p["width"] for p in ins))
    clock = iface.get("clock")
    conns = ([".%s(clk)" % clock] if clock else []) + [".%s(%s)" % (p["name"], p["name"]) for p in ins + outs]
    lines = ["`timescale 1ns/1ps", "module tb;", "  reg clk = 1'b0;",
             "  reg [%d:0] stim [0:%d];" % (total - 1, n_rows - 1), "  integer k, fd;"]
    lines += ["  " + _decl(p, "reg") for p in ins] + ["  " + _decl(p, "wire") for p in outs]
    lines += ["  %s u (%s);" % (iface["module"], ", ".join(conns)),
              "  initial begin",
              '    $readmemh("stim.hex", stim);',
              '    fd = $fopen("out.txt", "w");',
              "    for (k = 0; k < %d; k = k + 1) begin" % n_rows,
              "      clk = 1'b0;                 // falling edge: drive the inputs of row k",
              "      {%s} = stim[k];" % ", ".join(p["name"] for p in ins),
              '      #4 $fdisplay(fd, "%s"%s);  // sample 1 time unit before the rising edge'
              % (" ".join(["%h"] * len(outs)), "".join(", " + p["name"] for p in outs)),
              "      #1 clk = 1'b1;              // rising edge commits state",
              "      #5;",
              "    end",
              '    $fdisplay(fd, "DONE");',
              "    $fclose(fd);",
              "    $finish;",
              "  end",
              "endmodule", ""]
    return "\n".join(lines)


def pack(iface, row):
    val = 0
    total = 0
    for p in stim_inputs(iface):
        val = (val << p["width"]) | (row[p["name"]] & ((1 << p["width"]) - 1))
        total += p["width"]
    return format(val, "0%dx" % max(1, (total + 3) // 4))


def _value(tok):
    """Hex token from $fdisplay %h -> int, or "x" if any bit is x or z."""
    t = tok.lower()
    return "x" if any(c in "xz" for c in t) else int(t, 16)


def interface_problems(iface, text):
    found = dict(verilog.modules(text))
    if iface["module"] not in found:
        return ["missing module %s" % iface["module"]]
    got = {p["name"]: p for p in verilog.ports(found[iface["module"]])}
    want = {p["name"]: p for p in iface["ports"]}
    probs = []
    for name, p in want.items():
        g = got.get(name)
        if g is None:
            probs.append("missing port %s" % name)
        elif (g["dir"], g["width"], g["signed"]) != (p["dir"], p["width"], bool(p.get("signed"))):
            probs.append("port %s is %s[%s]%s, expected %s[%d]%s" % (
                name, g["dir"], g["width"], " signed" if g["signed"] else "",
                p["dir"], p["width"], " signed" if p.get("signed") else ""))
    probs += ["unexpected port %s" % n for n in got if n not in want]
    return probs


def simulate(iface, text, stimulus, expected=None, timeout=DEFAULT_TIMEOUT):
    """Run a design on stimulus rows. With expected rows (None = don't care) the result is pass/fail.
    Returns {status, stage, log, outputs, mismatches (first MAX_MISMATCHES), failing_rows, problems}."""
    res = {"status": None, "stage": None, "log": "", "outputs": None, "mismatches": [], "failing_rows": 0,
           "problems": []}
    bad = verilog.unsafe_constructs(text)
    if bad:
        res.update(status="rejected", stage="safety", problems=bad)
        return res
    work = tempfile.mkdtemp(prefix="stc-sim-")
    try:
        with open(os.path.join(work, "dut.v"), "w") as f:
            f.write(text)
        # 1. The design must compile on its own before we look at its interface.
        rc, log = run_bounded(["iverilog", "-g2012", "-o", "alone.vvp", "dut.v"], work, timeout)
        if rc != 0:
            res.update(status="timeout" if rc is None else "compile_error", stage="compile", log=log)
            return res
        # 2. Exact module name, port names, directions, widths and signedness.
        probs = interface_problems(iface, text)
        if probs:
            res.update(status="interface_error", stage="interface", problems=probs)
            return res
        # 3. Compile with the testbench and run it.
        with open(os.path.join(work, "tb.v"), "w") as f:
            f.write(testbench(iface, len(stimulus)))
        with open(os.path.join(work, "stim.hex"), "w") as f:
            f.write("".join(pack(iface, r) + "\n" for r in stimulus))
        rc, log = run_bounded(["iverilog", "-g2012", "-s", "tb", "-o", "sim.vvp", "tb.v", "dut.v"], work, timeout)
        if rc != 0:
            res.update(status="timeout" if rc is None else "compile_error", stage="compile_tb", log=log)
            return res
        rc, log = run_bounded(["vvp", "-n", "sim.vvp"], work, timeout)
        res["log"] = log
        if rc is None:
            res.update(status="timeout", stage="simulate")
            return res
        out_path = os.path.join(work, "out.txt")
        lines = []
        if os.path.exists(out_path):
            with open(out_path) as f:
                lines = [l for l in f.read().split("\n") if l.strip()]
        n_out = len(outputs(iface))
        if rc != 0 or not lines or lines[-1] != "DONE" or len(lines) - 1 != len(stimulus):
            res.update(status="sim_error", stage="simulate",
                       problems=["vvp exit code %s, %d of %d rows written" % (rc, max(0, len(lines) - 1), len(stimulus))])
            return res
        rows = [[_value(t) for t in l.split()] for l in lines[:-1]]
        if any(len(r) != n_out for r in rows):
            res.update(status="sim_error", stage="simulate", problems=["malformed output rows"])
            return res
        res["outputs"] = rows
        if expected is None:
            res.update(status="pass", stage="simulate")  # ran cleanly; nothing to compare against
            return res
        bad = compare(iface, stimulus, expected, rows)
        res.update(status="fail" if bad else "pass", stage="compare", failing_rows=len(bad),
                   mismatches=bad[:MAX_MISMATCHES])
        return res
    finally:
        shutil.rmtree(work, ignore_errors=True)


def compare(iface, stimulus, expected, actual):
    """Rows where some expected (non-None) output differs from the actual one, with inputs, expected and
    actual values by name. An "x" in the actual output never matches a number."""
    names = [p["name"] for p in outputs(iface)]
    bad = []
    for k, (e_row, a_row) in enumerate(zip(expected, actual)):
        wrong = [n for n, e, a in zip(names, e_row, a_row) if e is not None and e != a]
        if wrong:
            bad.append({"cycle": k, "inputs": stimulus[k], "signals": wrong,
                        "expected": dict(zip(names, e_row)), "actual": dict(zip(names, a_row))})
    return bad
