"""Overlapping serial sequence detector with a Moore output.

State S<i> means the last i bits of din equal the first i bits of the pattern (the longest such i).
On a rising edge the state moves on din; rst returns to S0. y is 1 exactly while the state is S<L>,
which is the cycle after the last pattern bit was sampled. Overlaps count: for 1011, the input
1011011 makes y high twice.

Wide groups (python3 -m stc.build --wide) use every 3- to 5-bit pattern, and add the key
"overlap": false for 4-bit patterns: after a match, detection starts over from the next bit, so the
bits of one match are never reused. 1011011 then makes y high once.
"""
from . import header, port, reset_rows

NAME = "fsm"
GROUPS = [{"pattern": s} for s in ("1011", "1101", "110", "1001")]
_ALL = [format(v, "0%db" % n) for n in (3, 4, 5) for v in range(1 << n)]
WIDE = [{"pattern": s} for s in _ALL if {"pattern": s} not in GROUPS] + \
       [{"pattern": s, "overlap": False} for s in _ALL if len(s) == 4]  # filtered below


def ports(p):
    return [port("clk", "input"), port("rst", "input"), port("din", "input"), port("y", "output")]


def table(pattern):
    """next[i][bit] for states 0..L: the longest prefix of the pattern that ends the bits seen so far."""
    L = len(pattern)
    nxt = []
    for i in range(L + 1):
        row = []
        for bit in "01":
            seen = pattern[:i] + bit
            row.append(max(k for k in range(min(L, len(seen)) + 1) if seen.endswith(pattern[:k])))
        nxt.append(row)
    return nxt


def restart(pattern):
    """The match state's row when overlaps are not allowed: only the new bit counts."""
    return [1 if pattern[0] == b else 0 for b in "01"]


def _bug_table(pattern, bug, overlap=True):
    nxt = [r[:] for r in table(pattern)]
    L = len(pattern)
    if not overlap:
        nxt[L] = restart(pattern)
    if bug == "wrong_transition":      # S2 on its advancing bit falls back to S0 instead of S3
        nxt[2][int(pattern[2])] = 0
    elif bug == "no_overlap":          # after a match, start over as if nothing had been seen
        nxt[L] = restart(pattern)
    elif bug == "overlaps":            # (non-overlapping groups) reuses the bits of the last match
        nxt[L] = table(pattern)[L]
    return nxt


def bugs(p):
    s = p["pattern"]
    out = ["wrong_transition", "mealy_output", "reset_to_s1"]
    if not p.get("overlap", True):
        return out[:1] + ["overlaps"] + out[1:]
    if _bug_table(s, "no_overlap") != table(s):  # only a bug when the pattern can overlap itself
        out.insert(1, "no_overlap")
    return out


def rtl(p, bug=None):
    s = p["pattern"]
    L = len(s)
    nxt = _bug_table(s, bug, p.get("overlap", True))
    sw = max(1, L.bit_length())
    lines = ["    // S<i>: the last i bits of din match the first i bits of %s." % s] + \
            (["    // No overlap: after a match, only the next bit counts toward a new one."]
             if not p.get("overlap", True) else []) + [
             "    localparam [%d:0] %s;" % (sw - 1, ", ".join("S%d = %d'd%d" % (i, sw, i) for i in range(L + 1))),
             "    reg [%d:0] state, next;" % (sw - 1),
             "    always @* begin",
             "        case (state)"]
    for i in range(L + 1):
        lines.append("            S%d: next = din ? S%d : S%d;" % (i, nxt[i][1], nxt[i][0]))
    lines += ["            default: next = S0;", "        endcase", "    end",
              "    always @(posedge clk) begin",
              "        if (rst)",
              "            state <= %s;" % ("S1" if bug == "reset_to_s1" else "S0"),
              "        else",
              "            state <= next;",
              "    end"]
    if bug == "mealy_output":  # fires one cycle early, from the last bit itself
        lines.append("    assign y = (state == S%d) && (din == 1'b%s);" % (L - 1, s[-1]))
    else:
        lines.append("    assign y = (state == S%d);  // Moore: high the cycle after the last bit" % L)
    return header(ports(p)) + "\n".join(lines) + "\nendmodule\n"


def rtl_shift(p):
    """The same detector written as a shift register of the last L bits compared with the pattern.

    Behaves exactly like rtl(p): a match is the last L bits equal to the pattern, counting only bits seen
    since reset (and, without overlap, since the last match). The pattern appears literally, oldest bit
    first, so reading it off a trace is enough to write the design. Used as a training answer style."""
    s = p["pattern"]
    L = len(s)
    overlap = p.get("overlap", True)
    cw = max(1, (L - 1).bit_length())
    lines = ["    // y is 1 the cycle after the last %d bits of din were %s (oldest first)." % (L, s),
             "    // Bits count toward a match only after reset%s." % ("" if overlap else
                                                                    " and, with no overlap, after the last match"),
             "    reg [%d:0] hist;  // earlier bits of din, the newest in bit 0" % (L - 1),
             "    reg [%d:0] seen;  // how many of them count, up to %d" % (cw - 1, L - 1),
             "    reg y_r;",
             "    wire [%d:0] now = {hist[%d:0], din};" % (L - 1, L - 2),
             "    wire hit = (seen == %d'd%d) && (now == %d'b%s);" % (cw, L - 1, L, s),
             "    always @(posedge clk) begin",
             "        if (rst) begin",
             "            seen <= %d'd0;" % cw,
             "            y_r <= 1'b0;",
             "        end else begin",
             "            hist <= now;",
             "            y_r <= hit;",
             ("            seen <= (seen == %d'd%d) ? seen : seen + %d'd1;" % (cw, L - 1, cw) if overlap else
              "            seen <= hit ? %d'd0 : (seen == %d'd%d) ? seen : seen + %d'd1;" % (cw, cw, L - 1, cw)),
             "        end",
             "    end",
             "    assign y = y_r;"]
    return header(ports(p)) + "\n".join(lines) + "\nendmodule\n"


def _bits(text):
    return [{"rst": 0, "din": int(c)} for c in text]


def corners(p):
    s = p["pattern"]
    L = len(s)
    near = s[:-1] + ("0" if s[-1] == "1" else "1")
    rows = reset_rows(["din"])
    rows += _bits(s + "00")                    # one clean match
    rows += _bits(s + s[1:] + s + "0")         # back-to-back and overlapping matches
    rows += _bits(near + s + "0")              # near miss, then recovery
    rows += _bits("1" * 8 + "0" * 8 + s + "0")  # long runs
    for i in range(L + 1):                     # reset while in every state, then a full match
        rows += _bits(s[:i]) + reset_rows(["din"], 1) + _bits(s + "0")
    rows += reset_rows(["din"], 1) + _bits(s[1:] + "00")  # pattern without its first bit: no match
    return rows


def random_rows(p, rng, n):
    s = p["pattern"]
    rows = reset_rows(["din"])
    while len(rows) < n:
        if rng.random() < 0.15:                # plant a match now and then so the output is exercised
            rows += _bits(s)
        else:
            rows.append({"rst": int(rng.random() < 0.02), "din": rng.randrange(2)})
    return rows[:n]


def visible_len(p):
    return 96


# A non-overlapping group is a separate design only when the pattern can overlap itself.
WIDE = [p for p in WIDE if p.get("overlap", True) or restart(p["pattern"]) != table(p["pattern"])[len(p["pattern"])]]

# Fresh held-out groups: ten 6-bit patterns (longer than any other group) and four 5-bit patterns
# without overlap. Chosen by a fixed seed.
import random as _random
FRESH = [{"pattern": s} for s in _random.Random("fresh").sample([format(v, "06b") for v in range(64)], 10)] + \
        [p for p in ({"pattern": s, "overlap": False} for s in _random.Random("fresh5").sample(
            [format(v, "05b") for v in range(32)], 12)) if restart(p["pattern"]) != table(p["pattern"])[5]][:4]


def sample(rng):
    """A random group for procedural training data (python3 -m stc.build --proc)."""
    n = rng.randint(3, 6)
    p = {"pattern": format(rng.randrange(1 << n), "0%db" % n)}
    if rng.random() < 0.3 and restart(p["pattern"]) != table(p["pattern"])[n]:
        p["overlap"] = False
    return p
