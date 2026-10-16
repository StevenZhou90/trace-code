# Hard tier: can an agent reverse-engineer RTL from signals?

This is a light test, run on 2026-10-15. The agent was Claude Opus 5.5 (`claude-opus-5-5`), running as
Claude Code headless on Modal, with one attempt per task. The agent got only each task's `public/` folder:
the task text, the observation, and a copy of the harness so it could simulate its own answer. It had
`python3` and `iverilog`, and no web access. Grading ran locally on hidden tests that never left this
machine. A task passes only if every output matches on every checked cycle.

## The tasks

Tier 1 lives in `hard/designs.py` and tier 2 in `hard/designs2.py`. Each design has hand-written
reference RTL, an independent Python model, deliberate bugs, visible stimulus and hidden stimulus.

| task | what is hidden from the agent |
|---|---|
| `bucket_clean` | Token-bucket limiter, with only `req` and `grant` visible: capacity, starting tokens, refill period, refill and spend in the same cycle |
| `lock_clean` | 5-digit combination lock: the code, the restart-on-first-digit rule, 3 strikes, a 20-cycle lockout, a 6-cycle unlock, and keys ignored while open or locked |
| `cpu_clean` | 4-register machine with 16 opcodes, a shift-in immediate load and zero-flag rules |
| `cache_clean` | 4-way, 8-set cache with a single `hit` output: scrambled set and tag bits, lowest-free fill, tree pseudo-LRU |
| `mcu_clean` | 16-byte program memory and an accumulator machine: 8 opcodes, sign-extended add, one empty cycle after a taken jump, loads and XORs from program memory, writes ignored while busy |
| `crcrx_clean` | Serial receiver: start bit, LSB-first bytes, length byte from 1 to 15, bit stuffing after five 1s, CRC-8 (polynomial 0x07, initial value 0), and the error rules |
| `*_capture` | The same designs as a logic-analyzer capture. Every port bit is a separate 1-bit channel in shuffled order, with no names. The clock has jitter at about 7.35 samples per cycle. Inputs have skew and outputs have delay. There are single-sample glitches, and the capture starts after power-on. The agent must also find the clock, the reset and its polarity, and the bus grouping and bit order. |

`hard/build.py` checks every task before an agent sees it:
1. The reference matches the model on the visible and hidden stimulus.
2. Every bug fails the hidden tests.
3. Every bug can be told apart from the reference on the visible observation, after the first reset that
   the observation shows.
4. For capture tasks, a channel-level wrapper around the reference passes the channel-level grader.

A separate decoder I wrote, which finds the clock, filters glitches and samples before each rising edge,
recovers the capture bits with 0 mismatches. The one exception is `mcu_capture`, with 1 bit out of
130,185 wrong. I looked at that case: a clock glitch next to an edge fooled the simple decoder, and the
capture itself is consistent there.

## Results

| task | result | failing rows | turns | cost | wall time |
|---|---|---|---|---|---|
| `bucket_clean` | pass | 0 / 928 | 8 | $0.23 | 1 min |
| `lock_clean` | pass | 0 / 1017 | 11 | $0.35 | 2 min |
| `handshake_capture` | pass | 0 / 641 | 21 | $0.62 | 3 min |
| `cpu_clean` | pass | 0 / 1251 | 14 | $0.59 | 3 min |
| `lock_capture` | pass | 0 / 1017 | 40 | $1.86 | 11 min |
| `cpu_capture` | pass | 0 / 1251 | 125 | $10.39 | 69 min |
| `cache_clean` | pass | 0 / 1621 | 16 | $0.45 | 2 min |
| `mcu_clean` | pass | 0 / 2585 | 41 | $1.94 | 8 min |
| `crcrx_clean` (first version) | pass | 0 / 3426 | 16 | $0.55 | 3 min |
| `crcrx_capture` (first version) | **fail** | 208 / 3426 | 34 | $1.62 | 8 min |
| `mcu_capture` | pass | 0 / 2585 | (reported as 1) | $14.86 | 57 min |
| `crcrx_clean` (fixed) | pass | 0 / 3426 | 14 | $0.47 | 2 min |
| `crcrx_capture` (fixed) | pass | 0 / 3426 | 35 | $1.72 | 9 min |

The reported total for all 13 runs is $35.65. A first `cpu_capture` run was cancelled by a connection
error in the local Modal client. Whatever it spent is not counted.

### The one failure was a task defect

The first `crcrx_capture` failed because the visible stimulus only had valid lengths 1 to 12, while the
hidden tests had a length-15 frame. The agent noticed the gap and said so in its final message. It
guessed that 13 to 15 are errors. The agent on the clean version guessed 15 and happened to be right.

Changing that one constant in the failing answer from 12 to 15 makes it pass, with 0 of 3,426 rows wrong.
So the agent recovered the rest of the protocol from the capture: the clock, the reset, the bit order of
the data bus, the stuffing, the CRC and the error rules.

The fix: the visible lengths now cover 1 to 15, and a new bug, `length_12_max`, makes the visibility
check prove that lengths 13 to 15 appear in the observation. Both receiver tasks were rebuilt and run
again, and both passed (the two "fixed" rows above).

## What this says

- Opus 5.5 solved all 11 tasks once each task's behavior was fully shown in its observation. Each task
  got one attempt, and the defective receiver task got one more attempt after the fix.
- Clean traces with hidden state took 1 to 8 minutes. Captures cost 2 to 25 times more, with the largest
  capture tasks at about an hour and $10 to $15.
- Its final notes reliably named what the observation could not settle. The one failure was exactly such
  a named guess. The CPU agents also pointed out that bytes `0x74` to `0x7F` never appear in that task.
- These tasks are not "months of human work". A careful engineer could probably do each one in a day or
  a few days. Making tasks harder needs longer hidden state (memory, multi-cycle protocols, timeouts),
  behavior that shows up only rarely, and observations with less redundancy.

## Lessons for building tasks

- **A mutant can be equivalent.** Two cache bugs could never change a hit or miss, and the build caught
  both: filling free ways from the top mirrors the tree, and every tree bit is rewritten before a victim
  is needed. They were dropped.
- **The visibility check only covers the bugs you list.** The length-limit gap went through until a bug
  for that boundary existed. Every numeric limit and every unused encoding needs its own boundary bug,
  or a coverage rule.
- **Stated noise rules must hold exactly.** The first renderer could put two glitches next to each other,
  which breaks the "single-sample glitches" promise in the task text. It now keeps glitches at least 3
  samples apart. That changed the tier-1 `cpu_capture` file after it had been run; the run used the older
  file.
- **Do not trust the reported turn count.** Claude Code reported 1 turn for `mcu_capture`, after 57 minutes
  of tool use. The cost and time figures are the reliable ones.

## Reproduce

```
python3 -m hard.build --out out/hard --tier 1
python3 -m hard.build --out out/hard2 --tier 2
modal run modal/run_agent.py --tasks all                        # tier 1
STC_TASKS=hard2 modal run modal/run_agent.py --tasks all        # tier 2
```

The runner uses the Modal secret `anthropic-secret`. Results, transcripts and answers go to
`results/hard/<timestamp>/`, which git ignores. `out/` holds the private hidden tests, and git ignores it
too.
