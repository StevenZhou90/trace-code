# trace-code

Signal-to-code data and grading pipeline, CPU only. A task shows a model the interface of a hidden
Verilog module and a cycle-by-cycle trace of its inputs and outputs. The model must write synthesizable
Verilog that also passes hidden tests it never saw. This repository builds those tasks and grades
candidate answers. It contains no model, no training code and no GPU code.

The code in this repository was written with an AI coding agent (Claude Code) and reviewed by running
the tests and commands below.

## Setup

- Python 3 standard library only (tested with Python 3.14.7). No packages to install.
- Icarus Verilog (tested with `Icarus Verilog version 13.0 (stable) (v13_0)`): `brew install icarus-verilog`
  on macOS or `apt-get install iverilog` on Debian and Ubuntu. Both `iverilog` and `vvp` must be on `PATH`.
  Verilator is not used.

## Commands

End-to-end smoke test (about 25 seconds). It builds a small dataset for all five families, checks the
testbenches, and grades one supplied candidate on hidden tests. The last command prints a `fail` report
and exits 1, because that example candidate is deliberately broken.

```
python3 -m stc.build --out /tmp/stc-smoke --small
python3 -m stc.selfcheck --dataset /tmp/stc-smoke
python3 -m stc.evaluate --dataset /tmp/stc-smoke --task tef5d471775 --candidate examples/handshake_drop_word.v
```

Full test suite (38 tests, about 33 seconds):

```
python3 -m unittest discover -s tests -t . -v
```

Build the default dataset (3 seed variants per design group) and check it:

```
python3 -m stc.build --out data/seed0 --seed 0
python3 -m stc.selfcheck --dataset data/seed0
```

Grade any candidate file on one task's hidden tests (exit code 0 only for `pass`):

```
python3 -m stc.evaluate --dataset data/seed0 --task <task_id> --candidate answer.v --report report.json
```

Look at a public trace as a table:

```
python3 -m stc.show --dataset data/seed0 --task <task_id> --rows 32
```

Task IDs are listed in `records.jsonl`. With seed 0 the IDs are always the same.

## What gets built

```
DIR/public/<task>/interface.json   model input: ports, clock, reset, timing rule
DIR/public/<task>/trace.json       model input: observed trace, one row per cycle
DIR/target/<task>/reference.v      training target: the reference RTL, module renamed to dut
DIR/private/<task>/hidden.json     grader only: hidden stimulus and expected outputs
DIR/logs/<task>/reference.log      reference compile and simulation log (bounded)
DIR/records.jsonl                  one record per task (schema below)
DIR/rejects.jsonl                  every rejected source or task, with a reason
DIR/summary.json                   counts by family and split, tool versions
DIR/selfcheck.json                 written by stc.selfcheck
```

A model may only see `public/<task>/`. A test checks that the public files hold no reference source, no
family or bug names, no parameters, no seeds and no hidden answers. Task IDs are hashes, and every module
is named `dut`. Port names are part of the public interface, and they do hint at what a block does.

### Record schema (`records.jsonl`, one JSON object per line)

| field | meaning |
|---|---|
| `task_id` | `t` followed by 10 hex characters, stable for a given seed |
| `family` | `comb`, `counter`, `fsm`, `arbiter`, `handshake`, or `ingested` |
| `origin`, `license` | `synthetic` and `project-owned`, or the fixture path and its license from `SOURCES.json` |
| `source_sha256`, `norm_sha256` | hash of the source text, and hash after normalization (see dedup rules) |
| `generator_version`, `params`, `seed` | generator version (`stc-0.1`), structural parameters, task seed |
| `design_group`, `split` | the group used for deduplication and splitting, and its split (`train`, `val` or `test`) |
| `interface` | the same object as `public/<task>/interface.json` |
| `public_dir`, `public_trace_path`, `reference_rtl_path`, `private_tests_path`, `reference_log_path` | paths relative to the dataset folder |
| `simulator`, `simulator_version` | `icarus` and the first line of `iverilog -V` |
| `reference_status` | result of the reference on the visible and hidden stimulus (`pass` is required) |
| `model_check_status` | `agree` when the reference matched the independent Python model on every row; `none` for ingested modules, which have no model |
| `visible_rows`, `hidden_rows` | row counts |

`trace.json` has `signals` (inputs first, then outputs, each in port declaration order, with `name`, `dir`,
`width` and `signed`) and `rows` (one list per cycle in the same order). `hidden.json` has `stimulus`
(one object per row), `expected` (one list per row in output order, where `null` means don't care),
`corner_rows` and `random_rows`.

## Timing conventions

These conventions are the same for every task, and they are written into every `interface.json`.

- There is one clock, `clk`, and it is active on the rising edge. The clock is not a trace column.
- Reset `rst` is synchronous, active high, and wins over every other input. For ingested modules, whether
  the reset is synchronous is not checked.
- In row `k`, the testbench drives the inputs at the falling edge (`t = 10k` ns). It samples every output
  at `t = 10k + 4`, which is 1 ns before the rising edge at `t = 10k + 5`, and that edge then updates the
  state. So row `k` holds the inputs of row `k` and the outputs `g(state_k, inputs_k)`. Inputs never change
  near a rising edge and outputs are never read on an edge, so the testbench has no races.
- Values are unsigned integers of the port width. No port is signed in this milestone, but the field
  exists. An output with any `x` or `z` bit is written as `"x"`, and it never matches an expected number.
- Rows before the first reset take effect have unknown state, so the expected value there is "don't care"
  (`null`).

## Harness and statuses

`stc/sim.py` writes the candidate to a fresh temporary folder, which is deleted afterwards. The candidate
is only ever passed to `iverilog` as a file argument. Before compiling, any system task outside a small
allow-list (`$display`, `$finish`, `$fatal`, `$signed`, ...) and any `` `include `` gets the candidate
rejected. So candidate code cannot open files or run commands. Every tool run has a wall-clock timeout
(10 seconds by default) that kills the whole process group, and only the first 8000 bytes of output are
kept.

| status | meaning |
|---|---|
| `pass` | every expected output matched on every hidden row |
| `fail` | it simulated, but some outputs differ; the report lists failing rows with inputs, expected and actual values |
| `compile_error` | `iverilog` failed |
| `interface_error` | module `dut` is missing, or a port name, direction, width or signedness is wrong |
| `sim_error` | `vvp` exited with an error (for example `$fatal`), or stopped before writing every row |
| `timeout` | a tool run went over the time limit and was killed |
| `rejected` | the source uses a forbidden system task or `` `include ``, and it was never compiled |

A compile success is not a pass. A pass shows that the outputs matched in simulation. It does not show
that the design synthesizes.

## Task families

Each family is one small file in `stc/families/`. It has its parameters, the reference RTL with named
bugs, the corner-case rows and the random rows. The independent Python models are in `stc/models.py`.

| family | design groups | rule | corner cases in the hidden tests |
|---|---|---|---|
| `comb` | mux4 and saturating add, W = 4 and 8 | `y = d[sel]`; `y = min(a + b, 2^W - 1)` | every select value; every input pair for W = 4; sums just below, at and above the limit |
| `counter` | W = 3, 4, 8, with and without enable | reset to 0; count up when enabled, modulo 2^W; otherwise hold | wraparound, holding, reset together with enable, reset in the middle of a count |
| `fsm` | patterns 1011, 1101, 110, 1001 | overlapping detector; Moore output high the cycle after the last bit | overlaps, near misses, reset in every state, the pattern without its first bit |
| `arbiter` | N = 2, 3, 4 | registered grant; the lowest-numbered request wins; zero when there is no request | no request, every request pattern, every requester alone, reset while requests are pending |
| `handshake` | depth 1 and 2, W = 4 and 8 | ready/valid buffer; `in_ready` = not full; first in, first out; reset empties it | long backpressure, a full buffer with changing input, push and pop together, reset while full |

The arbiter has fixed priority and is **not fair**: requester 0 can starve every other requester forever.

How the hidden tests are made, for every task:

- The expected outputs come from the Python model, not from the reference RTL. The build simulates the
  reference on the visible stimulus and on the hidden stimulus. The task is kept only if the reference
  agrees with the model on every row.
- The hidden stimulus is the family's corner cases followed by 200 random rows. The random rows use a
  seed different from the visible trace's seed.
- For handshake tasks, the grader also runs a protocol check that does not use the model. Each word must
  come out once and in order, and `out_data` must not change while the output is stalled.

`stc.selfcheck` verifies the testbenches themselves:

- Each reference must pass.
- Each named bug must fail. The bugs include a wrong reset value, an asynchronous reset, wrapping one
  early, ignoring the enable, a wrong state transition, no overlap, Mealy timing, reversed priority, more
  than one grant, a dropped word, a duplicated word, data changing while stalled, and reset keeping data.
- Six broken candidates per family must each get the right status: a syntax error, a renamed port, a
  runtime `$fatal`, an early `$finish`, an endless loop, and a `$system` call.

## Ingestion

`stc/ingest.py` reads `fixtures/ingest/`, which holds Verilog files written for this repository, plus
`SOURCES.json`, which gives each file's origin and license. Files are read in sorted order. Each file is
rejected with a reason if any of these is true:

- its license is unknown;
- it has a forbidden system task or `` `include ``;
- it does not have exactly one module;
- it has an `inout` port;
- a port width cannot be worked out, or a port is wider than 32 bits;
- it has a clock other than `clk`, or a `negedge` clock;
- it does not compile;
- it duplicates a file that was already accepted.

Accepted modules are renamed to `dut`, and their traces come from random stimulus. They have no
independent model, so the reference simulation is the oracle for them, and their records say
`model_check_status: none`. **External ingestion is not done.** No external benchmark was downloaded or
redistributed in this milestone.

## Deduplication and splits

These rules are in `stc/dedup.py`.

- **Exact duplicate**: same SHA-256 of the raw source. The first file is kept and the others are rejected.
- **Normalized duplicate**: same SHA-256 after removing comments and collapsing every run of whitespace to
  one space. This is deliberately conservative. It does **not** catch renamed signals or modules,
  reordered code, spacing inside a statement (`y=x` compared with `y = x`), or designs that behave the
  same but are written differently. It is not semantic deduplication. A test shows that a renamed copy of
  a fixture gets through.
- **Duplicate task**: the same normalized reference with the same visible trace. This happens, for
  example, when a counter's only input is the reset. In the default seed-0 build, 1 of 63 synthetic
  variants was dropped for this reason.
- **Splits**: a design group is the family plus the structural parameters (for example
  `counter:{"W": 4, "enable": true}`), or the normalized hash for ingested files. The split comes from a
  fixed hash of the group name: 80 / 10 / 10 into train, val and test. It is assigned before any seed
  variant is made, so every variant of a design, and every task with the same normalized source, is in
  the same split. Different seeds do not make designs independent.
- With only 21 synthetic groups, the split sizes are uneven, and some family and split pairs are empty
  (see `summary.json`). The held-out split holds different parameter sets of the same five templates. It
  is not evidence of generalization to new kinds of designs.

## License notes

All Verilog in this repository, both the generated references and the fixtures, was written for this
project. No third-party RTL is included. No license file has been chosen for the repository yet.

## Limitations

- The pass/fail grading is simulation on finite stimulus. It is not formal equivalence and not proof of
  synthesis. No synthesis check runs.
- The five families are small templates with 21 design groups in total. They are a pipeline test bed, not
  a benchmark.
- The generator, the seeds and the models are public. Anyone can rebuild the hidden tests of a known seed,
  so a real held-out evaluation needs a seed that is not published.
- Ingestion is local only. The port parser only reads plain module headers (ANSI or non-ANSI, with
  constant or simple parameter widths). Anything it cannot read is rejected, not guessed.
- Ingested modules are graded against their own simulation, without an independent model.
- The visible trace alone does not pin down the design. In the default seed-0 self-check, 29 of 222 bug runs
  pass the visible trace (12 of 75 in the `--small` build), and only the hidden corner cases catch them.

## Hard tier: agent reverse-engineering test

`hard/` builds harder tasks on top of the same harness. They use designs with deep hidden state (a
combination lock, a token bucket, a 16-opcode CPU, a pseudo-LRU cache, a program-memory
microcontroller, and a serial receiver with bit stuffing and CRC). Each design comes as a clean trace
and as a messy logic-analyzer capture. The capture has shuffled 1-bit channels, clock jitter, skew,
glitches, and no power-on reset. `modal/run_agent.py` runs Claude Code headless on each task's public
folder on Modal and grades the answer locally against hidden tests. In a light test, Claude Opus 5.5
solved all 11 tasks once each task's behavior was fully observable. The full write-up is in
`docs/hard-tier.md`. The runs, answers, transcripts, task texts and build checks are in `reports/hard/`,
with `reports/hard/summary.md` as the table.

```
python3 -m hard.build --out out/hard --tier 1        # build and verify tier 1 (out/ is git-ignored)
python3 -m hard.build --out out/hard2 --tier 2       # tier 2
modal run modal/run_agent.py --tasks all             # agent runs (Modal secret anthropic-secret)
STC_TASKS=hard2 modal run modal/run_agent.py --tasks all
python3 -m hard.report --out reports/hard            # collect results for a report
```

## Training data and LoRA baseline

`--wide` adds each family's wider groups: more widths and sizes, every 3- to 5-bit FSM pattern, and
new structure (down and modulo counters; subtract, max, min, popcount and Gray code; non-overlapping
detectors; highest-index and round-robin arbiters). The original 21 groups keep their names and splits.
Seed 0 with 5 variants gives 196 synthetic groups (163 train, 18 val, 15 test) and 981 tasks. The
self-check passes: 977/977 references pass and 3,469/3,469 bugs fail. Arbiters landed in no test group,
so they are reported on the validation split.

```
python3 -m stc.build --out data/wide --seed 0 --wide --variants 5
python3 -m stc.selfcheck --dataset data/wide
python3 -m stc.export --dataset data/wide --out out/sft     # prompts and answers, plus control sets
# on the GPU machine: train/lora.py, then train/generate.py (see train/README.md)
python3 -m stc.score --dataset data/wide --candidates candidates.jsonl --out scores.json
```

A prompt holds the ports, the timing rule and the visible trace table; the answer is the reference
Verilog. Two control sets check whether a model reads the trace: the trace removed, and the trace of a
different design group with the same ports.

First run (Qwen2.5-Coder-1.5B-Instruct, LoRA rank 16, 3 epochs, 802 examples, one A100, 13.5 minutes,
one seed, greedy decoding). Pass means every hidden test passed:

| | base compiled | base passed | LoRA compiled | LoRA passed | LoRA, no trace | LoRA, wrong trace |
|---|---|---|---|---|---|---|
| test (75 tasks, 15 groups) | 58.7% | 0% | 100% | 40.0% | 33.3% | 4.6% |
| val (90 tasks, 18 groups) | 52.2% | 0% | 100% | 22.2% | 16.7% | 0% |

The wrong-trace drop shows that the model follows the trace. The no-trace score shows that much of
the result comes from the ports and the familiar templates. FSMs and arbiters pass 0%. Variants of a
group share one answer, so the 75 test tasks are 15 independent designs. Held-out groups are new
parameter sets and options of the same five templates, not new kinds of circuits.

## Less information: anonymous ports and pins, against a frontier model

Each task can be given at three information levels (`stc/blind.py`):
- A: named ports;
- B: anonymous ports in shuffled order, with no reset named;
- C: every bit is a separate anonymous 1-bit pin in shuffled order, so which pins form a bus, the bit
  order and the reset are all hidden.

The hidden tests are the same at every level, because a candidate is wrapped back onto the original
ports before grading.

The fine-tuned model is Qwen2.5-Coder-7B-Instruct with LoRA rank 16, trained in four rounds on one
A100:
- round 1: levels A, B and C of the wide training groups;
- round 2: more training groups;
- round 3: 1,000 procedurally sampled designs (`stc.build --proc`), none from a held-out group;
- round 4: the same data, with sequence detectors written as a shift register of the last L bits
  compared with the pattern (`stc.export --style shift`), instead of a state table.

The shift-register form behaves exactly the same as the state table and passes every hidden test. Its
advantage is that the pattern appears literally in the code, so the model only has to read the pattern
off the trace.

At test time the model draws 64 samples per task. The pick uses only the public visible trace:
- `stc.rewire` (level C) searches pin wiring, bus widths, constants and next-state targets against the
  visible trace;
- `stc.consensus` keeps the candidates that reproduce the visible trace, groups them by their outputs on
  extra random inputs, and picks the most voted behavior.

The frontier baseline is Opus 5.5 with the same prompt, no tools and one turn
(`baselines/claude_cli.py`). It is reported as one sample, and as the best of four samples picked with
the same visible-trace check. Giving Opus our pin search and vote made it worse at level C (63.2%
against 65.8%), so its best number is shown.

Fresh set: 76 tasks from 38 design groups that were never trained on, with new parameter values
(counter moduli 7, 13, 28, 100, 18 and 50; 7-bit datapaths; 6-bit and non-overlapping 5-bit sequence
detectors; 9-input arbiters; 7- and 10-bit handshakes). The p values are an exact paired McNemar test
per task against Opus best-of-4, and a sign test per design group.

| fresh set | ours | Opus, 1 sample | Opus, best of 4 | p (tasks) | groups better / worse, p |
|---|---|---|---|---|---|
| A named ports | **88.2%** | 72.4% | 73.7% | 0.0034 | 8 / 1, 0.039 |
| B anonymous ports | **90.8%** | 73.7% | 76.3% | 0.0074 | 9 / 1, 0.021 |
| C anonymous pins | **71.0%** | 60.5% | 65.8% | 0.42 | 6 / 5, 1.0 |

Held-out groups of the original split, 165 tasks from 33 groups (test and val together):

| held-out | ours | Opus, 1 sample | Opus, best of 4 | p (tasks) |
|---|---|---|---|---|
| A | 90.3% | 86.7% | | 0.34 |
| B | 90.3% | 86.7% | 87.9% | 0.57 |
| C | **82.4%** | 67.3% | 69.7% | 0.00051 |

What the gap is made of:
- Sequence detectors are the main gain. On the fresh set Opus passes 28.6% of them with named ports,
  while our model passes 67.9% at level A and 75% at level B. Most of the remaining misses drop the first
  bit of a 6-bit pattern; the shorter pattern also fits the visible trace.
- At level C, Opus is still better on 9-input arbiters and 7-bit arithmetic, where the bit order of two
  operand buses must be found.
- Many Opus failures reproduce the visible trace but fail the hidden tests, so part of the task is
  choosing the behavior that the visible trace does not fully fix.

Equal sample budget. The tables above draw 64 samples from our model against 4 from Opus. With the
same 4 samples per task (the first 4 of the 64, picked the same way), our model does not beat Opus:

| 4 samples each | ours | Opus | p (tasks) |
|---|---|---|---|
| fresh A | 77.6% | 73.7% | 0.61 |
| fresh B | 77.6% | 76.3% | 1.0 |
| fresh C | 39.5% | **65.8%** | 0.00009 |
| held-out B | 73.3% | **87.9%** | 0.0009 |
| held-out C | 69.7% | 69.7% | 1.0 |

At 16 samples each, the fresh set was run again for Opus at levels A and B (12 more passes, $69). Opus
is shown with whichever pick is better for it, the visible-trace check or the behavioral vote:

| 16 samples each | ours | Opus | p (tasks) | groups better / worse, p |
|---|---|---|---|---|
| fresh A | 80.3% | 76.3% | 0.58 | 4 / 3, 1.0 |
| fresh B | **92.1%** | 76.3% | 0.012 | 10 / 2, 0.039 |

Opus does not improve from 4 to 16 samples (76.3% at level B both times): its wrong sequence detectors
reproduce the visible trace, so more samples do not help it pick. Ours climbs from 77.6% at 4 samples
to 84.2% at 8 and 92.1% at 16. At level C ours reaches 55.3% at 16 samples, still below Opus at 4
(65.8%).

With one sample each, fresh A is 65.8% for ours against 72.4% for Opus (p = 0.36). So the gains come
from many samples plus the visible-trace pick, not from a better single answer: our samples are varied
enough that one of them is right, and Opus's are not. The level B win at 16 samples each holds at an
equal sample budget, and the other wins hold at equal cost:
- one Opus pass over the 76 fresh tasks cost $3.05, so best-of-4 is about $0.16 per task;
- 64 samples of the 7B model for the same 76 tasks took about 8 minutes on one A100, which is a few
  tenths of a dollar at common A100 hourly prices, plus CPU time for the level C search.

Caveats:
- The selection never sees a hidden test.
- The fresh groups are new parameter values of the same five families, not new kinds of circuits.
- The fresh set is small (38 groups), so the level C result on it is a lead, not a significant win.
- The model weights are not published.
- The benchmark is our own generator, and the result does not carry over outside it. VerilogEval
  (NVIDIA, MIT license) has 10 problems given only as a waveform that fit one row per cycle (circuit1
  to circuit10 without circuit8, and mt2015_q4b). They were converted to our prompt format and graded
  with our own tests, written from each problem's reference design; VerilogEval's testbenches were not
  run. Opus passes 10 of 10 with 4 samples, on our prompt and on the original prompt. Our model passes
  4 of 10 with 64 samples and 0 of 10 with 4: it fails plain logic functions such as (a|b)&(c|d) that
  lie outside its five training families.
- With greedy decoding (one answer), our model scores 67.1% (A) and 63.2% (B) on the fresh set, against
  72.4% and 73.7% for one Opus sample.

## Layout

```
stc/sim.py            harness: testbench, isolated run, timeout, statuses, comparison
stc/verilog.py        comment stripping, safety scan, module and port parsing
stc/families/*.py     the five families
stc/models.py         independent Python models and the handshake stream checker
stc/ingest.py         local ingestion and rejection reasons
stc/dedup.py          hashes, duplicate detection, split assignment
stc/build.py          dataset build (one command)
stc/evaluate.py       grade one candidate on one task's hidden tests
stc/selfcheck.py      references pass, bugs fail, broken candidates classified
stc/show.py           print a trace as a table
stc/export.py         prompt and answer files for fine-tuning, with control sets
stc/score.py          grade generated candidates and summarize by split and family
fixtures/ingest/      project-owned Verilog fixtures and SOURCES.json
examples/             two deliberately broken candidates for the smoke test
docs/samples/         sample traces, a sample record and a sample failure report
docs/                 milestone brief, design spec, checklist; docs/slides/ has the deck and its generator
tests/                unittest suite
hard/                 hard-tier designs, capture renderer, task build and checks, report collector
modal/run_agent.py    Claude Code agent runner on Modal, with local grading
train/                LoRA fine-tuning and batched generation (run on a GPU machine)
reports/hard/         agent runs, answers, transcripts and the summary table
```
