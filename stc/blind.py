"""Views of a task with less information: anonymous ports, or anonymous pins.

Level "A": the named interface, as built.
Level "B": anonymous ports. Every port except the clock gets a meaningless name (inputs i0, i1, ...,
           outputs o0, o1, ...) in shuffled order. Widths stay. The reset is not identified.
Level "C": anonymous pins. Every bit of every port except the clock is its own 1-bit pin (p00, p01, ...)
           in shuffled order, so the bus grouping, the bit order and the reset are all hidden. Only each
           pin's direction is given.

The clock stays "clk" at every level: a cycle table is sampled from it, so it is not part of the puzzle.
A view is fixed by the task id and the level. A candidate for level B or C is a module dut over the
anonymous ports; for grading, it is renamed dut_view and wrapped in a module dut with the original
ports, so the normal harness and hidden tests apply unchanged.
"""
import random
import re

from .families import header

TIMING = ("Row k: inputs are applied at the falling clock edge, outputs are sampled 1 time unit before the "
          "next rising edge, then the rising edge updates state. So outputs in row k depend on the state "
          "before that edge and on the inputs of row k. clk is the clock and is not shown in the table.")
TIMING_NO_CLOCK = "This block has no clock: row k is one input vector and the outputs it produces."


def make_view(iface, task_id, level):
    """[(view name, dir, width, [(original port, bit), ...] from LSB up)] in declaration order."""
    rng = random.Random("view:%s:%s" % (task_id, level))
    ports = [p for p in iface["ports"] if p["name"] != iface.get("clock")]
    if level == "A":
        return [(p["name"], p["dir"], p["width"], [(p["name"], b) for b in range(p["width"])]) for p in ports]
    if level == "B":
        ports = ports[:]
        rng.shuffle(ports)
        count = {"input": 0, "output": 0}
        out = []
        for p in ports:
            name = "%s%d" % (p["dir"][0], count[p["dir"]])
            count[p["dir"]] += 1
            out.append((name, p["dir"], p["width"], [(p["name"], b) for b in range(p["width"])]))
        return out
    bits = [(p["name"], b, p["dir"]) for p in ports for b in range(p["width"])]
    rng.shuffle(bits)
    return [("p%02d" % i, d, 1, [(name, b)]) for i, (name, b, d) in enumerate(bits)]


def view_ports(iface, view):
    clock = [{"name": iface["clock"], "dir": "input", "width": 1, "signed": False}] if iface.get("clock") else []
    return clock + [{"name": n, "dir": d, "width": w, "signed": False} for n, d, w, _ in view]


def view_trace(trace, view):
    """The public trace re-expressed over the view's columns. An unknown ("x") output stays unknown."""
    names = [s["name"] for s in trace["signals"]]
    rows = []
    for r in trace["rows"]:
        val = dict(zip(names, r))
        row = []
        for _, _, _, bits in view:
            if any(val[n] == "x" for n, _ in bits):
                row.append("x")
            else:
                row.append(sum(((val[n] >> b) & 1) << i for i, (n, b) in enumerate(bits)))
        rows.append(row)
    signals = [{"name": n, "dir": d, "width": w, "signed": False} for n, d, w, _ in view]
    order = [i for i, s in enumerate(signals) if s["dir"] == "input"] + \
            [i for i, s in enumerate(signals) if s["dir"] == "output"]
    return {"signals": [signals[i] for i in order], "rows": [[row[i] for i in order] for row in rows]}


def timing(iface):
    return TIMING if iface.get("clock") else TIMING_NO_CLOCK


def _concat(bits):
    """Verilog for the value whose bit i is bits[i] (LSB first)."""
    return bits[0] if len(bits) == 1 else "{%s}" % ", ".join(reversed(bits))


def wrapper(iface, view):
    """module dut with the original ports, driving dut_view from them (the grading side)."""
    conns = (["        .%s(%s)" % (iface["clock"], iface["clock"])] if iface.get("clock") else [])
    width = {p["name"]: p["width"] for p in iface["ports"]}
    for name, _, _, bits in view:
        conns.append("        .%s(%s)" % (name, _concat(["%s[%d]" % (n, b) if width[n] > 1 else n for n, b in bits])))
    return header(iface["ports"]) + "    dut_view u (\n" + ",\n".join(conns) + "\n    );\nendmodule\n"


def wrap_candidate(iface, view, text):
    """Rename the candidate's module dut to dut_view and add the wrapper, for the normal harness."""
    return re.sub(r"\bmodule\s+dut\b", "module dut_view", text, count=1) + "\n" + wrapper(iface, view)


def view_reference(iface, view, ref):
    """The reference rewritten over the view's ports: the original ports become internal signals with
    their usual names, tied to the anonymous ports. This is the training answer for levels B and C."""
    body = ref[ref.index(");\n") + 3:]
    decl_regs = set(re.findall(r"output\s+reg\s+(?:\[[^\]]*\]\s*)?(\w+)", ref[:ref.index(");\n")]))
    lines = []
    width = {p["name"]: p["width"] for p in iface["ports"]}
    src = {}  # original input -> [view expression per bit]
    for name, d, w, bits in view:
        for i, (n, b) in enumerate(bits):
            src.setdefault(n, {})[b] = name if w == 1 else "%s[%d]" % (name, i)
    for p in iface["ports"]:
        if p["name"] == iface.get("clock"):
            continue
        rng = "[%d:0] " % (p["width"] - 1) if p["width"] > 1 else ""
        if p["dir"] == "input":
            expr = _concat([src[p["name"]][b] for b in range(p["width"])])
            lines.append("    wire %s%s = %s;" % (rng, p["name"], expr))
        else:
            lines.append("    %s %s%s;" % ("reg" if p["name"] in decl_regs else "wire", rng, p["name"]))
    for name, d, w, bits in view:
        if d == "output":
            expr = _concat(["%s[%d]" % (n, b) if width[n] > 1 else n for n, b in bits])
            lines.append("    assign %s = %s;" % (name, expr))
    return header(view_ports(iface, view)) + "\n".join(lines) + "\n" + body
