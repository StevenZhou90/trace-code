# Definition-of-done checklist

Mark each line `[x]` done, `[~]` partial (say what is missing), or `[ ]` missing. Only mark a line done
after the command that proves it has run and its output was read. Put the proof command next to it.

## Audit
- [ ] Folder state recorded before changes (it was empty on 2026-10-15, no git).
- [ ] `../signal-to-code/` read for reusable pieces; nothing in it changed.

## Ingestion, records, dedup, splits
- [ ] Local ingest of project-owned fixtures with origin, license, source hash, family, generator version, parameters, seed.
- [ ] Unsupported designs rejected with a reason (at least: license unknown, multiple modules, `inout`, system task, too wide).
- [ ] One JSONL record schema; big artifacts by relative path.
- [ ] Public / target / private separation, with a test that public files leak nothing.
- [ ] Exact duplicate removal tested.
- [ ] Normalized (comments and whitespace) duplicate detection tested; renamed-signal copy documented as not caught.
- [ ] Split by design group before variants; test that every variant of a group shares a split.
- [ ] External ingestion marked incomplete in the README.

## Harness
- [ ] Icarus Verilog, fresh temp dir per run, wall-clock timeout, bounded logs, fixed seeds.
- [ ] Candidate treated as untrusted (no shell strings, banned system tasks rejected).
- [ ] Distinct statuses: compile_error, sim_error, timeout, interface_error, fail, pass.
- [ ] Fail output lists failing cycles with inputs, expected and actual.
- [ ] Timing conventions implemented as in `docs/SPEC.md` and written in the README.

## Families (each: generator, reference RTL, corner cases, random stimulus, Python model, mutants)
- [ ] comb
- [ ] counter
- [ ] fsm
- [ ] arbiter (README says fixed priority is not fair)
- [ ] handshake (no loss, no duplicate, no reorder, stable while stalled)

## Testbench verification (fill in real counts)
| family | references pass | mutants killed / total | compile_error ok | sim/interface error ok | timeout ok |
|---|---|---|---|---|---|
| comb | | | | | |
| counter | | | | | |
| fsm | | | | | |
| arbiter | | | | | |
| handshake | | | | | |

- [ ] Reference RTL agrees with the independent Python model on every visible and hidden row.
- [ ] Hidden tests use different seeds from visible traces plus extra corner cases.
- [ ] Sample traces left in `docs/samples/` for manual reading.
- [ ] Same seed, two clean builds, identical hashes.

## Docs, commit, push
- [ ] README: setup, smoke command, full test command, build and evaluate commands, record schema, timing, split/dedup rules, license notes, limitations, written-with-an-AI-coding-agent note.
- [ ] Tests run from a clean temp output directory; output pasted into the handoff.
- [ ] Diff checked for secrets, large files, private evaluation data, personal names.
- [ ] `.gitignore` covers generated outputs.
- [ ] Commit on the approved feature branch with a plain factual message.
- [ ] Push to the confirmed remote, then remote branch verified to contain the commit (or the blocker stated).

## Slides
- [ ] Four-page deck built from real results only (see `docs/SLIDES.md`), exported to PDF.
