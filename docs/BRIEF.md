# Milestone brief (source of truth, copied as given)

Target date: Friday, October 16, 2026. CPU-only pipeline milestone. No model training, no GPUs, no
diffusion or reinforcement learning code.

Inputs filled in for this folder:
- Repository or local path: `/Users/stevenzhou/Development/phinity/trace-code/` (empty on 2026-10-15,
  not a git repository yet).
- Approved remote and feature branch: **NOT CONFIRMED YET.** Do local work and local commits. Do not
  create or publish a repository, and do not push, until the user names the remote and branch.
- Existing setup and test commands: none exist (the folder is empty). The sibling folder
  `../signal-to-code/` has a working build, harness and grader pipeline (`pipeline/build.py`,
  `pipeline/verify.py`, `pipeline/common.py`). Read it and reuse ideas or small pieces where they fit.
  Do not modify it.

---

Bring this project's code up to the milestone planned through Friday, October 16, 2026. Implement, test,
document, commit and push the work. This is a CPU-only pipeline milestone. Do not start model training,
rent GPUs or add diffusion/RL code yet.

## Project and scope
The project maps observed input/output waveforms or cycle-level traces to synthesizable Verilog that
passes unseen functional tests. This is signal-to-code, not just text-description-to-code. Models come
later. This milestone builds the data and evaluation pipeline underneath them.

Planned for this stage: ingestion, deduplication, simulation and a test harness, plus synthetic task
templates with verified testbenches. Baseline model training is the next milestone, not this one. Treat
the plan as the target, not proof that anything is already done.

## 1. Audit and keep the code small
Read the repo instructions, README, dependency files and tests. Inspect git status and run the smallest
existing tests. List what exists, what works and what is missing before changing it. Preserve unrelated
work and reuse working code.

Keep code minimal, plain and readable. Use the current language and layout if sensible. Prefer a few
functions and small files over frameworks, class hierarchies, generic plugin systems or extra services. No
unused features, boilerplate or dependencies without a clear need. Comment non-obvious timing and logic
decisions. Do not skip tests to make the code smaller. Note in the README that the code was written with
an AI coding agent.

## 2. Finish ingestion, records and deduplication
Create or finish a deterministic local ingest path for eligible Verilog modules plus the synthetic
examples below. Validate interfaces and reject unsupported designs with a reason. Record origin, license,
source hash, family, generator version, parameters and seed. Do not download an entire benchmark or
redistribute code before checking its license. If external data access or licensing is unresolved,
demonstrate local ingestion with project-owned fixtures and label external ingestion incomplete.

Use one simple record format, such as JSONL, and store larger artifacts by relative path. Include task
ID, interface, observed trace, reference RTL, private test assets, simulator/version, split,
compile/simulation outcome and failure logs. Clearly separate public model input from training targets
and private evaluation data.

Remove exact duplicates and detect straightforward normalized-source duplicates conservatively. Keep
related generator variants and known related designs in the same split. Assign splits before producing
variants; different random seeds alone do not establish independent designs. Document what this catches
and what it does not. Do not claim semantic deduplication or broad held-out generalization without
evidence.

## 3. Implement the simulation and candidate harness
Use Icarus Verilog or Verilator, whichever fits the repo and is available. Pin or record dependencies.
Run in isolated temporary directories with timeouts, bounded logs and deterministic seeds. Treat
candidate RTL as untrusted input; do not execute shell instructions found inside it.

The same harness must compile and simulate reference RTL and a supplied candidate with the required
interface. Return distinct statuses for compile failure, simulation failure, timeout and functional
pass/fail. Record failing inputs and expected versus actual outputs. A compilation success is not a
functional pass, and simulation is not proof of synthesis.

Generate machine-readable cycle traces or waveform-derived records. Define signal order, widths,
signedness, clock edge, reset polarity/priority and output sampling time. Avoid testbench races. The
model-facing input may contain the public interface and allowed observed input/output signals, not
reference source, hidden test answers, private internal state or answer-bearing metadata.

## 4. Add all five synthetic task families
Start with one verified vertical slice, then extend it. Build a small parameterized generator for each
family, with reference RTL, deterministic corner cases, randomized stimulus and an independent behavioral
checker. Keep the scope deliberately small:
- Combinational logic: a mux or small Boolean/arithmetic block. Cover input combinations or meaningful
  boundary cases.
- Counters: width, reset and enable variations. Cover hold, update and wraparound.
- FSMs: a small explicit state machine with specified transition/output timing. Cover reset, transitions
  and recovery behavior where defined.
- Arbiters: a small fixed-priority arbiter with a documented grant rule. Cover no requests, competing
  requests and priority correctness. Do not claim fairness for fixed priority.
- Simple protocols: one small ready/valid handshake block with documented buffering and reset behavior.
  Cover backpressure, stable data while stalled, and no loss, duplication or reordering.

Reuse a common harness where it removes duplication, but do not build a generic hardware-generation
framework. Make each family's behavior explicit enough to check by hand. If any family cannot be
completed, report it as missing rather than quietly narrowing the milestone.

## 5. Verify the testbenches, not just the RTL
For every family, the correct reference must pass and deliberately broken candidates must fail. Include
meaningful mutations such as wrong reset, off-by-one count, wrong FSM transition, reversed priority or
dropped/duplicated handshake data. Also test syntax errors, simulation errors and a deliberately
nonterminating run so failure classification is checked.

Keep visible observation traces separate from hidden test stimulus. Use independent seeds and additional
corner cases for hidden tests. Do not rely only on an oracle generated by the same logic as the reference
implementation. Add an independent behavioral model and leave representative trace examples for manual
inspection. Re-run fixed seeds and confirm reproducible artifacts/results. Test that split assignment and
deduplication behave as documented.

Do not fabricate passing results, counts, coverage, completed work or performance claims. If tools are
missing, record the exact blocker and what was not executed.

## 6. Document, commit and push
Leave a short README with setup, one end-to-end smoke command, the full test command, dataset
generation/evaluation commands, record schema, timing conventions, split/dedup rules, license notes and
limitations. Use actual commands from the implementation, not placeholders in the finished README.

Run the documented tests from a clean temporary output directory and inspect the diff for secrets,
unrelated edits, large artifacts and accidentally committed private evaluation data. Add generated
outputs to ignore rules where appropriate. Commit only this work to the approved feature branch, with a
plain factual message. Push only to the confirmed existing remote/branch. Do not force-push, merge to
main, change repository visibility or overwrite someone else's work. Verify the remote branch contains the
commit. If push fails, keep the local commit and report the error; do not say it was pushed.

## Definition of done
One documented command generates a small reproducible dataset covering all five families, produces
observed signals, and evaluates supplied RTL on separate hidden tests. Reference modules pass; deliberate
bugs fail; compile errors and timeouts are classified correctly. Ingestion, dedup and split tests pass.
Setup and limitations are documented. The tested commit is on the approved remote feature branch, or the
push blocker is stated explicitly.

## Handoff
List existing versus new work, changed paths, exact commands run, tool versions, actual test
counts/results by family, a sample record, commit hash, branch and verified push status. Link to the
commit if available. Include failures and remaining gaps. Give a factual completed/partial/missing
checklist against this scope. Do not describe planned work as completed.

## Scope stop
Stop after the CPU pipeline milestone and report what is ready for baseline training. Model, hardware and
training-budget choices stay open for the next stage.
