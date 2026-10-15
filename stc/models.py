"""Independent behavioral models: expected output rows for a stimulus, written from each family's rule
(the docstrings in stc/families/), not from the reference RTL. Hidden-test answers come from here.

Each model returns one list per row, outputs in port order. None means "don't care": the state is
unknown before the first reset has been applied, and out_data has no meaning while out_valid is low.
Row k sees the state before the rising edge of row k (see the timing rule in stc/sim.py).
"""


def comb(p, rows):
    out = []
    for r in rows:
        if p["op"] == "mux4":
            out.append([[r["d0"], r["d1"], r["d2"], r["d3"]][r["sel"]]])
        else:
            out.append([min(r["a"] + r["b"], (1 << p["W"]) - 1)])
    return out


def counter(p, rows):
    q, out = None, []
    for r in rows:
        out.append([q])
        if r["rst"]:
            q = 0
        elif q is not None and (r.get("en", 1)):
            q = (q + 1) % (1 << p["W"])
    return out


def fsm(p, rows):
    """Keeps the raw bit history since the last reset and looks for the pattern at its end, with no state
    table at all, so it does not share logic with the reference."""
    pattern = [int(c) for c in p["pattern"]]
    hist, out = None, []
    for r in rows:
        out.append([None if hist is None else int(hist[-len(pattern):] == pattern)])
        if r["rst"]:
            hist = []
        elif hist is not None:
            hist.append(r["din"])
    return out


def arbiter(p, rows):
    gnt, out = None, []
    for r in rows:
        out.append([gnt])
        if r["rst"]:
            gnt = 0
        elif gnt is not None:
            gnt = r["req"] & -r["req"]  # lowest set bit, as a one-hot value (0 when there is no request)
    return out


def handshake(p, rows):
    q, out = None, []  # q: stored words, oldest first
    for r in rows:
        if q is None:
            out.append([None, None, None])
        else:
            out.append([int(len(q) < p["D"]), int(len(q) > 0), q[0] if q else None])
        if r["rst"]:
            q = []
        elif q is not None:
            push = r["in_valid"] and len(q) < p["D"]
            pop = len(q) > 0 and r["out_ready"]
            if pop:
                q.pop(0)
            if push:
                q.append(r["in_data"])
    return out


MODELS = {"comb": comb, "counter": counter, "fsm": fsm, "arbiter": arbiter, "handshake": handshake}


def check_stream(rows, outs):
    """Protocol check on any handshake run, using only its own in_ready/out_valid/out_data (no model):
    within each reset-free stretch, words delivered (out_valid && out_ready) must be exactly the words
    accepted (in_valid && in_ready), in order, each once; and out_data must not change while
    out_valid && !out_ready. Rows before the first reset are skipped. Returns a list of problems."""
    probs, accepted, delivered, started = [], [], [], False
    for k, (r, (in_ready, out_valid, out_data)) in enumerate(zip(rows, outs)):
        if r["rst"]:  # reset wins: nothing is accepted or delivered in this row, the buffer empties
            started, accepted, delivered = True, [], []
            continue
        if not started:
            continue
        if "x" in (in_ready, out_valid) or (out_valid == 1 and out_data == "x"):
            probs.append("cycle %d: x on a handshake output" % k)
            break
        if out_valid and r["out_ready"]:
            delivered.append(out_data)
            if delivered != accepted[:len(delivered)]:
                probs.append("cycle %d: delivered %s, expected %s" % (k, out_data, accepted[len(delivered) - 1]
                             if len(accepted) >= len(delivered) else "nothing (duplicate or invented word)"))
                break
        if in_ready and r["in_valid"]:
            accepted.append(r["in_data"])
        if k + 1 < len(rows) and out_valid and not r["out_ready"] and not r["rst"]:
            nv, nd = outs[k + 1][1], outs[k + 1][2]
            if nv != 1 or nd != out_data:
                probs.append("cycle %d: stalled word %s changed to valid=%s data=%s" % (k, out_data, nv, nd))
                break
    return probs
