"""Ready/valid buffer of depth D (1 or 2) carrying W-bit words.

in_ready  = fewer than D words are stored (it never depends on out_ready).
out_valid = at least one word is stored; out_data = the oldest stored word.
On a rising edge: if rst, the buffer empties; else the oldest word leaves when out_valid && out_ready,
and in_data enters when in_valid && in_ready (both can happen in one cycle). Words leave in the order
they entered, each exactly once, and out_data does not change while out_valid is high and out_ready low.
With D = 1 the block passes at most one word every two cycles.
Wide groups (python3 -m stc.build --wide) add more word widths.
"""
from . import header, port, reset_rows

NAME = "handshake"
GROUPS = [{"D": d, "W": w} for d in (1, 2) for w in (4, 8)]
WIDE = [{"D": d, "W": w} for d in (1, 2) for w in (1, 2, 3, 5, 6, 12, 16)]
FRESH = [{"D": d, "W": w} for d in (1, 2) for w in (7, 10)]


def sample(rng):
    """A random group for procedural training data (python3 -m stc.build --proc)."""
    return {"D": rng.choice([1, 2]), "W": rng.randint(1, 16)}


def ports(p):
    W = p["W"]
    return [port("clk", "input"), port("rst", "input"), port("in_valid", "input"), port("in_data", "input", W),
            port("out_ready", "input"), port("in_ready", "output"), port("out_valid", "output"),
            port("out_data", "output", W)]


def bugs(p):
    return ["drop_word", "duplicate_word", "unstable_data", "reset_keeps_data"]


def rtl(p, bug=None):
    D, W = p["D"], p["W"]
    head = header(ports(p))
    reset = "            ;  // (bug) reset does not empty the buffer" if bug == "reset_keeps_data" else None
    late = "        if (in_valid) mem0 <= in_data;  // (bug) head overwritten while stalled\n" \
        if bug == "unstable_data" else ""
    if D == 1:
        ready = "1'b1" if bug == "drop_word" else "!full"
        clear = "full <= 1'b1;" if bug == "duplicate_word" else "full <= 1'b0;"
        return head + (
            "    reg [%d:0] mem0;\n"
            "    reg full;\n"
            "    assign in_ready  = %s;\n"
            "    assign out_valid = full;\n"
            "    assign out_data  = mem0;\n"
            "    wire push = in_valid && !full;      // a word enters at this rising edge\n"
            "    wire pop  = full && out_ready;      // the stored word leaves at this rising edge\n"
            "    always @(posedge clk) begin\n"
            "        if (rst)\n%s\n"
            "        else if (push) begin\n"
            "            mem0 <= in_data;\n"
            "            full <= 1'b1;\n"
            "        end else if (pop)\n"
            "            %s\n"
            "%s"
            "    end\n"
            "endmodule\n") % (W - 1, ready, reset or "            full <= 1'b0;", clear, late)
    both = "count <= 2'd0;  // (bug) the incoming word is lost" if bug == "drop_word" else "mem0 <= in_data;"
    pop_count = "if (count == 2'd1) count <= 2'd0;  // (bug) count stays 2" if bug == "duplicate_word" \
        else "count <= count - 2'd1;"
    return head + (
        "    // Two-entry queue: mem0 is always the oldest word, mem1 the next one.\n"
        "    reg [%d:0] mem0, mem1;\n"
        "    reg [1:0] count;\n"
        "    wire push = in_valid && in_ready;   // a word enters at this rising edge\n"
        "    wire pop  = out_valid && out_ready; // the oldest word leaves at this rising edge\n"
        "    assign in_ready  = (count != 2'd2);\n"
        "    assign out_valid = (count != 2'd0);\n"
        "    assign out_data  = mem0;\n"
        "    always @(posedge clk) begin\n"
        "        if (rst)\n%s\n"
        "        else begin\n"
        "            case ({push, pop})\n"
        "                2'b10: begin\n"
        "                    if (count == 2'd0) mem0 <= in_data; else mem1 <= in_data;\n"
        "                    count <= count + 2'd1;\n"
        "                end\n"
        "                2'b01: begin\n"
        "                    mem0 <= mem1;\n"
        "                    %s\n"
        "                end\n"
        "                2'b11: %s  // only possible with count 1\n"
        "                default: ;\n"
        "            endcase\n"
        "        end\n"
        "%s"
        "    end\n"
        "endmodule\n") % (W - 1, reset or "            count <= 2'd0;", pop_count, both, late)


def _row(rst=0, v=0, d=0, r=0):
    return {"rst": rst, "in_valid": v, "in_data": d, "out_ready": r}


def corners(p):
    D, MAX = p["D"], (1 << p["W"]) - 1
    rows = reset_rows(["in_valid", "in_data", "out_ready"])
    rows += [_row(v=1, d=(3 * i + 1) & MAX) for i in range(D + 3)]       # fill under backpressure
    rows += [_row(v=1, d=(7 * i + 2) & MAX) for i in range(6)]           # long stall, input keeps changing
    rows += [_row(r=1) for _ in range(D + 2)]                            # drain in order
    rows += [_row(v=1, d=(5 * i + 3) & MAX, r=1) for i in range(8)]      # stream with push and pop together
    rows += [_row(v=1, d=MAX, r=0), _row(v=1, d=0, r=0), _row(rst=1, v=1, d=9 & MAX), _row(r=1), _row(r=1)]  # reset while full
    rows += [_row(v=i % 2, d=i & MAX, r=(i // 2) % 2) for i in range(12)]  # alternating valid and ready
    return rows


def random_rows(p, rng, n):
    rows = reset_rows(["in_valid", "in_data", "out_ready"])
    ready_p = 0.5
    while len(rows) < n:
        if rng.random() < 0.1:  # switch between bursty backpressure and free flow
            ready_p = rng.choice([0.1, 0.5, 0.9])
        rows.append(_row(rst=int(rng.random() < 0.02), v=int(rng.random() < 0.6),
                         d=rng.randrange(1 << p["W"]), r=int(rng.random() < ready_p)))
    return rows[:n]


def visible_len(p):
    return 80
