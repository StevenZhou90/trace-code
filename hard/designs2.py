"""Tier-2 hidden-state designs: deeper state, fewer outputs. Same dict shape as hard/designs.py.

cache   4-way set-associative hit/miss tracker, 8 sets, tree pseudo-LRU, scrambled index bits; one output.
mcu     16-byte program memory + accumulator machine with a taken-jump bubble; only out/busy visible.
crcrx   serial frame receiver: start bit, length byte, bit stuffing, CRC-8; data and frame-status pulses.
"""
from .designs import port


# --------------------------------------------------------------------------------------------- cache
# addr[0] is the byte offset (ignored). set = {addr[5], addr[2], addr[1]}, tag = {addr[7], addr[6], addr[4], addr[3]}.
# On req: hit if a valid way in the set holds the tag. On a miss the line is filled into the lowest-numbered
# invalid way, or, if all 4 are valid, the tree pseudo-LRU victim. Every access (hit or fill) points the tree
# away from the way used. Tree bits per set: b0 = 0 -> victim among ways 0/1, 1 -> among ways 2/3;
# b1 = 0 -> way 0 else way 1; b2 = 0 -> way 2 else way 3. rst or flush clears all valid bits and tree bits.
# hit (registered) is 1 in the cycle after a request that hit, else 0.

def cache_fields(addr, bug=None):
    a = [(addr >> i) & 1 for i in range(8)]
    if bug == "index_bits_low":
        return (addr >> 1) & 7, addr >> 4
    s = (a[5] << 2) | (a[2] << 1) | a[1]
    t = (a[7] << 3) | (a[6] << 2) | (a[4] << 1) | (a[0] if bug == "tag_uses_offset" else a[3])
    return s, t


def cache_rtl(bug=None):
    if bug == "index_bits_low":
        set_t, tag_t = "addr[3:1]", "addr[7:4]"
    else:
        set_t = "{addr[5], addr[2], addr[1]}"
        tag_t = "{addr[7], addr[6], addr[4], addr[0]}" if bug == "tag_uses_offset" else "{addr[7], addr[6], addr[4], addr[3]}"
    victim = "plru[set][0] ? (plru[set][1] ? 2'd1 : 2'd0) : (plru[set][2] ? 2'd3 : 2'd2)" if bug == "root_inverted" else \
        "plru[set][0] ? (plru[set][2] ? 2'd3 : 2'd2) : (plru[set][1] ? 2'd1 : 2'd0)"
    slot = "found ? way_hit : victim" if bug == "victim_ignores_free" else "found ? way_hit : (has_free ? free_way : victim)"
    free_loop = "for (w = 0; w < 4; w = w + 1)" if bug == "highest_free_first" else "for (w = 3; w >= 0; w = w - 1)"
    touch = "if (req && !found)" if bug == "hit_does_not_touch" else "if (req)"
    clear = "for (i = 0; i < 8; i = i + 1) plru[i] <= 3'd0;" if bug != "flush_keeps_tree" else \
        "if (rst) for (i = 0; i < 8; i = i + 1) plru[i] <= 3'd0;"
    return f"""module dut (
    input  wire       clk,
    input  wire       rst,
    input  wire       req,
    input  wire       flush,
    input  wire [7:0] addr,
    output reg        hit
);
    wire [2:0] set = {set_t};
    wire [3:0] tag = {tag_t};
    reg  [3:0] tags [0:31];             // index set*4 + way
    reg [31:0] valid;
    reg  [2:0] plru [0:7];              // [0] root, [1] ways 0/1, [2] ways 2/3
    reg  [1:0] way_hit, free_way, victim, slot;
    reg        found, has_free;
    integer w, i;
    always @* begin
        found = 1'b0; way_hit = 2'd0; has_free = 1'b0; free_way = 2'd0;
        for (w = 0; w < 4; w = w + 1)
            if (valid[set * 4 + w] && tags[set * 4 + w] == tag) begin found = 1'b1; way_hit = w; end
        {free_loop}                     // the last match wins: this picks the lowest free way
            if (!valid[set * 4 + w]) begin has_free = 1'b1; free_way = w; end
        victim = {victim};
        slot = {slot};
    end
    always @(posedge clk) begin
        if (rst || flush) begin
            valid <= 32'd0;
            hit <= 1'b0;
            {clear}
        end else begin
            hit <= req && found;
            if (req && !found) begin
                tags[set * 4 + slot] <= tag;
                valid[set * 4 + slot] <= 1'b1;
            end
            {touch} begin              // point the tree away from the way just used
                plru[set][0] <= (slot < 2'd2);
                if (slot < 2'd2) plru[set][1] <= (slot == 2'd0);
                else            plru[set][2] <= (slot == 2'd2);
            end
        end
    end
endmodule
"""


def cache_model(rows):
    st, out = None, []
    for r in rows:
        out.append([None if st is None else st["hit"]])
        if r["rst"] or r["flush"]:
            st = {"lines": [[None] * 4 for _ in range(8)], "tree": [[0, 0, 0] for _ in range(8)], "hit": 0}
            continue
        if st is None:
            continue
        hit = 0
        if r["req"]:
            s, t = cache_fields(r["addr"])
            ways, tree = st["lines"][s], st["tree"][s]
            if t in ways:
                use, hit = ways.index(t), 1
            elif None in ways:
                use = ways.index(None)
                ways[use] = t
            else:
                use = (2 + tree[2]) if tree[0] else tree[1]
                ways[use] = t
            tree[0] = int(use < 2)
            if use < 2:
                tree[1] = int(use == 0)
            else:
                tree[2] = int(use == 2)
        st["hit"] = hit
    return out


def cache_rows(rng, n):
    rows = [{"rst": 1, "req": 0, "flush": 0, "addr": 0}] * 2
    hot = [rng.randrange(256) for _ in range(rng.randrange(10, 22))]
    while len(rows) < n:
        if rng.random() < 0.05:
            hot[rng.randrange(len(hot))] = rng.randrange(256)
        if rng.random() < 0.004:
            rows.append({"rst": 0, "req": rng.randrange(2), "flush": 1, "addr": rng.randrange(256)})
            continue
        if rng.random() < 0.02:  # a burst of conflicting lines in one set shows the replacement order
            s = rng.randrange(8)
            lines = [a for a in range(256) if cache_fields(a)[0] == s and a % 2 == 0]
            pick = rng.sample(lines, 6)
            for a in [rng.choice(pick) for _ in range(rng.randrange(8, 20))]:
                rows.append({"rst": 0, "req": 1, "flush": 0, "addr": a | rng.randrange(2)})
            continue
        a = rng.choice(hot) if rng.random() < 0.85 else rng.randrange(256)
        rows.append({"rst": 0, "req": int(rng.random() < 0.75), "flush": 0, "addr": a})
    return rows[:n]


def cache_hidden(rng):
    rows = [{"rst": 1, "req": 0, "flush": 0, "addr": 0}] * 2
    for s in range(8):  # fill every set, evict in tree order, re-touch, evict again
        lines = [a for a in range(0, 256, 2) if cache_fields(a)[0] == s][:7]
        for a in lines[:4] + [lines[0], lines[2]] + lines[4:7] + lines[:4] + [lines[1] | 1]:
            rows.append({"rst": 0, "req": 1, "flush": 0, "addr": a})
    rows.append({"rst": 0, "req": 1, "flush": 1, "addr": 0})
    rows += [{"rst": 0, "req": 1, "flush": 0, "addr": a} for a in (0, 2, 0, 1, 3, 255, 254)]
    return rows + cache_rows(rng, 1500)


CACHE = {
    "name": "cache", "clock": "clk", "reset": ("rst", 1),
    "ports": [port("clk", "input"), port("rst", "input"), port("req", "input"), port("flush", "input"),
              port("addr", "input", 8), port("hit", "output")],
    "rtl": cache_rtl, "model": cache_model,
    # Dropped as equivalent (hit/miss can never differ): "highest_free_first" (filling free ways 3..0 mirrors
    # the tree) and "flush_keeps_tree" (every tree bit is rewritten by the fills before a victim is needed).
    "bugs": ["index_bits_low", "tag_uses_offset", "root_inverted", "victim_ignores_free", "hit_does_not_touch"],
    "visible": cache_rows, "hidden": cache_hidden,
    "describe": "a block that answers 1 or 0 to address requests",
}


# ----------------------------------------------------------------------------------------------- mcu
# 16 x 8-bit program memory, written by we/waddr/wdata only while idle. start (while idle) begins a run:
# busy = 1, pc = 0, acc = 0. While busy, one instruction runs per cycle, except that a taken jump is
# followed by one empty cycle. Writes and start are ignored while busy. ins = mem[pc]:
#   op = ins[7:5], arg = ins[4:0] (5 bits), adr = ins[3:0]
#   0 LDI  acc = arg            1 ADDI acc += sign-extended arg       2 LD   acc = mem[adr]
#   3 IN   acc = in_data        4 OUT  out = acc, out_valid one cycle 5 JNZ  if acc != 0: pc = adr (+1 empty cycle)
#   6 XORM acc ^= mem[adr]      7 HALT busy = 0
# pc counts modulo 16. rst clears memory, pc, acc, busy and the outputs.

def mcu_step(st, r, bug=None):
    """One rising edge. Returns the new state (the model's only definition of behavior)."""
    if r["rst"]:
        return {"mem": [0] * 16, "pc": 0, "acc": 0, "busy": 0, "bubble": 0, "out": 0, "ov": 0}
    st = dict(st, mem=list(st["mem"]), ov=0)
    if not st["busy"]:
        if r["we"]:
            st["mem"][r["waddr"]] = r["wdata"]
        if r["start"]:
            st.update(busy=1, pc=0, acc=0, bubble=0)
        return st
    if st["bubble"]:
        st["bubble"] = 0
        return st
    ins = st["mem"][st["pc"]]
    op, arg, adr = ins >> 5, ins & 31, ins & 15
    nxt = (st["pc"] + 1) % 16
    if op == 0:
        st["acc"] = arg
    elif op == 1:
        st["acc"] = (st["acc"] + (arg - 32 if arg & 16 else arg)) & 255
    elif op == 2:
        st["acc"] = st["mem"][adr]
    elif op == 3:
        st["acc"] = r["in_data"]
    elif op == 4:
        st["out"], st["ov"] = st["acc"], 1
    elif op == 5:
        if st["acc"] != 0:
            nxt, st["bubble"] = adr, 1
    elif op == 6:
        st["acc"] ^= st["mem"][adr]
    else:
        st["busy"] = 0
        nxt = st["pc"]
    st["pc"] = nxt
    return st


def mcu_model(rows):
    st, out = None, []
    for r in rows:
        out.append([None, None, None] if st is None else [st["out"], st["ov"], st["busy"]])
        if r["rst"]:
            st = mcu_step(None, r)
        elif st is not None:
            st = mcu_step(st, r)
    return out


def mcu_rtl(bug=None):
    addi = "acc + {3'b000, arg}" if bug == "addi_zero_extends" else "acc + {{3{arg[4]}}, arg}"
    jcond = "acc == 8'd0" if bug == "jump_on_zero" else "acc != 8'd0"
    bubble = "" if bug == "no_jump_bubble" else "bubble <= 1'b1;"
    in_src = "in_q" if bug == "in_one_cycle_late" else "in_data"
    xorm = "acc + mem[adr]" if bug == "xorm_adds" else "acc ^ mem[adr]"
    idle_cond = "1'b1" if bug == "writes_while_busy" else "!busy"
    start_acc = "" if bug == "start_keeps_acc" else "acc <= 8'd0;"
    return f"""module dut (
    input  wire       clk,
    input  wire       rst,
    input  wire       we,
    input  wire [3:0] waddr,
    input  wire [7:0] wdata,
    input  wire       start,
    input  wire [7:0] in_data,
    output reg  [7:0] out,
    output reg        out_valid,
    output reg        busy
);
    reg  [7:0] mem [0:15];
    reg  [3:0] pc;
    reg  [7:0] acc;
    reg        bubble;                  // the empty cycle after a taken jump
    reg  [7:0] in_q;
    wire [7:0] ins = mem[pc];
    wire [2:0] op  = ins[7:5];
    wire [4:0] arg = ins[4:0];
    wire [3:0] adr = ins[3:0];
    integer i;
    always @(posedge clk) begin
        in_q <= in_data;
        if (rst) begin
            for (i = 0; i < 16; i = i + 1) mem[i] <= 8'd0;
            pc <= 4'd0; acc <= 8'd0; busy <= 1'b0; bubble <= 1'b0; out <= 8'd0; out_valid <= 1'b0;
        end else begin
            out_valid <= 1'b0;
            if ({idle_cond} && we) mem[waddr] <= wdata;
            if (!busy) begin
                if (start) begin busy <= 1'b1; pc <= 4'd0; {start_acc} bubble <= 1'b0; end
            end else if (bubble)
                bubble <= 1'b0;
            else begin
                pc <= pc + 4'd1;
                case (op)
                    3'd0: acc <= {{3'b000, arg}};
                    3'd1: acc <= {addi};
                    3'd2: acc <= mem[adr];
                    3'd3: acc <= {in_src};
                    3'd4: begin out <= acc; out_valid <= 1'b1; end
                    3'd5: if ({jcond}) begin pc <= adr; {bubble} end
                    3'd6: acc <= {xorm};
                    3'd7: begin busy <= 1'b0; pc <= pc; end
                endcase
            end
        end
    end
endmodule
"""


def _program(rng):
    """A random 16-byte program biased toward runs that show behavior: inputs, outputs, countdown loops."""
    prog = []
    for a in range(16):
        u = rng.random()
        if u < 0.14:
            ins = (0 << 5) | rng.randrange(32)
        elif u < 0.30:
            ins = (1 << 5) | rng.randrange(32)
        elif u < 0.38:
            ins = (2 << 5) | rng.randrange(32)
        elif u < 0.50:
            ins = (3 << 5) | rng.randrange(32)
        elif u < 0.72:
            ins = (4 << 5) | rng.randrange(32)
        elif u < 0.82:
            ins = (5 << 5) | (rng.randrange(2) << 4) | rng.randrange(max(1, a + 1))
        elif u < 0.90:
            ins = (6 << 5) | rng.randrange(32)
        else:
            ins = (7 << 5) | rng.randrange(32)
        prog.append(ins)
    if rng.random() < 0.6:
        prog[rng.randrange(10, 16)] = (7 << 5) | rng.randrange(32)
    return prog


def mcu_rows(rng, n, max_run=70):
    idle = lambda **kw: dict({"rst": 0, "we": 0, "waddr": rng.randrange(16), "wdata": rng.randrange(256),
                              "start": 0, "in_data": rng.randrange(256)}, **kw)
    rows = [idle(rst=1), idle(rst=1)]
    st = None
    for r in rows:
        st = mcu_step(st, r)

    def push(r):
        nonlocal st
        rows.append(r)
        st = mcu_step(st, r)

    while len(rows) < n:
        if rng.random() < 0.5 or st["mem"] == [0] * 16:
            prog = _program(rng)
            addrs = list(range(16)) if rng.random() < 0.6 else rng.sample(range(16), rng.randrange(2, 8))
            for a in addrs:
                push(idle(we=1, waddr=a, wdata=prog[a]))
                if rng.random() < 0.1:
                    push(idle())
        push(idle(start=1, we=int(rng.random() < 0.2)))
        for _ in range(max_run):
            if not st["busy"]:
                break
            push(idle(we=int(rng.random() < 0.15), start=int(rng.random() < 0.1)))  # ignored while busy
        if st["busy"]:
            push(idle(rst=1))
        for _ in range(rng.randrange(1, 4)):
            push(idle())
    return rows[:n]


def mcu_hidden(rng):
    rows = []
    def prog_run(prog, cycles, ins=None):
        rws = [{"rst": 0, "we": 1, "waddr": a, "wdata": b, "start": 0, "in_data": 0} for a, b in enumerate(prog)]
        rws.append({"rst": 0, "we": 0, "waddr": 0, "wdata": 0, "start": 1, "in_data": 0})
        rws += [{"rst": 0, "we": 0, "waddr": 0, "wdata": 0, "start": 0, "in_data": (ins or [7])[k % len(ins or [7])]}
                for k in range(cycles)]
        return rws
    rows += [{"rst": 1, "we": 0, "waddr": 0, "wdata": 0, "start": 0, "in_data": 0}] * 2
    # countdown loop: LDI 5; OUT; ADDI -1; JNZ 1; HALT
    rows += prog_run([0x05, 0x80, 0x3F, 0xA1, 0xE0] + [0] * 11, 30)
    # sign extension edge values, IN, XORM/LD on program bytes, OUT of every result, HALT
    rows += prog_run([0x60, 0x80, 0x2F, 0x80, 0x30, 0x80, 0x5F, 0x80, 0xCF, 0x80, 0x4E, 0x80, 0xE0, 0x00, 0xA5, 0x3C],
                     20, [0x80, 0x7F, 0xFF])
    return rows + mcu_rows(rng, 2500)


MCU = {
    "name": "mcu", "clock": "clk", "reset": ("rst", 1),
    "ports": [port("clk", "input"), port("rst", "input"), port("we", "input"), port("waddr", "input", 4),
              port("wdata", "input", 8), port("start", "input"), port("in_data", "input", 8),
              port("out", "output", 8), port("out_valid", "output"), port("busy", "output")],
    "rtl": mcu_rtl, "model": mcu_model,
    "bugs": ["addi_zero_extends", "jump_on_zero", "no_jump_bubble", "in_one_cycle_late", "xorm_adds",
             "writes_while_busy", "start_keeps_acc"],
    "visible": mcu_rows, "hidden": mcu_hidden,
    "describe": "a small programmable block with a load port and a run control",
}


# --------------------------------------------------------------------------------------------- crcrx
# One serial bit per clock on rx. Idle: wait for a 0 (start bit). In a frame, bits are destuffed: after five
# consecutive 1 data bits the next bit must be 0 and is dropped; a 1 there makes the frame bad. Data bits
# form bytes least-significant bit first. Byte 1 is the length L (1..15; 0 or more than 15 makes the frame
# bad). Then L payload bytes, each output on data with a one-cycle data_valid pulse. Then one CRC byte:
# CRC-8, polynomial 0x07, initial value 0x00, no reflection, over the length byte and the payload. A match
# pulses frame_ok, a mismatch pulses frame_bad. Any bad frame returns to idle at once.
CRC_POLY, CRC_INIT = 0x07, 0x00


def crc8(crc, byte, poly=CRC_POLY):
    crc ^= byte
    for _ in range(8):
        crc = ((crc << 1) ^ poly) & 255 if crc & 128 else (crc << 1) & 255
    return crc


def crcrx_model(rows):
    st, out = None, []
    for r in rows:
        out.append([None] * 4 if st is None else [st["data"], st["dv"], st["ok"], st["bad"]])
        if r["rst"]:
            st = {"mode": "idle", "data": 0, "dv": 0, "ok": 0, "bad": 0}
            continue
        if st is None:
            continue
        b = r["rx"]
        st = dict(st, dv=0, ok=0, bad=0)
        if st["mode"] == "idle":
            if b == 0:
                st.update(mode="frame", ones=0, bits=[], phase="len", crc=CRC_INIT, left=0)
            continue
        if st["ones"] == 5:
            if b:
                st.update(bad=1, mode="idle")
            else:
                st["ones"] = 0
            continue
        st["ones"] = st["ones"] + 1 if b else 0
        st["bits"] = st["bits"] + [b]
        if len(st["bits"]) < 8:
            continue
        byte = sum(v << i for i, v in enumerate(st["bits"]))
        st["bits"] = []
        if st["phase"] == "len":
            if byte == 0 or byte > 15:
                st.update(bad=1, mode="idle")
            else:
                st.update(left=byte, crc=crc8(st["crc"], byte), phase="pay")
        elif st["phase"] == "pay":
            st.update(data=byte, dv=1, crc=crc8(st["crc"], byte), left=st["left"] - 1)
            if st["left"] == 0:
                st["phase"] = "crc"
        else:
            st.update(mode="idle", ok=int(byte == st["crc"]), bad=int(byte != st["crc"]))
    return out


def crcrx_rtl(bug=None):
    poly = "8'h31" if bug == "crc_poly_31" else "8'h07"
    init = "8'hFF" if bug == "crc_init_ff" else "8'h00"
    shift = "{sh[6:0], rx}" if bug == "msb_first" else "{rx, sh[7:1]}"
    len_ok = "(nbyte != 8'd0 && nbyte <= 8'd16)" if bug == "length_16_allowed" else "(nbyte != 8'd0 && nbyte <= 8'd15)"
    len_crc = "crc" if bug == "crc_skips_length" else "crc8(crc, nbyte)"
    stuff = "1'b0" if bug == "no_destuffing" else "(ones == 3'd5)"
    viol = "1'b0" if bug == "stuff_violation_ignored" else "rx"
    return f"""module dut (
    input  wire       clk,
    input  wire       rst,
    input  wire       rx,
    output reg  [7:0] data,
    output reg        data_valid,
    output reg        frame_ok,
    output reg        frame_bad
);
    localparam IDLE = 2'd0, LEN = 2'd1, PAY = 2'd2, CHK = 2'd3;
    reg [1:0] state;
    reg [2:0] ones;      // consecutive 1 data bits, for destuffing
    reg [2:0] nbits;     // data bits collected in the current nbyte
    reg [7:0] sh;        // nbyte being collected, first bit ends up in bit 0
    reg [7:0] crc;
    reg [3:0] left;      // payload bytes still to come
    wire [7:0] nbyte = {shift};
    function [7:0] crc8(input [7:0] c, input [7:0] d);
        integer k;
        begin
            crc8 = c ^ d;
            for (k = 0; k < 8; k = k + 1)
                crc8 = crc8[7] ? ((crc8 << 1) ^ {poly}) : (crc8 << 1);
        end
    endfunction
    always @(posedge clk) begin
        data_valid <= 1'b0; frame_ok <= 1'b0; frame_bad <= 1'b0;
        if (rst) begin
            state <= IDLE; data <= 8'd0; ones <= 3'd0; nbits <= 3'd0; sh <= 8'd0; crc <= 8'd0; left <= 4'd0;
        end else if (state == IDLE) begin
            if (!rx) begin state <= LEN; ones <= 3'd0; nbits <= 3'd0; crc <= {init}; end
        end else if ({stuff}) begin
            if ({viol}) begin frame_bad <= 1'b1; state <= IDLE; end   // a 1 where a stuffed 0 belongs
            else ones <= 3'd0;                                        // drop the stuffed 0
        end else begin
            ones <= rx ? ones + 3'd1 : 3'd0;
            sh <= nbyte;
            nbits <= nbits + 3'd1;
            if (nbits == 3'd7) begin                                  // nbyte complete
                case (state)
                    LEN: if ({len_ok}) begin left <= nbyte[3:0]; crc <= {len_crc}; state <= PAY; end
                         else begin frame_bad <= 1'b1; state <= IDLE; end
                    PAY: begin
                        data <= nbyte; data_valid <= 1'b1; crc <= crc8(crc, nbyte);
                        left <= left - 4'd1;
                        if (left == 4'd1) state <= CHK;
                    end
                    default: begin
                        frame_ok <= (nbyte == crc); frame_bad <= (nbyte != crc); state <= IDLE;
                    end
                endcase
            end
        end
    end
endmodule
"""


def frame_bits(rng, length=None, payload=None, corrupt=None):
    """Raw rx bits for one frame (start bit included), optionally corrupted."""
    L = length if length is not None else rng.randrange(1, 13)
    pay = payload if payload is not None else [rng.choice([0xFF, 0x7E, 0x00, rng.randrange(256)]) for _ in range(max(L, 0))]
    crc = CRC_INIT
    for b in [L & 255] + pay:
        crc = crc8(crc, b)
    if corrupt == "crc":
        crc ^= 1 << rng.randrange(8)
    data = []
    for b in [L & 255] + pay[:min(L, 15) if 0 < L <= 15 else 0] + ([crc] if 0 < L <= 15 else []):
        data += [(b >> i) & 1 for i in range(8)]
    bits, ones, viol_at = [0], 0, None
    if corrupt == "stuff":
        viol_at = rng.randrange(len(data))
    for k, d in enumerate(data):
        bits.append(d)
        ones = ones + 1 if d else 0
        if ones == 5:
            bits.append(1 if viol_at is not None and k >= viol_at else 0)
            if viol_at is not None and k >= viol_at:
                break
            ones = 0
    return bits


def crcrx_bits(rng, n_bits):
    bits = [1] * 4
    while len(bits) < n_bits:
        u = rng.random()
        corrupt = "crc" if u < 0.15 else "stuff" if u < 0.22 else None
        length = rng.choice([0, 16, 17, 31]) if 0.22 <= u < 0.28 else None
        bits += frame_bits(rng, length=length, corrupt=corrupt)
        bits += [1] * rng.randrange(1, 12)
    return bits[:n_bits]


def crcrx_rows(rng, n):
    rows = [{"rst": 1, "rx": 1}] * 2
    for b in crcrx_bits(rng, n - 2):
        rows.append({"rst": int(rng.random() < 0.0015), "rx": b})
    return rows


def crcrx_hidden(rng):
    bits = [1] * 3
    bits += frame_bits(rng, 1, [0xFF]) + [1]
    bits += frame_bits(rng, 15, [0xFF] * 15) + [1] * 2                # maximum stuffing
    bits += frame_bits(rng, 3, [0x1F, 0xF8, 0x3E]) + [1]               # runs crossing byte boundaries
    bits += frame_bits(rng, 0) + [1] * 8 + frame_bits(rng, 16) + [1] * 8
    bits += frame_bits(rng, 2, [0x55, 0xAA], corrupt="crc") + [1]
    bits += frame_bits(rng, 4, corrupt="stuff") + [1] * 9
    bits += frame_bits(rng, 2, [0x12, 0x34]) + frame_bits(rng, 1, [0x00])  # back to back, no idle bit
    rows = [{"rst": 1, "rx": 1}] * 2 + [{"rst": 0, "rx": b} for b in bits]
    return rows + crcrx_rows(rng, 3000)


CRCRX = {
    "name": "crcrx", "clock": "clk", "reset": ("rst", 1),
    "ports": [port("clk", "input"), port("rst", "input"), port("rx", "input"), port("data", "output", 8),
              port("data_valid", "output"), port("frame_ok", "output"), port("frame_bad", "output")],
    "rtl": crcrx_rtl, "model": crcrx_model,
    "bugs": ["crc_poly_31", "crc_init_ff", "msb_first", "length_16_allowed", "crc_skips_length", "no_destuffing",
             "stuff_violation_ignored"],
    "visible": crcrx_rows, "hidden": crcrx_hidden,
    "describe": "a block with one serial input",
}

DESIGNS2 = {d["name"]: d for d in (CACHE, MCU, CRCRX)}
