"""Combinational blocks (no clock, no reset). The trace still has one row per step.

mux4:    y = d<sel>          (sel = 0..3 picks d0..d3)
add_sat: y = min(a + b, 2^W - 1)   (unsigned saturating add)
"""
from . import header, port

NAME = "comb"
GROUPS = [{"op": "mux4", "W": 4}, {"op": "mux4", "W": 8}, {"op": "add_sat", "W": 4}, {"op": "add_sat", "W": 8}]


def ports(p):
    W = p["W"]
    if p["op"] == "mux4":
        return [port("d0", "input", W), port("d1", "input", W), port("d2", "input", W), port("d3", "input", W),
                port("sel", "input", 2), port("y", "output", W)]
    return [port("a", "input", W), port("b", "input", W), port("y", "output", W)]


def bugs(p):
    return ["swapped_select_bits", "sel3_gives_d2"] if p["op"] == "mux4" else ["no_saturation", "limit_off_by_one"]


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
    body = "    wire [%d:0] sum = a + b;  // one extra bit keeps the carry\n" % W
    if bug == "no_saturation":
        body += "    assign y = sum[%d:0];\n" % (W - 1)
    elif bug == "limit_off_by_one":
        body += "    assign y = (sum > %d) ? %d'd%d : sum[%d:0];\n" % (MAX + 1, W, MAX, W - 1)
    else:
        body += "    assign y = sum[%d] ? %d'd%d : sum[%d:0];  // carry out means the sum passed 2^W - 1\n" % (W, W, MAX, W - 1)
    return header(ports(p)) + body + "endmodule\n"


def corners(p):
    W, MAX = p["W"], (1 << p["W"]) - 1
    if p["op"] == "mux4":
        rows = []
        for pattern in ([1, 2, 3, 4], [MAX, 0, MAX, 0], [0, MAX, 0, MAX], [0x5 & MAX, 0xA & MAX, MAX, 0]):
            for s in range(4):
                rows.append({"d0": pattern[0], "d1": pattern[1], "d2": pattern[2], "d3": pattern[3], "sel": s})
        return rows
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
