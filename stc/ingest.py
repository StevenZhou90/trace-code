"""Local ingestion of Verilog modules from a folder with a SOURCES.json license list.

Accepted: one module per file; input/output ports only, each at most 32 bits with a width that can be
evaluated; either no clock or a single clock named clk (rising edge); an optional reset named rst; only
safe system tasks; compiles with Icarus. Every rejected file gets a reason string.
Nothing is downloaded. External benchmarks are not ingested in this milestone.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile

from . import verilog

MAX_WIDTH = 32


def check_module(text):
    """(interface, None) for an acceptable module, else (None, reason)."""
    bad = verilog.unsafe_constructs(text)
    if bad:
        return None, "unsafe_construct:" + ",".join(bad)
    mods = verilog.modules(text)
    if len(mods) != 1:
        return None, "module_count:%d" % len(mods)
    name, body = mods[0]
    ports = verilog.ports(body)
    if any(p["dir"] == "inout" for p in ports):
        return None, "inout_port"
    if any(p["width"] is None for p in ports):
        return None, "unresolved_width"
    if any(p["width"] > MAX_WIDTH for p in ports):
        return None, "port_too_wide"
    if not any(p["dir"] == "output" for p in ports) or not any(p["dir"] == "input" for p in ports):
        return None, "needs_inputs_and_outputs"
    names = {p["name"] for p in ports}
    edges = set(re.findall(r"\b(?:posedge|negedge)\s+([A-Za-z_]\w*)", body))
    if re.search(r"\bnegedge\b", body) or edges - {"clk"}:
        return None, "unsupported_clock:" + ",".join(sorted(edges - {"clk"}) or ["negedge"])
    if "clk" in names and "clk" not in edges:
        return None, "clk_port_unused"
    if any(p["name"] in ("clk", "rst") and (p["dir"] != "input" or p["width"] != 1) for p in ports):
        return None, "bad_clock_or_reset_port"
    iface = {"module": "dut", "ports": ports, "clock": "clk" if "clk" in names else None,
             "reset": {"name": "rst", "active": "high", "synchronous": "not checked"} if "rst" in names else None}
    return iface, None


def compiles(text):
    work = tempfile.mkdtemp(prefix="stc-ingest-")
    try:
        with open(os.path.join(work, "m.v"), "w") as f:
            f.write(text)
        r = subprocess.run(["iverilog", "-g2012", "-o", "m.vvp", "m.v"], cwd=work, capture_output=True,
                           text=True, timeout=30)
        return r.returncode == 0, (r.stdout + r.stderr)[-2000:]
    finally:
        shutil.rmtree(work, ignore_errors=True)


def rename_module(text, new="dut"):
    """The stored reference is renamed to dut so the original module name never reaches the model."""
    return re.sub(r"\bmodule\s+[A-Za-z_]\w*", "module " + new, text, count=1)


def ingest(folder, seen):
    """Scan folder in sorted (deterministic) order. Returns (accepted, rejected); accepted items are
    {file, text, interface, origin, license}, rejected items are {file, reason}. seen is a dedup.Seen
    that may already hold synthetic references."""
    with open(os.path.join(folder, "SOURCES.json")) as f:
        sources = json.load(f)["files"]
    accepted, rejected = [], []
    for fname in sorted(os.listdir(folder)):
        if not fname.endswith(".v"):
            continue
        rel = os.path.join(os.path.basename(os.path.normpath(folder)), fname)
        with open(os.path.join(folder, fname)) as f:
            text = f.read()
        meta = sources.get(fname) or {}
        if not meta.get("license"):
            rejected.append({"file": rel, "reason": "license_unknown"})
            continue
        iface, reason = check_module(text)
        if reason is None:
            ok, log = compiles(text)
            reason = None if ok else "compile_error: " + log.strip().splitlines()[0][:200]
        if reason is None:
            reason = seen.check(text, rel)
        if reason:
            rejected.append({"file": rel, "reason": reason})
            continue
        accepted.append({"file": rel, "text": text, "interface": iface, "origin": meta.get("origin", "local"),
                         "license": meta["license"]})
    return accepted, rejected
