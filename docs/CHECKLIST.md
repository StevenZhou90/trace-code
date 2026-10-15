# Definition-of-done checklist

`[x]` done, `[~]` partial (what is missing is stated), `[ ]` missing. Each line names the command or test
that proves it. Everything was run on 2026-10-15, with Python 3.14.7 and Icarus Verilog 13.0
(`Icarus Verilog version 13.0 (stable) (v13_0)`), on macOS (Darwin 23.5.0), laptop CPU only.

## Audit
- [x] Folder state recorded before changes. `trace-code/` was empty and was not a git repository. The
  planning docs were committed to `main` first.
- [x] `../signal-to-code/` was read for reusable ideas: the stimulus-hex testbench pattern and the
  comparison style. Nothing in it was changed. No code was copied; the harness was written fresh and
  smaller.

## Ingestion, records, dedup, splits
- [x] Local ingest of project-owned fixtures. Records hold origin, license, source hash, family, generator
  version, parameters and seed. Proof: `tests/test_ingest.py::test_ingested_records`.
- [x] Unsupported designs are rejected with a reason: `license_unknown`, `module_count:2`, `inout_port`,
  `unsafe_construct:system_task:$fopen`, `port_too_wide`, `unsupported_clock:clock`, `compile_error`,
  exact and normalized duplicates. Proof: `test_accepts_and_rejects_with_reasons`.
- [x] One JSONL record schema, with big artifacts stored by relative path. The schema is in the README.
  The sample is `docs/samples/record_fsm.json`.
- [x] Public, target and private data are separated, with a leak test. Proof: `test_public_files_leak_nothing`.
- [x] Exact duplicate removal is tested (`test_exact_and_normalized_duplicates`, fixture `shift4_copy.v`).
- [x] Normalized duplicate detection (comments and whitespace) is tested with fixture `shift4_reformatted.v`.
  The renamed-signal copy is documented as not caught, and that is tested (`test_renamed_copy_is_not_caught`,
  fixture `shift4_renamed.v`).
- [x] Splits are by design group, assigned before variants. Every variant of a group shares a split, and
  the split does not depend on the seed. Proof: `test_variants_of_a_group_share_one_split`,
  `test_split_depends_only_on_the_group`.
- [x] The README marks external ingestion as incomplete.

## Harness
- [x] Icarus Verilog, a fresh temporary folder per run, a wall-clock timeout that kills the process group,
  logs bounded to 8000 bytes, fixed seeds. Proof: `tests/test_harness.py` (`test_timeout_is_enforced`,
  `test_logs_are_bounded`).
- [x] Candidates are treated as untrusted. They are passed only as a file argument. Forbidden system tasks
  and `` `include `` are rejected before compiling, and a `$system("touch ...")` marker is never created.
  Proof: `test_untrusted_input_is_never_run`.
- [x] Distinct statuses: pass, fail, compile_error, interface_error, sim_error, timeout, rejected.
- [x] A fail report lists failing cycles with inputs, expected and actual values. Proof:
  `test_functional_fail_reports_inputs_expected_actual`. The sample is
  `docs/samples/fail_report_handshake_drop_word.json`.
- [x] The timing conventions are implemented as written in `docs/SPEC.md` and the README. Proof:
  `test_timing_rule_row_shows_state_before_the_edge`.

## Families (each has a generator, reference RTL, corner cases, random stimulus, a Python model and bugs)
- [x] comb (mux4 and saturating add, 4 design groups)
- [x] counter (6 design groups)
- [x] fsm (4 design groups)
- [x] arbiter (3 design groups; the README says fixed priority is not fair)
- [x] handshake (4 design groups; a stream checker for no loss, no duplicate, no reorder, and stable data
  while stalled)

## Testbench verification
Commands: `python3 -m stc.build --out data/seed0 --seed 0` then `python3 -m stc.selfcheck --dataset data/seed0`.
The default build has 66 tasks (62 synthetic, 4 ingested). 1 synthetic variant was dropped as a duplicate
task, and 9 fixtures were rejected.

| family | references pass | bug runs that fail | bug runs caught by the visible trace alone | broken candidates classified | compile_error | interface_error | sim_error (2 kinds) | timeout | rejected |
|---|---|---|---|---|---|---|---|---|---|
| comb | 12/12 | 24/24 | 22/24 | 6/6 | ok | ok | ok | ok | ok |
| counter | 17/17 | 69/69 | 53/69 | 6/6 | ok | ok | ok | ok | ok |
| fsm | 12/12 | 45/45 | 37/45 | 6/6 | ok | ok | ok | ok | ok |
| arbiter | 9/9 | 36/36 | 33/36 | 6/6 | ok | ok | ok | ok | ok |
| handshake | 12/12 | 48/48 | 48/48 | 6/6 | ok | ok | ok | ok | ok |
| **total** | **62/62** | **222/222** | **193/222** | **30/30** | | | | | |

For the `--small` build (25 tasks, 1 variant per group): 21/21 references pass, 75/75 bug runs fail
(63 of them are caught by the visible trace alone), and 30/30 broken candidates are classified.

- [x] The reference RTL agrees with the independent Python model on every visible and hidden row. The build
  keeps a task only if it does. Proof: `test_reference_agrees_with_independent_model`.
- [x] Hidden tests use a seed different from the visible trace, plus extra corner cases. Proof:
  `test_hidden_tests_are_separate_from_the_visible_trace`.
- [x] Sample traces for manual reading are in `docs/samples/` (one per family, plus a record, a reference
  and a failure report). I checked the handshake sample by hand, row by row.
- [x] Building twice with the same seed into two clean folders gives byte-identical files. Proof:
  `test_same_seed_gives_identical_files`.

## Tests
- [x] `python3 -m unittest discover -s tests -t . -v`: 38 tests pass in about 33 seconds. The full log is
  `docs/slides/test_output.txt`. It also ran with `-W error::ResourceWarning`, after a pipe leak in
  `run_bounded` was found and fixed.

## Docs, commit, push
- [x] README: setup, smoke command, full test command, build and evaluate commands, record schema, timing
  conventions, split and dedup rules, license notes, limitations, and the AI-coding-agent note.
- [x] Tests and the smoke commands ran from clean temporary output folders (`/tmp/stc-smoke`, temporary
  test folders).
- [x] Diff checked for secrets, large files, private evaluation data and personal names (see the handoff).
- [x] `.gitignore` covers generated datasets (`data/`, `out/`), which hold the private hidden tests.
- [x] Commit on `feat/cpu-pipeline` and push to `origin`. The handoff gives the hash and the remote
  verification.

## Gaps (stated, not hidden)
- [~] Dedup handles comments and whitespace only. It does not catch renamed signals or semantic duplicates.
- [~] Splits hold new parameter sets of the same five templates. That is not evidence of generalization to
  new kinds of designs. With 21 groups, some family and split pairs are empty: comb has no val or test
  tasks, and arbiter has no test tasks.
- [ ] External benchmark ingestion: no license review and no download were done.
- [ ] Synthesis check: none. A pass is simulation only.
- [~] Ingested modules have no independent model. They are graded against their own reference simulation.
- [~] The generator and seed 0 are public, so the seed-0 hidden tests can be rebuilt by anyone. A real
  held-out evaluation needs a seed that is not published.

## Slides
- [x] `docs/slides/deck.pdf`: four pages, generated by `docs/slides/make_deck.py` from `data/seed0` and the
  saved test log. Each page was rendered at 1920x1080 (`docs/slides/pages/`) and checked by eye for
  overflow and overlap.
