"""Fixed-priority arbiter with a registered grant, N requesters.

On a rising edge: if rst, gnt becomes 0; else gnt becomes the one-hot bit of the lowest-numbered active
request, or 0 when no request is active. So gnt in row k answers the requests of row k-1.
Fixed priority is not fair: requester 0 can starve every other requester forever.
"""
from . import header, port, reset_rows

NAME = "arbiter"
GROUPS = [{"N": n} for n in (2, 3, 4)]


def ports(p):
    return [port("clk", "input"), port("rst", "input"), port("req", "input", p["N"]), port("gnt", "output", p["N"])]


def bugs(p):
    return ["reversed_priority", "multi_grant", "grant_without_request", "reset_ignored"]


def rtl(p, bug=None):
    N = p["N"]
    order = range(N - 1, -1, -1) if bug == "reversed_priority" else range(N)
    lines = ["    // Lowest index wins. Not fair: a busy requester 0 starves the others.",
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
    return rows


def random_rows(p, rng, n):
    rows = reset_rows(["req"])
    while len(rows) < n:
        rows.append({"rst": int(rng.random() < 0.03), "req": rng.randrange(1 << p["N"])})
    return rows[:n]


def visible_len(p):
    return 64
