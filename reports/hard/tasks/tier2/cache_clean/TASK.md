# Task

You are given an observation of a block that answers 1 or 0 to address requests: its ports (`interface.json`) and a cycle-by-cycle trace of
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
