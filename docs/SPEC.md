# Design spec for the CPU pipeline milestone

This file fixes the decisions that the brief leaves open, so the code and the tests have one target.
If the implementation has to differ, change this file in the same commit and say why.

## Changes made during implementation (2026-10-15)

- Layout: there is no `trace.py`; the testbench and trace parsing live in `sim.py`. Split assignment lives in
  `dedup.py`. Two small commands were added: `stc.selfcheck` (testbench verification) and `stc.show` (trace
  table). Tests run with `python3 -m unittest discover -s tests -t .`.
- A seventh status, `rejected`, was added for sources with forbidden system tasks or `` `include ``. They
  are never compiled, so they are neither compile errors nor interface errors.
- The candidate safety scan is an allow-list of system tasks rather than a deny-list. `$display`-style tasks
  are allowed, because the harness bounds the output it keeps.
- The arbiter grant is registered (it updates on the clock edge, and reset clears it), not combinational. This
  makes the reset behavior testable and keeps the family different from `comb`.
- Mutants that turned out to be equivalent for a parameter set are skipped. `no_overlap` is skipped for the
  pattern 110, whose overlap fallback equals a fresh start.
- Two variants with an identical normalized reference and an identical visible trace are dropped as
  `duplicate_task`. This happens for counters whose only input is `rst`.
- Ingestion also rejects `negedge` clocks, unused `clk` ports, and files that do not compile.
- Expected values before the first reset are don't-care (`null`), and so is `out_data` while `out_valid` is
  low.

## Tools and environment (checked on 2026-10-15)

- Simulator: Icarus Verilog 13.0 (`/opt/homebrew/bin/iverilog`, `vvp`). Verilator is not installed, so
  it is not used. Record `iverilog -V` first line in every record.
- Yosys is installed. It may be used for an optional "does it synthesize" lint, but simulation results
  must never be reported as synthesis proof.
- Python 3 (system 3.14). Use only the standard library. Tests use `unittest` so no install is needed.
  If pytest is used for running, the tests must still pass under `python3 -m unittest`.
- Long or wide runs may go on Modal through one small script, but the milestone
  must run fully on a laptop CPU.

## Layout (target, keep it this small)

```
trace-code/
  README.md
  stc/                      one small Python package
    sim.py                  isolated compile + run with timeout, bounded logs, status classification
    trace.py                stimulus -> testbench, VCD-free cycle table parse, trace JSONL
    families/               one file per family: params, reference RTL text, stimulus, mutants
      comb.py counter.py fsm.py arbiter.py handshake.py
    models.py               independent Python behavioral models (one function per family)
    ingest.py               local Verilog ingest + interface validation + reject reasons
    dedup.py                exact hash + normalized-source hash
    split.py                group-based split assignment
    build.py                one command: build the dataset
    evaluate.py             one command: evaluate a candidate on hidden tests
  fixtures/ingest/          project-owned Verilog modules for the ingest demo (with a LICENSE note)
  tests/                    unittest files
  docs/                     this spec, brief, checklist, sample traces, slides
```

Names are a suggestion. Fewer files is fine. No class hierarchies or plugin registries; a family is a
module with a few plain functions and a dictionary entry in one table.

## Commands (the README must show the real ones)

- Smoke: `python3 -m stc.build --out /tmp/stc-smoke --seed 0 --small` then
  `python3 -m stc.evaluate --dataset /tmp/stc-smoke --task <id> --candidate <file.v>`.
- Full tests: `python3 -m unittest discover -s tests -v`.
- Dataset generation: `python3 -m stc.build --out <dir> --seed <n>`.

## Timing conventions (the same for every family)

- One clock `clk`, rising edge active. One synchronous reset `rst`, active high. Reset has priority over
  every other input. Combinational blocks have no clock or reset; the harness still steps them by cycle.
- Signal order in every trace: inputs first in port-declaration order, then outputs in port-declaration
  order. `clk` is not a trace column.
- All values are unsigned unless the interface marks a port `signed`. Values are written as integers in
  JSON. Any `x` or `z` bit is written as the string `"x"` and always counts as a mismatch.
- Race-free stepping. For cycle `k` the testbench:
  1. drives the inputs for cycle `k` on the falling edge of `clk`,
  2. samples every output 1 time unit before the next rising edge,
  3. lets the rising edge commit state.
  So row `k` holds `in_k` and `out_k = g(state_k, in_k)`, and `state_{k+1} = f(state_k, in_k)`.
  Inputs never change near a rising edge, and outputs are never read on an edge.
- Period 10 time units, `timescale 1ns/1ps`. The run ends with `$finish` after the last row. The harness
  enforces a wall-clock timeout (default 10 s) and a simulation time limit inside the testbench.

## Status values from the harness

`compile_error`, `sim_error`, `timeout`, `interface_error`, `fail`, `pass`, `rejected`. A `fail` record lists the
first failing cycles (bounded, for example 20), with the inputs, expected and actual outputs. Logs are
truncated to a fixed byte limit. Each run happens in a fresh temporary directory that is deleted after.

Untrusted candidate rules: the candidate is only passed as a file argument to `iverilog`. It is never
`source`d, `eval`ed or put into a shell string. Reject candidates that use `$system`, `$fopen`,
`$readmem*`, `` `include `` or other file and system tasks before compiling (reason recorded). The
candidate must declare exactly the required module name and ports with the right widths and directions.

## Public, target and private data

| part | who sees it | contents |
|---|---|---|
| `public/` | the model | interface (ports, widths, directions, signedness, clock/reset roles), observed trace rows, timing conventions text |
| `target/` | training only | reference RTL |
| `private/` | the grader only | hidden stimulus, expected outputs, mutant list, seeds |

Public input must not contain the reference source, hidden stimulus or answers, internal state, family
name, parameters, mutant names or anything else that gives the answer away. Add a test that scans public
files for these.

## Record format (one JSONL line per task)

```
task_id, family, origin, license, source_sha256, norm_sha256, generator_version, params, seed,
design_group, split, interface, public_trace_path, reference_rtl_path, private_tests_path,
simulator, simulator_version, reference_status, reference_log_path, model_check_status, created_with
```

Paths are relative to the dataset root. Big things (traces, RTL, logs) live in files, not in the line.

## Families (keep each one hand-checkable)

| family | parameters | reference behavior | corner cases | mutants (each must fail) |
|---|---|---|---|---|
| comb | width W in {4, 8}, op in {mux4, add_sat} | `mux4`: `y = d[sel]`; `add_sat`: `y = min(a+b, 2^W-1)` | all `sel` values; `a+b` at, below and above max; zeros | wrong select bit, no saturation, off-by-one limit |
| counter | width W in {3, 4, 8}, has_enable | on reset `q=0`; else if `en` `q=q+1` mod 2^W; else hold | reset mid-count, enable low hold, wraparound at 2^W-1, reset and enable together | reset value 1, wrap one early, ignores enable, reset loses priority |
| fsm | one sequence detector (for example "1011", overlapping), Moore output | documented state table; `y=1` in the cycle after the last bit | reset in every state, overlap, near misses, recovery after a wrong bit | one wrong transition, Mealy instead of Moore timing, no overlap |
| arbiter | N in {2, 3, 4} requesters | fixed priority: lowest index wins; grant is one-hot or zero; registered grant (reset clears it) | no request, all requests, every pair, single requests | reversed priority, two grants at once, grant with no request |
| handshake | data width W, one-entry or two-entry buffer | ready/valid in and out, documented depth, reset empties the buffer | backpressure for many cycles, input valid while full, reset while full | drops a word, duplicates a word, data changes while stalled, reset keeps data |

Fixed priority is not fair; the README must say so. The handshake checker compares the output stream as a
sequence (no loss, no duplicate, no reorder) and checks that `out_data` is stable while
`out_valid && !out_ready`.

Each family also gets three generic bad candidates that test classification: a syntax error
(`compile_error`), a runtime failure such as a `$fatal` path or a port mismatch (`sim_error` or
`interface_error`), and a combinational loop or other non-terminating design (`timeout`). Note: a pure
zero-delay loop may hang `vvp`; that is the intended timeout test, so the wall-clock limit must kill it.

## Oracles

- The expected outputs for hidden tests come from the Python behavioral model in `models.py`, written
  from the table above, not from the reference RTL.
- The build step simulates the reference RTL on both visible and hidden stimulus and requires that it
  agrees with the Python model on every row. Any disagreement stops the build for that task.
- Visible traces and hidden tests use different seeds derived from the task seed (for example
  `seed*2+0` and `seed*2+1` through a fixed hash), and hidden tests add the deterministic corner cases.

## Deduplication and splits

- Exact duplicate: same SHA-256 of the raw source bytes. Keep the first, log the rest.
- Normalized duplicate: same SHA-256 after removing comments, collapsing whitespace and dropping blank
  lines. Conservative on purpose. It does not catch renamed signals, reordered statements or
  functionally equal designs. Do not call it semantic deduplication.
- `design_group` = family plus the structural parameters (for synthetic tasks) or the normalized hash
  plus origin (for ingested modules). Split = a fixed hash of `design_group` mapped to train / val / test
  (for example 80 / 10 / 10). The split is chosen from the group before any seed variant is made, so all
  seed variants of one design share a split. Seeds do not make designs independent.
- Tests: duplicate fixtures are removed, a comment-only change is caught as a normalized duplicate, a
  renamed-signal copy is not caught (documented limit), and all variants of one group land in one split.

## Ingestion

- Input: a local folder of `.v` files plus a sidecar (for example `SOURCES.json`) giving origin and
  license per file. Files without a known license are rejected with reason `license_unknown`.
- Accept only single-module files with one clock named `clk` (or no clock), an optional `rst`, port
  widths that are constants up to 32 bits, and no `include`, memories loaded from files, system tasks or
  `inout` ports. Every reject has a reason string.
- Ingested modules get a trace from random stimulus and a reference status, but no independent Python
  model. Say so in the record (`model_check_status: "none"`).
- External benchmarks are not downloaded in this milestone. The README marks external ingestion as
  incomplete.

## Reproducibility

- Building twice with the same seed into two clean directories must give byte-identical records,
  traces and private tests (ignore only fields that hold absolute paths or times, and avoid having those).
- One test runs the build twice and compares hashes.
