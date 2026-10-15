"""Up counter of width W, optionally with an enable.

On a rising edge: if rst, q becomes 0 (reset wins over enable); else if en (or always, without an
enable), q becomes q + 1 modulo 2^W (all ones wraps to zero); otherwise q holds.
"""
from . import header, port, reset_rows

NAME = "counter"
GROUPS = [{"W": w, "enable": e} for w in (3, 4, 8) for e in (True, False)]


def ports(p):
    return [port("clk", "input"), port("rst", "input")] + ([port("en", "input")] if p["enable"] else []) + \
           [port("q", "output", p["W"])]


def bugs(p):
    b = ["reset_to_one", "wraps_one_early", "async_reset"]
    return b + (["ignores_enable", "enable_beats_reset"] if p["enable"] else [])


def rtl(p, bug=None):
    W, MAX = p["W"], (1 << p["W"]) - 1
    step = "q <= (q == %d'd%d) ? %d'd0 : q + 1'b1;" % (W, MAX - 1, W) if bug == "wraps_one_early" else \
           "q <= q + 1'b1;  // all ones + 1 wraps to zero"
    reset = "q <= %d'd1;" % W if bug == "reset_to_one" else "q <= %d'd0;" % W
    edge = "posedge clk or posedge rst" if bug == "async_reset" else "posedge clk"
    if not p["enable"]:
        logic = ("        if (rst)\n            %s\n"
                 "        else\n            %s\n") % (reset, step)
    elif bug == "ignores_enable":
        logic = ("        if (rst)\n            %s\n"
                 "        else\n            %s\n") % (reset, step)
    elif bug == "enable_beats_reset":
        logic = ("        if (en)\n            %s\n"
                 "        else if (rst)\n            %s\n") % (step, reset)
    else:
        logic = ("        if (rst)              // synchronous reset, wins over enable\n            %s\n"
                 "        else if (en)\n            %s\n") % (reset, step)
    return header(ports(p), regs={"q"}) + "    always @(%s) begin\n%s    end\nendmodule\n" % (edge, logic)


def _rows(p, pairs):
    """Rows from (rst, en) pairs; the en column is dropped for the no-enable variant."""
    return [dict(rst=r, **({"en": e} if p["enable"] else {})) for r, e in pairs]


def corners(p):
    W = p["W"]
    names = ["en"] if p["enable"] else []
    rows = reset_rows(names)
    rows += _rows(p, [(0, 1)] * ((1 << W) + 3))            # count through wraparound
    rows += _rows(p, [(0, 0)] * 4 + [(0, 1)] * 3)           # hold, then update
    rows += _rows(p, [(1, 1)] * 2 + [(0, 1)] * 5)           # reset and enable together: reset wins
    rows += _rows(p, [(0, 1)] * 3 + [(1, 0)] + [(0, 1)] * 4)  # reset in the middle of a count
    rows += _rows(p, [(0, 1), (0, 0)] * 6)                  # alternate enable
    return rows


def random_rows(p, rng, n):
    rows = reset_rows(["en"] if p["enable"] else [])
    while len(rows) < n:
        rows.append(dict(rst=int(rng.random() < 0.03), **({"en": int(rng.random() < 0.75)} if p["enable"] else {})))
    return rows[:n]


def visible_len(p):
    return min(2 * (1 << p["W"]) + 16, 300)
