# Task

You are given a logic analyzer capture of a block with one serial input.

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
