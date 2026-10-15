"""Overlapping serial sequence detector with a Moore output.

State S<i> means the last i bits of din equal the first i bits of the pattern (the longest such i).
On a rising edge the state moves on din; rst returns to S0. y is 1 exactly while the state is S<L>,
which is the cycle after the last pattern bit was sampled. Overlaps count: for 1011, the input
1011011 makes y high twice.
"""
from . import header, port, reset_rows

NAME = "fsm"
GROUPS = [{"pattern": s} for s in ("1011", "1101", "110", "1001")]


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


def _bug_table(pattern, bug):
    nxt = [r[:] for r in table(pattern)]
    L = len(pattern)
    if bug == "wrong_transition":      # S2 on its advancing bit falls back to S0 instead of S3
        nxt[2][int(pattern[2])] = 0
    elif bug == "no_overlap":          # after a match, start over as if nothing had been seen
        nxt[L] = [1 if pattern[0] == b else 0 for b in "01"]
    return nxt


def bugs(p):
    s = p["pattern"]
    out = ["wrong_transition", "mealy_output", "reset_to_s1"]
    if _bug_table(s, "no_overlap") != table(s):  # only a bug when the pattern can overlap itself
        out.insert(1, "no_overlap")
    return out


def rtl(p, bug=None):
    s = p["pattern"]
    L = len(s)
    nxt = _bug_table(s, bug)
    sw = max(1, L.bit_length())
    lines = ["    // S<i>: the last i bits of din match the first i bits of %s." % s,
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
