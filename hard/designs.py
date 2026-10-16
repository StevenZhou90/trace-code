"""Hidden-state designs for the hard tier. Each design is a dict with:

  name, ports (in declaration order), clock, reset (name, active level)
  rtl(bug=None)          reference Verilog, or a named deliberate bug
  bugs                   bug names
  model(rows)            independent Python model -> expected output rows (None = don't care)
  visible(rng, n)        stimulus for the observation trace
  hidden(rng)            stimulus for the hidden tests (corner cases + random)

All outputs are registered (Moore): row k shows the state after rising edge k-1, so a trace can be
rendered as a real-time capture without knowing anything about combinational paths.
"""
from stc.families import handshake as hs_family
from stc.models import handshake as hs_model


def port(name, direction, width=1):
    return {"name": name, "dir": direction, "width": width, "signed": False}


# --------------------------------------------------------------------------------------------- lock
# A 5-digit combination lock with a wrong-key counter and timed lockout.
#   code 7, 2, E, 2, 9. A key press is key_valid high; presses are ignored while unlocked or locked out.
#   Correct digit: advance. After the 5th digit: unlocked for 6 cycles, progress and wrong-key count clear.
#   Wrong digit: progress becomes 1 if the key is the first code digit (7), else 0; the wrong-key count
#   goes up, and on the 3rd wrong key the lock alarms for 20 cycles and the count clears.
#   rst_n is synchronous and active low.
LOCK_CODE = [7, 2, 14, 2, 9]
LOCK_OPEN, LOCK_OUT, LOCK_FAILS = 6, 20, 3


def lock_rtl(bug=None):
    code = list(LOCK_CODE)
    if bug == "wrong_code_digit":
        code[3] = 3
    restart = "3'd0" if bug == "restart_always_zero" else "((key == 4'd7) ? 3'd1 : 3'd0)"
    out_len = LOCK_OUT - 1 if bug == "lockout_one_short" else LOCK_OUT
    open_len = LOCK_OPEN + 1 if bug == "unlock_one_long" else LOCK_OPEN
    last_fail = 3 if bug == "four_strikes" else 2
    gate = "key_valid && lock_t == 5'd0" if bug == "keys_counted_while_open" else \
        "key_valid && lock_t == 5'd0 && open_t == 3'd0"
    on_open = "p <= 3'd0; open_t <= 3'd%d;" % open_len if bug == "success_keeps_fails" else \
        "p <= 3'd0; fails <= 2'd0; open_t <= 3'd%d;" % open_len
    rst_body = "p <= 3'd0; lock_t <= 5'd0; open_t <= 3'd0;" if bug == "reset_keeps_fails" else \
        "p <= 3'd0; fails <= 2'd0; lock_t <= 5'd0; open_t <= 3'd0;"
    return f"""module dut (
    input  wire       clk,
    input  wire       rst_n,
    input  wire [3:0] key,
    input  wire       key_valid,
    output wire       unlocked,
    output wire       alarm
);
    reg [2:0] p;        // code digits matched so far
    reg [1:0] fails;    // wrong keys since the last success or lockout
    reg [4:0] lock_t;   // lockout cycles left; alarm while nonzero
    reg [2:0] open_t;   // unlocked cycles left
    reg [3:0] digit;    // the digit expected next
    always @* begin
        case (p)
            3'd0: digit = 4'd{code[0]};
            3'd1: digit = 4'd{code[1]};
            3'd2: digit = 4'd{code[2]};
            3'd3: digit = 4'd{code[3]};
            default: digit = 4'd{code[4]};
        endcase
    end
    assign unlocked = (open_t != 3'd0);
    assign alarm    = (lock_t != 5'd0);
    always @(posedge clk) begin
        if (!rst_n) begin
            {rst_body}
        end else begin
            if (lock_t != 5'd0) lock_t <= lock_t - 5'd1;
            if (open_t != 3'd0) open_t <= open_t - 3'd1;
            if ({gate}) begin
                if (key == digit) begin
                    if (p == 3'd4) begin
                        {on_open}
                    end else
                        p <= p + 3'd1;
                end else begin
                    p <= {restart};
                    if (fails == 2'd{last_fail}) begin
                        fails <= 2'd0;
                        lock_t <= 5'd{out_len};
                    end else
                        fails <= fails + 2'd1;
                end
            end
        end
    end
endmodule
"""


def lock_model(rows):
    st, out = None, []
    for r in rows:
        out.append([None, None] if st is None else [int(st["open"] > 0), int(st["lock"] > 0)])
        if not r["rst_n"]:
            st = {"p": 0, "fails": 0, "lock": 0, "open": 0}
            continue
        if st is None:
            continue
        accept = r["key_valid"] and st["lock"] == 0 and st["open"] == 0
        nxt = dict(st, lock=max(0, st["lock"] - 1), open=max(0, st["open"] - 1))
        if accept:
            if r["key"] == LOCK_CODE[st["p"]]:
                if st["p"] == 4:
                    nxt.update(p=0, fails=0, open=LOCK_OPEN)
                else:
                    nxt["p"] = st["p"] + 1
            else:
                nxt["p"] = 1 if r["key"] == LOCK_CODE[0] else 0
                if st["fails"] + 1 == LOCK_FAILS:
                    nxt.update(fails=0, lock=LOCK_OUT)
                else:
                    nxt["fails"] = st["fails"] + 1
        st = nxt
    return out


def _press(k, gap=0):
    return [{"rst_n": 1, "key": k, "key_valid": 1}] + [{"rst_n": 1, "key": k, "key_valid": 0}] * gap


def lock_rows(rng, n, planted):
    """Random presses mixed with planted episodes: correct codes, near misses, a wrong key equal to the
    first digit followed by the rest of the code, strike-outs, presses during unlock and lockout."""
    rows = [{"rst_n": 0, "key": 0, "key_valid": 0}] * 2
    while len(rows) < n:
        u = rng.random()
        if u < planted:
            kind = rng.choice(["code", "code", "near", "restart7", "strikeout", "code_then_press", "reset"])
            if kind == "code":
                for k in LOCK_CODE:
                    rows += _press(k, rng.choice([0, 0, 1, 3]))
            elif kind == "near":
                cut = rng.randrange(1, 5)
                for k in LOCK_CODE[:cut]:
                    rows += _press(k, rng.choice([0, 1]))
                rows += _press(rng.choice([x for x in range(16) if x != LOCK_CODE[cut]]))
            elif kind == "restart7":  # 7 2 7 2 E 2 9: the wrong 7 restarts progress at 1
                for k in [7, 2, 7, 2, 14, 2, 9]:
                    rows += _press(k, rng.choice([0, 1]))
            elif kind == "strikeout":
                for _ in range(3):
                    rows += _press(rng.choice([1, 3, 5, 8]), rng.choice([0, 2]))
                for _ in range(rng.randrange(6, 26)):  # keep pressing through the lockout
                    rows += _press(LOCK_CODE[0], rng.choice([0, 1]))
            elif kind == "code_then_press":
                for k in LOCK_CODE:
                    rows += _press(k)
                for _ in range(rng.randrange(3, 9)):
                    rows += _press(rng.randrange(16))
            else:
                for _ in range(rng.choice([1, 2])):
                    rows.append({"rst_n": 0, "key": rng.randrange(16), "key_valid": rng.randrange(2)})
        else:
            rows.append({"rst_n": 1, "key": rng.randrange(16), "key_valid": int(rng.random() < 0.45)})
    return rows[:n]


def lock_hidden(rng):
    rows = [{"rst_n": 0, "key": 0, "key_valid": 0}] * 2
    for k in LOCK_CODE:                                   # clean open
        rows += _press(k)
    rows += _press(3) * 8                                 # presses while open, then a strike-out
    for _ in range(3):
        rows += _press(0)
    rows += _press(7) * 25                                # lockout length, presses ignored
    rows += [{"rst_n": 1, "key": 0, "key_valid": 0}] * 3
    for k in [7, 2, 7, 2, 14, 2, 9]:                      # restart on a wrong 7
        rows += _press(k)
    rows += [{"rst_n": 1, "key": 0, "key_valid": 0}] * 8
    for k in [1, 2] + LOCK_CODE:                          # two wrong keys, then a success clears them
        rows += _press(k)
    rows += [{"rst_n": 1, "key": 0, "key_valid": 0}] * 8
    rows += _press(5) + _press(6)
    rows += [{"rst_n": 1, "key": 0, "key_valid": 0}] * 7
    rows += _press(4)                                     # third strike only if fails survived the open
    rows += [{"rst_n": 1, "key": 0, "key_valid": 0}] * 25  # wait out the lockout
    rows += _press(1) + _press(1) + [{"rst_n": 0, "key": 0, "key_valid": 0}] + _press(1)
    rows += [{"rst_n": 1, "key": 0, "key_valid": 0}] * 3   # reset must clear the wrong-key count
    return rows + lock_rows(rng, 900, 0.25)


LOCK = {
    "name": "lock", "clock": "clk", "reset": ("rst_n", 0),
    "ports": [port("clk", "input"), port("rst_n", "input"), port("key", "input", 4), port("key_valid", "input"),
              port("unlocked", "output"), port("alarm", "output")],
    "rtl": lock_rtl, "model": lock_model,
    "bugs": ["wrong_code_digit", "restart_always_zero", "lockout_one_short", "unlock_one_long", "four_strikes",
             "keys_counted_while_open", "success_keeps_fails", "reset_keeps_fails"],
    "visible": lambda rng, n: lock_rows(rng, n, 0.06), "hidden": lock_hidden,
    "describe": "a small keypad-controlled block",
}


# -------------------------------------------------------------------------------------------- bucket
# Token-bucket rate limiter. Capacity 5 tokens, 3 after reset. A free-running counter adds one token
# every 7 cycles (when the counter wraps from 6 to 0) unless the bucket is full. At each rising edge,
# grant becomes 1 if req is high and at least one token is left (that token is spent), else 0.
# A refill and a spend in the same cycle both happen. rst is synchronous and active high.
B_CAP, B_START, B_PERIOD = 5, 3, 7


def bucket_rtl(bug=None):
    cap = B_CAP + 1 if bug == "capacity_six" else B_CAP
    start = B_CAP if bug == "starts_full" else B_START
    last = B_PERIOD - 2 if bug == "period_six" else B_PERIOD - 1
    cnt_next = "(refill || take) ? 3'd0 : cnt + 3'd1" if bug == "counter_restarts_on_grant" else \
        "refill ? 3'd0 : cnt + 3'd1"
    take = "req && (tokens != 3'd0 || refill)" if bug == "spend_sees_refill" else "req && (tokens != 3'd0)"
    return f"""module dut (
    input  wire clk,
    input  wire rst,
    input  wire req,
    output reg  grant
);
    reg [2:0] tokens;
    reg [2:0] cnt;                       // free-running refill timer
    wire refill = (cnt == 3'd{last});
    wire take   = {take};
    wire [2:0] after_take = tokens - (take ? 3'd1 : 3'd0);
    always @(posedge clk) begin
        if (rst) begin
            tokens <= 3'd{start};
            cnt    <= 3'd0;
            grant  <= 1'b0;
        end else begin
            cnt    <= {cnt_next};
            grant  <= take;
            tokens <= (refill && after_take < 3'd{cap}) ? after_take + 3'd1 : after_take;
        end
    end
endmodule
"""


def bucket_model(rows):
    st, out = None, []
    for r in rows:
        out.append([None if st is None else st["grant"]])
        if r["rst"]:
            st = {"tokens": B_START, "cnt": 0, "grant": 0}
            continue
        if st is None:
            continue
        take = bool(r["req"]) and st["tokens"] > 0
        tokens = st["tokens"] - int(take)
        if st["cnt"] == B_PERIOD - 1:
            tokens = min(B_CAP, tokens + 1)
            cnt = 0
        else:
            cnt = st["cnt"] + 1
        st = {"tokens": tokens, "cnt": cnt, "grant": int(take)}
    return out


def bucket_rows(rng, n):
    rows = [{"rst": 1, "req": 0}] * 2
    mode = 0.5
    while len(rows) < n:
        if rng.random() < 0.06:
            mode = rng.choice([0.0, 0.2, 0.5, 0.9, 1.0])
        if rng.random() < 0.004:
            rows.append({"rst": 1, "req": rng.randrange(2)})
        elif rng.random() < 0.01:  # long idle fills the bucket, then a burst shows its capacity
            rows += [{"rst": 0, "req": 0}] * rng.randrange(36, 60) + [{"rst": 0, "req": 1}] * rng.randrange(8, 14)
        else:
            rows.append({"rst": 0, "req": int(rng.random() < mode)})
    return rows[:n]


def bucket_hidden(rng):
    rows = [{"rst": 1, "req": 0}] * 2
    rows += [{"rst": 0, "req": 1}] * 30           # drain from the reset level, then steady refill rate
    rows += [{"rst": 0, "req": 0}] * 50           # fill to capacity
    rows += [{"rst": 0, "req": 1}] * 20           # burst equals capacity
    rows += [{"rst": 1, "req": 1}] + [{"rst": 0, "req": 1}] * 10
    for gap in range(1, 10):                      # requests at every spacing
        rows += ([{"rst": 0, "req": 1}] + [{"rst": 0, "req": 0}] * gap) * 4
    return rows + bucket_rows(rng, 600)


BUCKET = {
    "name": "bucket", "clock": "clk", "reset": ("rst", 1),
    "ports": [port("clk", "input"), port("rst", "input"), port("req", "input"), port("grant", "output")],
    "rtl": bucket_rtl, "model": bucket_model,
    "bugs": ["capacity_six", "starts_full", "period_six", "counter_restarts_on_grant", "spend_sees_refill"],
    "visible": bucket_rows, "hidden": bucket_hidden,
    "describe": "a block that grants or refuses requests",
}


# ----------------------------------------------------------------------------------------------- cpu
# A tiny register machine. Four 8-bit registers r0..r3, a zero flag z. When valid is high, instr runs at
# the rising edge; op = instr[7:4], d = instr[3:2], s = instr[1:0]:
#   0 NOP        1 MOV rd=rs      2 ADD rd+=rs     3 SUB rd-=rs     4 AND rd&=rs     5 XOR rd^=rs
#   6 SHL rd <<= (s+1)            7 OUT: out=rs, out_valid=1 for one cycle
#   8..B LDN: instr = 10 dd nnnn, rd = (rd << 4) | nnnn    (dd = instr[5:4])
#   C INC rd     D DEC rd         E CMP: z = (rd == rs), no write    F NOT rd = ~rd
# z = (result == 0) after ADD SUB AND XOR SHL INC DEC NOT; set by CMP as above; unchanged otherwise.
# out holds its last value; out_valid is 1 only in the cycle after an OUT. rst clears everything.
CPU_ALU_Z = {2, 3, 4, 5, 6, 12, 13, 15}


def cpu_rtl(bug=None):
    sub = "b - a" if bug == "sub_reversed" else "a - b"
    shl = "a << s" if bug == "shl_by_s" else "a << (s + 3'd1)"
    ldn = "{4'd0, imm}" if bug == "ldn_no_shift" else "{r[ld][3:0], imm}"
    inc_z = "" if bug == "inc_keeps_z" else "setz = 1'b1;"
    cmp_z = "z <= (a != b);" if bug == "cmp_inverted" else "z <= (a == b);"
    out_src = "a" if bug == "out_uses_rd" else "b"
    mov_z = "setz = 1'b1;" if bug == "mov_sets_z" else ""
    return f"""module dut (
    input  wire       clk,
    input  wire       rst,
    input  wire [7:0] instr,
    input  wire       valid,
    output reg  [7:0] out,
    output reg        out_valid,
    output reg        z
);
    reg  [7:0] r [0:3];
    wire [3:0] op  = instr[7:4];
    wire [1:0] d   = instr[3:2];
    wire [1:0] s   = instr[1:0];
    wire [1:0] ld  = instr[5:4];        // LDN destination
    wire [3:0] imm = instr[3:0];        // LDN nibble
    wire [7:0] a = r[d];
    wire [7:0] b = r[s];
    reg  [7:0] res;
    reg        wr, setz;
    always @* begin
        res = a; wr = 1'b0; setz = 1'b0;
        case (op)
            4'h1: begin res = b; wr = 1'b1; {mov_z} end
            4'h2: begin res = a + b; wr = 1'b1; setz = 1'b1; end
            4'h3: begin res = {sub}; wr = 1'b1; setz = 1'b1; end
            4'h4: begin res = a & b; wr = 1'b1; setz = 1'b1; end
            4'h5: begin res = a ^ b; wr = 1'b1; setz = 1'b1; end
            4'h6: begin res = {shl}; wr = 1'b1; setz = 1'b1; end
            4'hC: begin res = a + 8'd1; wr = 1'b1; {inc_z} end
            4'hD: begin res = a - 8'd1; wr = 1'b1; setz = 1'b1; end
            4'hF: begin res = ~a; wr = 1'b1; setz = 1'b1; end
            default: ;
        endcase
    end
    integer i;
    always @(posedge clk) begin
        if (rst) begin
            for (i = 0; i < 4; i = i + 1) r[i] <= 8'd0;
            z <= 1'b0; out <= 8'd0; out_valid <= 1'b0;
        end else begin
            out_valid <= 1'b0;
            if (valid) begin
                if (op[3:2] == 2'b10)
                    r[ld] <= {ldn};
                else if (op == 4'h7) begin
                    out <= {out_src};
                    out_valid <= 1'b1;
                end else if (op == 4'hE)
                    {cmp_z}
                else begin
                    if (wr) r[d] <= res;
                    if (setz) z <= (res == 8'd0);
                end
            end
        end
    end
endmodule
"""


def cpu_model(rows):
    st, out_rows = None, []
    for row in rows:
        out_rows.append([None, None, None] if st is None else [st["out"], st["ov"], st["z"]])
        if row["rst"]:
            st = {"r": [0, 0, 0, 0], "z": 0, "out": 0, "ov": 0}
            continue
        if st is None:
            continue
        r, z, out = list(st["r"]), st["z"], st["out"]
        ov = 0
        if row["valid"]:
            ins = row["instr"]
            op, d, s = ins >> 4, (ins >> 2) & 3, ins & 3
            a, b = r[d], r[s]
            if op >> 2 == 2:
                ld = (ins >> 4) & 3
                r[ld] = ((r[ld] << 4) | (ins & 15)) & 255
            elif op == 7:
                out, ov = b, 1
            elif op == 14:
                z = int(a == b)
            elif op != 0:
                res = {1: b, 2: a + b, 3: a - b, 4: a & b, 5: a ^ b, 6: a << (s + 1), 12: a + 1, 13: a - 1,
                       15: ~a}[op] & 255
                r[d] = res
                if op in CPU_ALU_Z:
                    z = int(res == 0)
        st = {"r": r, "z": z, "out": out, "ov": ov}
    return out_rows


def cpu_rows(rng, n, out_rate=0.3):
    """Random instruction stream. LDN and OUT are common so register contents stay visible."""
    rows = [{"rst": 1, "instr": 0, "valid": 0}] * 2
    while len(rows) < n:
        if rng.random() < 0.003:
            rows.append({"rst": 1, "instr": rng.randrange(256), "valid": rng.randrange(2)})
            continue
        u = rng.random()
        if u < out_rate:
            ins = 0x70 | rng.randrange(4)                                # OUT rs
        elif u < out_rate + 0.25:
            ins = 0x80 | (rng.randrange(4) << 4) | rng.randrange(16)     # LDN
        else:
            op = rng.choice([0, 1, 2, 3, 4, 5, 6, 12, 13, 14, 15])
            ins = (op << 4) | rng.randrange(16)
        rows.append({"rst": 0, "instr": ins, "valid": int(rng.random() < 0.9)})
    return rows[:n]


def cpu_hidden(rng):
    rows = [{"rst": 1, "instr": 0, "valid": 0}] * 2
    def run(*ins):
        return [{"rst": 0, "instr": i, "valid": 1} for i in ins]
    # every op on edge values: 0x00, 0xFF, 0x80, overflow, shift amounts 1..4, CMP equal and not equal
    rows += run(0xBF, 0xBF, 0x9F, 0x90, 0x88, 0x80, 0x71, 0x72, 0x73, 0x70)   # r3=FF r1=F0 r0=80
    rows += run(0x2C, 0x73, 0x3D, 0x73, 0x60, 0x70, 0x61, 0x70, 0x62, 0x70, 0x63, 0x70)
    rows += run(0xE5, 0xEF, 0xC8, 0x72, 0xD8, 0x72, 0xD8, 0x72, 0xFC, 0x73, 0xF0, 0x70)
    rows += run(0x45, 0x71, 0x55, 0x71, 0x15, 0x71, 0x1E, 0x72, 0x00, 0x00)
    rows += [{"rst": 0, "instr": 0x7F, "valid": 0}] * 3                     # invalid cycles do nothing
    rows += [{"rst": 1, "instr": 0xC0, "valid": 1}] + run(0x70, 0x71)        # reset wins over an instruction
    return rows + cpu_rows(rng, 1200, 0.3)


CPU = {
    "name": "cpu", "clock": "clk", "reset": ("rst", 1),
    "ports": [port("clk", "input"), port("rst", "input"), port("instr", "input", 8), port("valid", "input"),
              port("out", "output", 8), port("out_valid", "output"), port("z", "output")],
    "rtl": cpu_rtl, "model": cpu_model,
    "bugs": ["sub_reversed", "shl_by_s", "ldn_no_shift", "inc_keeps_z", "cmp_inverted", "out_uses_rd", "mov_sets_z"],
    "visible": cpu_rows, "hidden": cpu_hidden,
    "describe": "a block that takes an 8-bit command stream",
}


# ----------------------------------------------------------------------------------------- handshake
# The milestone's 2-entry ready/valid buffer, reused as a calibration target for the capture tier.
HS_P = {"D": 2, "W": 8}
HANDSHAKE = {
    "name": "handshake", "clock": "clk", "reset": ("rst", 1),
    "ports": hs_family.ports(HS_P),
    "rtl": lambda bug=None: hs_family.rtl(HS_P, bug), "model": lambda rows: hs_model(HS_P, rows),
    "bugs": hs_family.bugs(HS_P),
    "visible": lambda rng, n: hs_family.random_rows(HS_P, rng, n),
    "hidden": lambda rng: hs_family.corners(HS_P) + hs_family.random_rows(HS_P, rng, 600),
    "describe": "a block that moves data words between two sides",
}

DESIGNS = {d["name"]: d for d in (LOCK, BUCKET, CPU, HANDSHAKE)}
