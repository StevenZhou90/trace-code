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
fixtures/ingest/      project-owned Verilog fixtures and SOURCES.json
examples/             two deliberately broken candidates for the smoke test
docs/samples/         sample traces, a sample record and a sample failure report
docs/                 milestone brief, design spec, checklist; docs/slides/ has the deck and its generator
tests/                unittest suite
hard/                 hard-tier designs, capture renderer, task build and checks, report collector
modal/run_agent.py    Claude Code agent runner on Modal, with local grading
reports/hard/         agent runs, answers, transcripts and the summary table
```
