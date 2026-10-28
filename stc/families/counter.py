"""Counter of width W, optionally with an enable.

On a rising edge: if rst, q becomes 0 (reset wins over enable); else if en (or always, without an
enable), q becomes q + 1 modulo 2^W (all ones wraps to zero); otherwise q holds.

Wide groups (python3 -m stc.build --wide) add two optional keys. "mod": M counts modulo M instead of
2^W (M - 1 wraps to 0). "down": true counts down instead (0 wraps to M - 1, or to all ones). Reset is 0
in every case. The keys appear only in wide groups, so the original groups keep their names and splits.
"""
from . import header, port, reset_rows

NAME = "counter"
GROUPS = [{"W": w, "enable": e} for w in (3, 4, 8) for e in (True, False)]
WIDE = [dict(x, enable=e) for e in (True, False) for x in
        [{"W": w} for w in (2, 5, 6, 7)] +
        [{"W": w, "down": True} for w in (3, 4, 5, 8)] +
        [{"W": w, "mod": m} for w, m in ((3, 5), (3, 6), (4, 10), (4, 12), (5, 20), (5, 24), (6, 40), (6, 60))] +
        [{"W": w, "mod": m, "down": True} for w, m in ((3, 5), (4, 10), (4, 12), (5, 24))]]


def _wide(p):
    return p not in GROUPS


def period(p):
    return p.get("mod", 1 << p["W"])


def ports(p):
    return [port("clk", "input"), port("rst", "input")] + ([port("en", "input")] if p["enable"] else []) + \
           [port("q", "output", p["W"])]


def bugs(p):
    b = ["reset_to_one", "wraps_one_early", "async_reset"] + (["ignores_modulus"] if "mod" in p else [])
    return b + (["ignores_enable", "enable_beats_reset"] if p["enable"] else [])


def rtl(p, bug=None):
    W, MAX = p["W"], (1 << p["W"]) - 1
    if _wide(p):
        step = _wide_step(p, bug)
    else:
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


def _wide_step(p, bug):
    """The count statement of a wide group. A bug moves the wrap point one step early or ignores M."""
    W, P = p["W"], period(p)
    if bug == "ignores_modulus":
        P = 1 << W
    early = int(bug == "wraps_one_early")
    if p.get("down"):
        if P == 1 << W and not early:
            return "q <= q - 1'b1;  // zero - 1 wraps to all ones"
        return "q <= (q == %d'd0) ? %d'd%d : q - 1'b1;  // zero wraps to %d" % (W, W, P - 1 - early, P - 1)
    if P == 1 << W and not early:
        return "q <= q + 1'b1;  // all ones + 1 wraps to zero"
    return "q <= (q == %d'd%d) ? %d'd0 : q + 1'b1;  // count modulo %d" % (W, P - 1 - early, W, P)


def _rows(p, pairs):
    """Rows from (rst, en) pairs; the en column is dropped for the no-enable variant."""
    return [dict(rst=r, **({"en": e} if p["enable"] else {})) for r, e in pairs]


def corners(p):
    W = p["W"]
    names = ["en"] if p["enable"] else []
    rows = reset_rows(names)
    rows += _rows(p, [(0, 1)] * (period(p) + 3))           # count through wraparound
    rows += _rows(p, [(0, 0)] * 4 + [(0, 1)] * 3)           # hold, then update
    rows += _rows(p, [(1, 1)] * 2 + [(0, 1)] * 5)           # reset and enable together: reset wins
    rows += _rows(p, [(0, 1)] * 3 + [(1, 0)] + [(0, 1)] * 4)  # reset in the middle of a count
    rows += _rows(p, [(0, 1), (0, 0)] * 6)                  # alternate enable
    return rows


def random_rows(p, rng, n):
    rows = reset_rows(["en"] if p["enable"] else [])
    if _wide(p):  # one full period right after reset, so the wrap point is always observed
        rows += _rows(p, [(0, 1)] * (period(p) + 2))
    while len(rows) < n:
        rows.append(dict(rst=int(rng.random() < 0.03), **({"en": int(rng.random() < 0.75)} if p["enable"] else {})))
    return rows[:n]


def visible_len(p):
    if _wide(p):
        return min(period(p) + 64, 320)
    return min(2 * (1 << p["W"]) + 16, 300)
