"""Combinational blocks (no clock, no reset). The trace still has one row per step.

mux4:    y = d<sel>          (sel = 0..3 picks d0..d3)
add_sat: y = min(a + b, 2^W - 1)   (unsigned saturating add)

Wide groups only (python3 -m stc.build --wide):
sub_sat:  y = max(a - b, 0)        (unsigned saturating subtract)
max, min: y = the larger / smaller of a and b, compared as unsigned
popcount: y = number of 1 bits in a (y has just enough bits to hold W)
gray:     y = a ^ (a >> 1)         (binary to Gray code)
"""
from . import header, port

NAME = "comb"
GROUPS = [{"op": "mux4", "W": 4}, {"op": "mux4", "W": 8}, {"op": "add_sat", "W": 4}, {"op": "add_sat", "W": 8}]
WIDE = [{"op": "mux4", "W": w} for w in (1, 2, 3, 5, 6, 7)] + [{"op": "add_sat", "W": w} for w in (2, 3, 5, 6, 7)] + \
       [{"op": op, "W": w} for op in ("sub_sat", "max", "min", "popcount", "gray") for w in (2, 3, 4, 5, 6, 8)]
FRESH = [{"op": op, "W": 7} for op in ("sub_sat", "max", "min", "popcount", "gray")]
TWO_INPUT = ("add_sat", "sub_sat", "max", "min")


def sample(rng):
    """A random group for procedural training data (python3 -m stc.build --proc)."""
    op = rng.choice(["mux4", "add_sat", "sub_sat", "max", "min", "popcount", "gray"])
    return {"op": op, "W": rng.randint(1 if op == "mux4" else 2, 8)}


def ports(p):
    W = p["W"]
    if p["op"] == "mux4":
        return [port("d0", "input", W), port("d1", "input", W), port("d2", "input", W), port("d3", "input", W),
                port("sel", "input", 2), port("y", "output", W)]
    if p["op"] == "popcount":
        return [port("a", "input", W), port("y", "output", W.bit_length())]
    if p["op"] == "gray":
        return [port("a", "input", W), port("y", "output", W)]
    return [port("a", "input", W), port("b", "input", W), port("y", "output", W)]


BUGS = {"mux4": ["swapped_select_bits", "sel3_gives_d2"], "add_sat": ["no_saturation", "limit_off_by_one"],
        "sub_sat": ["no_saturation", "swapped_operands"], "max": ["returns_min", "signed_compare"],
        "min": ["returns_max", "signed_compare"], "popcount": ["ignores_msb", "counts_zeros"],
        "gray": ["shift_wrong_way", "drops_msb"]}


def bugs(p):
    return BUGS[p["op"]]


def rtl(p, bug=None):
    W, MAX = p["W"], (1 << p["W"]) - 1
    if p["op"] == "mux4":
        sel = "{sel[0], sel[1]}" if bug == "swapped_select_bits" else "sel"
        last = "d2" if bug == "sel3_gives_d2" else "d3"
        body = ("    always @* begin\n"
                "        case (%s)\n"
                "            2'd0: y = d0;\n"
                "            2'd1: y = d1;\n"
                "            2'd2: y = d2;\n"
                "            default: y = %s;\n"
                "        endcase\n"
                "    end\n") % (sel, last)
        return header(ports(p), regs={"y"}) + body + "endmodule\n"
    if p["op"] != "add_sat":
        return _wide_rtl(p, bug)
    body = "    wire [%d:0] sum = a + b;  // one extra bit keeps the carry\n" % W
    if bug == "no_saturation":
        body += "    assign y = sum[%d:0];\n" % (W - 1)
    elif bug == "limit_off_by_one":
        body += "    assign y = (sum > %d) ? %d'd%d : sum[%d:0];\n" % (MAX + 1, W, MAX, W - 1)
    else:
        body += "    assign y = sum[%d] ? %d'd%d : sum[%d:0];  // carry out means the sum passed 2^W - 1\n" % (W, W, MAX, W - 1)
    return header(ports(p)) + body + "endmodule\n"


def _wide_rtl(p, bug):
    W, op = p["W"], p["op"]
    if op == "popcount":
        top = W - 1 if bug == "ignores_msb" else W
        bit = "!a[i]" if bug == "counts_zeros" else "a[i]"
        body = ("    integer i;\n"
                "    always @* begin\n"
                "        y = 0;\n"
                "        for (i = 0; i < %d; i = i + 1)\n"
                "            y = y + %s;\n"
                "    end\n") % (top, bit)
        return header(ports(p), regs={"y"}) + body + "endmodule\n"
    if op == "gray":
        expr = "a ^ (a << 1)" if bug == "shift_wrong_way" else "a ^ (a >> 1)"
        if bug == "drops_msb":
            expr = "{1'b0, a[%d:0] ^ a[%d:1]}" % (W - 2, W - 1)
        return header(ports(p)) + "    assign y = %s;  // binary to Gray code\n" % expr + "endmodule\n"
    if op == "sub_sat":
        x, z = ("b", "a") if bug == "swapped_operands" else ("a", "b")
        expr = "a - b" if bug == "no_saturation" else "(%s > %s) ? %s - %s : %d'd0" % (x, z, x, z, W)
        return header(ports(p)) + "    assign y = %s;  // unsigned, floors at zero\n" % expr + "endmodule\n"
    cmp = ">" if op == "max" else "<"
    if bug in ("returns_min", "returns_max"):
        cmp = "<" if cmp == ">" else ">"
    cond = "$signed(a) %s $signed(b)" % cmp if bug == "signed_compare" else "a %s b" % cmp
    return header(ports(p)) + "    assign y = (%s) ? a : b;  // unsigned compare\n" % cond + "endmodule\n"


def corners(p):
    W, MAX = p["W"], (1 << p["W"]) - 1
    if p["op"] == "mux4":
        rows = []
        for pattern in ([1, 2, 3, 4], [MAX, 0, MAX, 0], [0, MAX, 0, MAX], [0x5 & MAX, 0xA & MAX, MAX, 0]):
            for s in range(4):
                rows.append({"d0": pattern[0] & MAX, "d1": pattern[1] & MAX, "d2": pattern[2] & MAX,
                             "d3": pattern[3] & MAX, "sel": s})  # masked for narrow words
        return rows
    if p["op"] in ("popcount", "gray"):  # every input value
        return [{"a": a} for a in range(MAX + 1)]
    if W <= 4:  # every input pair
        return [{"a": a, "b": b} for a in range(MAX + 1) for b in range(MAX + 1)]
    h = 1 << (W - 1)
    pairs = [(0, 0), (MAX, 0), (0, MAX), (MAX, MAX), (MAX - 1, 1), (MAX, 1), (1, MAX), (h, h - 1), (h, h),
             (h, h + 1), (MAX - 1, 0), (MAX - 1, 2), (2, MAX - 1), (1, 1)]
    return [{"a": a, "b": b} for a, b in pairs]


def random_rows(p, rng, n):
    return [{q["name"]: rng.randrange(1 << q["width"]) for q in ports(p) if q["dir"] == "input"} for _ in range(n)]


def visible_len(p):
    return 48
