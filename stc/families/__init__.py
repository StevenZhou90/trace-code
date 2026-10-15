"""The five synthetic task families. Each family module provides:

  NAME, GROUPS          family name and the list of structural parameter sets (one design group each)
  ports(p)              interface: [{name, dir, width, signed}] in declaration order
  rtl(p, bug=None)      reference Verilog text, or a deliberately broken variant named by bug
  bugs(p)               bug names that apply to (and observably change) this parameter set
  corners(p)            deterministic corner-case input rows (used only in hidden tests)
  random_rows(p, rng, n) randomized input rows
  visible_len(p)        rows in the public observed trace

All synthetic designs use the module name "dut", clock "clk" (rising edge) and synchronous active-high
reset "rst" that wins over every other input. The independent behavioral models live in stc/models.py.
"""


def port(name, direction, width=1):
    return {"name": name, "dir": direction, "width": width, "signed": False}


def header(ports, regs=()):
    """ANSI module header for dut. Outputs named in regs are declared reg, all else wire."""
    lines = []
    for p in ports:
        kind = "reg " if p["name"] in regs else "wire"
        rng = "[%d:0]" % (p["width"] - 1) if p["width"] > 1 else ""
        lines.append("    %-6s %s %-6s %s" % (p["dir"], kind, rng, p["name"]))
    return "module dut (\n" + ",\n".join(lines) + "\n);\n"


def reset_rows(names, n=2):
    """n rows with rst high and every other input low: the start of every sequential stimulus."""
    return [dict({k: 0 for k in names}, rst=1) for _ in range(n)]


# Imported last: the family modules use the helpers above.
from . import arbiter, comb, counter, fsm, handshake  # noqa: E402

FAMILIES = {m.NAME: m for m in (comb, counter, fsm, arbiter, handshake)}
