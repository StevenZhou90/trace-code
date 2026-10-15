# /goal message draft

Paste the block below after `/goal`. Fill in the remote and branch first (marked REMOTE and BRANCH).

```
Build the CPU-only signal-to-code data and grading pipeline milestone in /Users/stevenzhou/Development/phinity/trace-code, then make a four-page slide deck of what was actually done.

Read these first and follow them: docs/BRIEF.md (the full milestone brief, the source of truth), docs/SPEC.md (the fixed design decisions: timing rule, statuses, record schema, families, mutants, dedup and split rules), docs/CHECKLIST.md (the definition of done, to be filled in with real proof), docs/SLIDES.md (the deck plan). You may read ../signal-to-code/ for reusable ideas but must not change it.

The goal is done only when all of these are true and proven by commands whose output you read:
1. One documented command builds a small reproducible dataset covering all five families (comb, counter, fsm, arbiter, handshake) with public observed traces, training-target reference RTL, and separate private hidden tests; a second command evaluates a supplied candidate on the hidden tests.
2. For every family the reference passes, every listed mutant fails, and a syntax error, a runtime or interface error, and a non-terminating design are each classified with their own status by the Icarus harness. Hidden expected outputs come from an independent Python model, and the reference RTL agrees with it on every row.
3. Ingestion of project-owned fixtures, rejection with reasons, exact and normalized dedup, group-based splits, public-data leak checks, and a same-seed rebuild giving identical hashes all have passing unittest tests.
4. The README has setup, the real smoke command, the full test command, build and evaluate commands, record schema, timing conventions, split and dedup rules, license notes, limitations, and a note that the code was written with an AI coding agent.
5. docs/CHECKLIST.md is filled in with real counts per family and marks anything incomplete as partial or missing.
6. The work is committed in a git repository in trace-code with a plain factual message (author steven@phinity.ai), the diff was checked for secrets, large files, private evaluation data and personal names, and it is pushed to REMOTE on branch BRANCH and the remote branch was checked to contain the commit. If the push fails, keep the local commit and report the exact error instead.
7. docs/slides/deck.pdf exists: four pages, built from the real results with generated waveform and result-matrix images, each page rendered and looked at for layout problems.

Rules: standard library Python plus Icarus Verilog only; small plain files, no frameworks; no model training, GPUs, diffusion or reinforcement learning code; no fabricated numbers; no personal names anywhere; do not force-push, merge to main, create a new repository or change visibility. Finish with the handoff described at the end of docs/BRIEF.md.
```
