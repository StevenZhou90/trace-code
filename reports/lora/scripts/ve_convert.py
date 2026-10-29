"""One-off: convert the VerilogEval waveform-only problems into our trace prompt format.

    python3 ve_convert.py VE_DATASET_DIR OUT_DIR

Writes eval_ve.jsonl ({"task_id", "family", "prompt"}, our format, level A), eval_ve_native.jsonl
(the original VerilogEval prompt, for the frontier model) and tasks.json (interface, visible rows and
outputs for the visible-trace pick). Combinational problems keep every waveform row with known inputs.
Clocked problems keep the rows with clk low, where the inputs of a cycle and the outputs before the next
rising edge are shown, which is our row rule. circuit8 (a latch and a falling-edge flop) does not fit
one row per cycle and is left out.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))  # repository root
from stc.export import prompt  # noqa: E402

PROBS = ["Prob083_mt2015_q4b", "Prob090_circuit1", "Prob103_circuit2", "Prob102_circuit3", "Prob101_circuit4",
         "Prob130_circuit5", "Prob126_circuit6", "Prob098_circuit7", "Prob117_circuit9", "Prob147_circuit10"]
COMB = ("This block has no clock: row k is one input vector and the outputs it produces.")
SEQ = ("Row k: inputs are applied at the falling clock edge, outputs are sampled 1 time unit before the next "
       "rising edge, then the rising edge updates state. So outputs in row k depend on the state before that "
       "edge and on the inputs of row k. Values are unsigned integers of the port width; \"x\" marks an output "
       "with an unknown bit. There is no reset input.")


def parse(text):
    ports = []
    for m in re.finditer(r"^ - (input|output)\s+(\w+)(?:\s*\(\s*(\d+) bits\))?", text, re.M):
        ports.append({"dir": m.group(1), "name": m.group(2), "width": int(m.group(3) or 1)})
    lines = text.split("\n")
    head = next(i for i, l in enumerate(lines) if l.strip().startswith("time"))
    cols = lines[head].split()[1:]
    rows = []
    for l in lines[head + 1:]:
        parts = l.split()
        if not parts or not parts[0].endswith("ns"):
            break
        rows.append(dict(zip(cols, parts[1:])))
    return ports, rows


def value(s, width):
    """VerilogEval prints every multi-bit value in hex."""
    return None if "x" in s else int(s, 16 if width > 1 else 10)


def main():
    src, out = sys.argv[1:]
    os.makedirs(out, exist_ok=True)
    ev, native, tasks = [], [], {}
    for p in PROBS:
        text = open(os.path.join(src, p + "_prompt.txt")).read()
        ports, wave = parse(text)
        clock = next((q["name"] for q in ports if q["name"] in ("clk", "clock")), None)
        ins = [q for q in ports if q["dir"] == "input" and q["name"] != clock]
        outs = [q for q in ports if q["dir"] == "output"]
        if clock:
            wave = [r for r in wave if r[clock] == "0"]
        rows, expected = [], []
        for r in wave:
            vals = [value(r[q["name"]], q["width"]) for q in ins]
            if None in vals:
                continue
            rows.append(dict(zip([q["name"] for q in ins], vals)))
            expected.append([value(r[q["name"]], q["width"]) for q in outs])
        order = ([{"dir": "input", "name": clock, "width": 1}] if clock else []) + ins + outs
        iface = {"module": "dut", "ports": [dict(q, signed=False) for q in order], "clock": clock,
                 "timing": SEQ if clock else COMB}
        trace = {"signals": [{"name": q["name"], "dir": q["dir"], "width": q["width"]} for q in ins + outs],
                 "rows": [[r[q["name"]] for q in ins] + ["x" if v is None else v for v in e]
                          for r, e in zip(rows, expected)]}
        ev.append({"task_id": p, "family": "verilogeval", "prompt": prompt(iface, trace)})
        native.append({"task_id": p, "family": "verilogeval", "prompt": text.replace("TopModule", "dut")})
        tasks[p] = {"interface": iface, "rows": rows, "expected": expected}
    for name, rows in (("eval_ve.jsonl", ev), ("eval_ve_native.jsonl", native)):
        with open(os.path.join(out, name), "w") as f:
            f.writelines(json.dumps(r) + "\n" for r in rows)
    json.dump(tasks, open(os.path.join(out, "tasks.json"), "w"), indent=1)
    print(len(ev), "tasks")


if __name__ == "__main__":
    main()
