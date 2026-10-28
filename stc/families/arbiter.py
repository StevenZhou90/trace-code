"""Fixed-priority arbiter with a registered grant, N requesters.

On a rising edge: if rst, gnt becomes 0; else gnt becomes the one-hot bit of the lowest-numbered active
request, or 0 when no request is active. So gnt in row k answers the requests of row k-1.
Fixed priority is not fair: requester 0 can starve every other requester forever.

Wide groups (python3 -m stc.build --wide) add N = 5..8 and two keys. "high": true makes the
highest-numbered active request win instead. "rr": true makes a round-robin arbiter: the search starts
just after the last granted requester (requester 0 first after reset), so every requester that keeps
asking is served within N grants. With no active request, gnt is 0 and the search start stays put.
"""
from . import header, port, reset_rows

NAME = "arbiter"
GROUPS = [{"N": n} for n in (2, 3, 4)]
WIDE = [{"N": n} for n in (5, 6, 7, 8)] + [{"N": n, "high": True} for n in range(2, 9)] + \
       [{"N": n, "rr": True} for n in range(2, 9)]
FRESH = [{"N": 9}, {"N": 9, "high": True}, {"N": 9, "rr": True}]


def ports(p):
    return [port("clk", "input"), port("rst", "input"), port("req", "input", p["N"]), port("gnt", "output", p["N"])]


def bugs(p):
    if p.get("rr"):
        return ["no_rotation", "rotates_when_idle", "multi_grant", "reset_ignored"]
    return ["reversed_priority", "multi_grant", "grant_without_request", "reset_ignored"]


def _rr_rtl(p, bug):
    N = p["N"]
    iw = max(1, (N - 1).bit_length())
    start = "1" if bug == "no_rotation" else "last + i"  # (bug) always search from requester 0
    reset = "" if bug == "reset_ignored" else (
        "        if (rst) begin\n"
        "            gnt  <= %d'd0;\n"
        "            last <= %d'd%d;  // so requester 0 is searched first\n"
        "        end else begin\n") % (N, iw, N - 1)
    pick = "g = req;" if bug == "multi_grant" else (
        "for (i = 1; i <= %d; i = i + 1) begin  // requesters last+1, last+2, ... in turn\n"
        "                k = (%s) %% %d;\n"
        "                if (!found && req[k]) begin\n"
        "                    found = 1'b1;\n"
        "                    g[k] = 1'b1;\n"
        "                    idx = k;\n"
        "                end\n"
        "            end") % (N, start if bug != "no_rotation" else "i - 1", N)
    idle = "            else last <= (last + 1'b1) %% %d;  // (bug) moves on with no grant\n" % N \
        if bug == "rotates_when_idle" else ""
    body = ("    // Round robin: the search starts just after the last granted requester.\n"
            "    reg [%d:0] last;\n"
            "    reg [%d:0] g;\n"
            "    reg found;\n"
            "    integer i, k, idx;\n"
            "    always @(posedge clk) begin\n"
            "%s"
            "            g = %d'd0;\n"
            "            found = 1'b0;\n"
            "            idx = 0;\n"
            "            %s\n"
            "            gnt <= g;\n"
            "            if (found) last <= idx;\n"
            "%s"
            "%s"
            "    end\n") % (iw - 1, N - 1, reset, N, pick, idle, "" if bug == "reset_ignored" else "        end\n")
    if bug == "multi_grant":
        body = body.replace("            if (found) last <= idx;\n", "")
    return header(ports(p), regs={"gnt"}) + body + "endmodule\n"


def rtl(p, bug=None):
    if p.get("rr"):
        return _rr_rtl(p, bug)
    N = p["N"]
    high = bool(p.get("high")) != (bug == "reversed_priority")
    order = range(N - 1, -1, -1) if high else range(N)
    note = "    // Highest index wins. Not fair: a busy requester %d starves the others." % (N - 1) if p.get("high") \
        else "    // Lowest index wins. Not fair: a busy requester 0 starves the others."
    lines = [note,
             "    always @(posedge clk) begin"]
    lead = "if"
    if bug != "reset_ignored":
        lines.append("        if (rst)\n            gnt <= %d'd0;" % N)
        lead = "else if"
    if bug == "multi_grant":
        lines.append("        else\n            gnt <= req;" if lead == "else if" else "        gnt <= req;")
    else:
        for i in order:
            lines.append("        %s (req[%d])\n            gnt <= %d'b%s;" % (lead, i, N, format(1 << i, "0%db" % N)))
            lead = "else if"
        idle = "%d'd1" % N if bug == "grant_without_request" else "%d'd0" % N
        lines.append("        else\n            gnt <= %s;" % idle)
    lines.append("    end")
    return header(ports(p), regs={"gnt"}) + "\n".join(lines) + "\nendmodule\n"


def corners(p):
    N = p["N"]
    full = (1 << N) - 1
    rows = reset_rows(["req"])
    rows += [{"rst": 0, "req": 0}] * 2                          # no requests
    rows += [{"rst": 0, "req": r} for r in range(1 << N)]       # every request pattern
    rows += [{"rst": 0, "req": 1 << i} for i in range(N)]       # each requester alone
    rows += [{"rst": 0, "req": full}] * 4                      # all compete: requester 0 keeps winning
    rows += [{"rst": 1, "req": full}, {"rst": 0, "req": full}]  # reset beats a pending request
    rows += [{"rst": 0, "req": full & ~1}, {"rst": 0, "req": 1 << (N - 1)}, {"rst": 0, "req": 0}]
    if p.get("rr"):  # grant each requester, then 1 to 3 idle cycles, then everyone competes
        for i in range(N):
            for idle in (1, 2, 3):
                rows += [{"rst": 0, "req": 1 << i}] + [{"rst": 0, "req": 0}] * idle + [{"rst": 0, "req": full}] * 2
    return rows


def random_rows(p, rng, n):
    rows = reset_rows(["req"])
    while len(rows) < n:
        rows.append({"rst": int(rng.random() < 0.03), "req": rng.randrange(1 << p["N"])})
    return rows[:n]


def visible_len(p):
    return 64
