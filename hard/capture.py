"""Render clean cycle rows as a messy logic-analyzer capture.

What the capture hides or degrades (all deterministic from the rng):
  - every port bit is its own channel ch00..chNN, in shuffled order; which channel is the clock, which
    is the reset, and which bits form a bus are not given. Only each channel's direction is given.
  - samples every 4 ns; the clock period is about 29.4 ns with per-cycle jitter and duty-cycle wobble,
    so there is no whole number of samples per cycle.
  - inputs change near the falling edge with per-bit skew; outputs change after the rising edge with a
    fixed per-bit delay plus jitter.
  - single-sample glitches on any channel.
  - the capture starts some cycles after power-on (the first reset is not shown) and stops early.

Timing model (row k of the clean trace, matching stc/sim.py): inputs of row k are applied around the
falling edge that starts row k; the rising edge in the middle of row k updates state; outputs of row k
(a function of the state after the rising edge of row k-1) are visible from that edge plus a delay.
"""
SAMPLE_NS = 4.0
PERIOD_NS = 29.4


def channels(ports, rng):
    """[(channel name, port name, bit, dir)] in shuffled order."""
    bits = [(p["name"], b, p["dir"]) for p in ports for b in range(p["width"])]
    rng.shuffle(bits)
    return [("ch%02d" % i, name, b, d) for i, (name, b, d) in enumerate(bits)]


def render(ports, clock, rows, outs, rng, start_row, end_row, glitch=0.0015):
    """Return (chans, csv_text). rows: input dicts per row (no clock); outs: output lists per row
    (port order, values may be "x")."""
    chans = channels(ports, rng)
    out_ports = [p for p in ports if p["dir"] == "output"]
    n = len(rows)
    # edge times
    fall, rise, t = [], [], 0.0
    for k in range(n + 1):
        per = PERIOD_NS * (1 + rng.gauss(0, 0.02))
        fall.append(t)
        rise.append(t + per * (0.5 + rng.uniform(-0.04, 0.04)))
        t += per
    events = {}  # channel -> [(time, value)]
    for ch, name, b, d in chans:
        ev = []
        if name == clock:
            for k in range(n):
                ev += [(fall[k], 0), (rise[k], 1)]
        elif d == "input":
            skew = rng.uniform(-0.1, 0.1) * PERIOD_NS
            for k in range(n):
                ev.append((fall[k] + skew + rng.uniform(-0.03, 0.03) * PERIOD_NS, (rows[k][name] >> b) & 1))
        else:
            j = [p["name"] for p in out_ports].index(name)
            delay = PERIOD_NS * rng.uniform(0.08, 0.2)
            power_on = rng.randrange(2)
            for k in range(n):
                v = outs[k][j]
                bit = power_on if v == "x" else (v >> b) & 1
                tk = (rise[k - 1] if k > 0 else fall[0]) + delay + rng.uniform(0, 0.02) * PERIOD_NS
                ev.append((tk, bit))
        ev.sort()
        events[ch] = ev
    t0, t1 = fall[start_row], fall[end_row]
    lines = ["t_ns," + ",".join(c[0] for c in chans)]
    idx = {c[0]: 0 for c in chans}
    cur = {c[0]: events[c[0]][0][1] for c in chans}
    ts = t0
    while ts < t1:
        vals = []
        for ch, *_ in chans:
            ev = events[ch]
            while idx[ch] < len(ev) and ev[idx[ch]][0] <= ts:
                cur[ch] = ev[idx[ch]][1]
                idx[ch] += 1
            v = cur[ch]
            if rng.random() < glitch:
                v ^= 1
            vals.append(str(v))
        lines.append("%.1f,%s" % (ts - t0, ",".join(vals)))
        ts += SAMPLE_NS
    return chans, "\n".join(lines) + "\n"


def to_channel_rows(chans, ports, rows, expected):
    """Map clean cycle-level stimulus and expected outputs onto 1-bit channel ports for grading."""
    out_names = [p["name"] for p in ports if p["dir"] == "output"]
    in_chans = [c for c in chans if c[3] == "input"]
    out_chans = [c for c in chans if c[3] == "output"]
    stim = []
    for r in rows:
        stim.append({ch: (r[name] >> b) & 1 for ch, name, b, d in in_chans if name in r})
    exp = []
    for e in expected:
        row = []
        for ch, name, b, d in out_chans:
            v = e[out_names.index(name)]
            row.append(None if v is None else (v >> b) & 1)
        exp.append(row)
    return stim, exp
