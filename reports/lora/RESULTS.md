# LoRA fine-tune against a frontier model: results for a report

This folder is the complete record of the fine-tuning experiment, written so that someone who did not
run it can write a report. The method and the main tables are also in the top-level README, in the
sections "Training data and LoRA baseline" and "Less information: anonymous ports and pins, against a
frontier model".

## The task

Each task gives a cycle-by-cycle input/output trace of a small hardware block and asks for a
synthesizable Verilog module `dut` that reproduces it. A candidate passes when it passes the hidden
tests, which are longer traces that the model never sees. The five families are combinational
datapaths, counters, sequence detectors (state machines), arbiters and valid/ready handshakes.

Information levels (`stc/blind.py`):
- A: named ports;
- B: anonymous ports in shuffled order, with no reset named;
- C: every bit is a separate anonymous 1-bit pin in shuffled order.

Evaluation sets:
- held-out: 165 tasks from 33 design groups (75 test tasks and 90 val tasks), split by design group;
- fresh: 76 tasks from 38 design groups that were never trained on, with new parameter values.

## Systems

- Ours: Qwen2.5-Coder-7B-Instruct with LoRA rank 16, trained in four rounds on one A100. Round 4 writes
  sequence detectors as a shift register compared with the pattern (`stc.export --style shift`). The
  weights are not published.
- Frontier: Opus 5.5 through the Claude Code CLI, with no tools, one turn and the same prompt
  (`baselines/claude_cli.py`).
- Picking among samples uses only the public visible trace: `stc.verify` (first sample that reproduces
  it), `stc.consensus` (behavioral vote among those that reproduce it) and, at level C, `stc.rewire`
  (search over pin wiring, bus widths, constants and state targets). No pick ever sees a hidden test.

## Headline results

Equal sample budget, 16 samples each, fresh set (the only significant win at an equal budget):

| | ours | Opus 5.5 | p (paired, tasks) | groups better / worse, p |
|---|---|---|---|---|
| fresh B | **92.1%** | 76.3% | 0.012 | 10 / 2, 0.039 |
| fresh A | 80.3% | 76.3% | 0.58 | 4 / 3, 1.0 |

Sample-count curve on the fresh set (ours, round 4; Opus best of 4 is 73.7% A, 76.3% B, 65.8% C):

| samples | A | B | C |
|---|---|---|---|
| 1 (greedy) | 67.1% | 63.2% | |
| 1 (temperature 1) | 65.8% | 64.5% | 26.3% |
| 4 | 77.6% | 77.6% | 39.5% |
| 8 | 76.3% | 84.2% | 47.4% |
| 16 | 80.3% | 92.1% | 55.3% |
| 64 | 88.2% | 90.8% | 71.0% |

Opus at 16 samples: 75.0% to 76.3% at A and 75.0% to 76.3% at B, depending on the pick. It does not
improve from 4 to 16 samples, because its wrong sequence detectors still reproduce the visible trace.

64 samples (ours) against 4 (Opus):

| | ours | Opus, 1 | Opus, best of 4 | p (against best of 4) |
|---|---|---|---|---|
| fresh A | 88.2% | 72.4% | 73.7% | 0.0034 |
| fresh B | 90.8% | 73.7% | 76.3% | 0.0074 |
| fresh C | 71.0% | 60.5% | 65.8% | 0.42 |
| held-out A | 90.3% | 86.7% | | 0.34 |
| held-out B | 90.3% | 86.7% | 87.9% | 0.57 |
| held-out C | 82.4% | 67.3% | 69.7% | 0.00051 |

Where Opus is better:
- with 4 samples each: fresh C (65.8% against 39.5%, p = 0.00009) and held-out B (87.9% against 73.3%,
  p = 0.0009); the other settings tie;
- with one sample each: fresh A (72.4% against 65.8%, p = 0.36);
- outside our generator, on VerilogEval (next section).

## Outside check: VerilogEval waveform-only problems

VerilogEval (NVIDIA, MIT license) has 10 problems given only as a waveform that fit one row per cycle:
circuit1 to circuit10 without circuit8 (a latch and a falling-edge flop), and mt2015_q4b.
`scripts/ve_convert.py` converts them into our prompt format. `scripts/ve_check.py` grades with our own
tests, written from each problem's reference design; VerilogEval's own testbenches were not run. The
tests pass 10 of 10 hand-written correct designs.

| | first sample | picked from samples |
|---|---|---|
| Opus 5.5, our prompt, 4 samples | 10/10 | 10/10 |
| Opus 5.5, original prompt, 4 samples | 9/10 | 10/10 |
| ours, 4 samples | 0/10 | 0/10 |
| ours, 64 samples | 0/10 | 4/10 |

Our model fails plain logic functions such as (a|b)&(c|d) that lie outside its five training families.

## Honest reading

- On one family of trace-to-Verilog tasks with port names hidden (level B), the fine-tuned 7B model with
  16 samples and a visible-trace pick beats Opus 5.5 with 16 samples, on design groups it never trained
  on. The gain is in sequence detectors: Opus passes about 30% to 40% of the never-trained ones.
- The gain comes from many varied samples plus the pick, not from a better single answer.
- It does not carry over outside the generator, and it is not state of the art on any independent
  benchmark.
- The fresh groups are new parameter values of the same five families, not new kinds of circuits.

## Cost

- Opus: one pass over the 76 fresh tasks cost about $3.05, so about $0.04 per task and sample. The
  12 extra passes for the 16-sample comparison cost $69.06. All Opus runs together cost roughly $250.
- Ours: 64 samples for 76 tasks took about 8 minutes on one A100; the level C search adds CPU time.

## Files

`scores/` holds one JSON per graded run: `summary` (pass rate by split and family) and `tasks` (status
per task, with its design group). Failure examples are left out, because they contain hidden test rows.

| setting | ours | Opus 5.5 |
|---|---|---|
| fresh, 64 samples | `fresh/score_c_r4_fresh.json` (A), `fresh/score_c_r4_fresh_B.json` (B), `fresh/score_c_rw6_r4_fresh_C.json` (C) | `frontier/score_opus_fresh_{A,B,C}_single.json`, `frontier/score_opus_fresh_{A,B,C}_n4.json` |
| fresh, equal budget | `eq/score_c_k{1,4,8,16}_fresh{,_B,_C}.json` | `frontier/score_opus_fresh_{A,B}_n16.json`, `frontier/score_opus_fresh_{A,B}_n16_consensus.json` |
| fresh, greedy | `greedy/score_eval_fresh{,_B}.json` | |
| fresh, Opus with our search | | `frontier/score_opus_fresh_C_rw6.json`, `frontier/score_opus_fresh_C_consensus.json`, `frontier/score_opus_fresh_B_consensus.json` |
| held-out, 64 samples | `r4/score_c_r4_{test,val}{,_B}.json`, `r4/score_c_rw6_r4_{test,val}_C.json` | `frontier/score_opus_{test,val}_{A,B,C}_all.json` (1 sample), `frontier/score_opus_{test,val}_{B,C}_n4.json` |
| held-out, equal budget | `eq/score_c_k{1,4}_{test,val}{,_B,_C}.json` | as above |
| earlier rounds | `lora1/` (1.5B), `q7/` (7B round 1), `q7r2/` (round 2), `fresh/score_v_r3_*`, `fresh/*pool*` | `frontier/score_sonnet_{test,val}.json` (Sonnet 5.5, level A) |

`scripts/`:
- `compare.py`: exact paired McNemar test, for example
  `python3 reports/lora/scripts/compare.py "fresh B 16|eq/score_c_k16_fresh_B.json|frontier/score_opus_fresh_B_n16.json"`;
  several files can be joined with commas.
- `groups.py`: per design group sign test, same arguments.
- `check_shift.py`: checks that the shift-register answer style passes every hidden test.
- `ve_convert.py`, `ve_check.py`: the VerilogEval outside check (needs a clone of
  github.com/NVlabs/verilog-eval).

To rebuild a dataset and grade a candidate file:
`python3 -m stc.build --out data/fresh --seed 7 --fresh --variants 2`, then
`python3 -m stc.score --dataset data/fresh --level B --candidates picks.jsonl --out score.json`.
