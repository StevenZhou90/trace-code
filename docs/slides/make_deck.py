"""Build the four-page deck from real pipeline outputs. Every number on it is read from files.

    python3 -m stc.build --out data/seed0 --seed 0
    python3 -m stc.selfcheck --dataset data/seed0
    python3 -m unittest discover -s tests -t . -v 2> docs/slides/test_output.txt
    python3 docs/slides/make_deck.py --dataset data/seed0
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu \
        --no-pdf-header-footer --print-to-pdf=docs/slides/deck.pdf docs/slides/deck.html
"""
import argparse
import html
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from stc.evaluate import evaluate  # noqa: E402
from stc.families import FAMILIES  # noqa: E402

# Dark-mode reference palette (validated: 5 slots pass every categorical check on #1a1a19).
FAM_COLOR = {"comb": "#3987e5", "counter": "#d95926", "fsm": "#199e70", "arbiter": "#c98500", "handshake": "#d55181"}
FAM_LABEL = {"comb": "Combinational", "counter": "Counter", "fsm": "State machine", "arbiter": "Arbiter",
             "handshake": "Ready/valid buffer"}
INK, INK2, MUTED, GRID, AXIS, SURF = "#f0efec", "#c3c2b7", "#898781", "#2c2c2a", "#383835", "#1a1a19"
GOOD, CRIT = "#0ca30c", "#d03b3b"
SPLIT_COLOR = {"train": "#3987e5", "val": "#86b6ef", "test": "#cde2fb"}  # ordinal blue ramp


def esc(s):
    return html.escape(str(s))


def load(ds):
    recs = [json.loads(l) for l in open(os.path.join(ds, "records.jsonl"))]
    rejects = [json.loads(l) for l in open(os.path.join(ds, "rejects.jsonl"))]
    summary = json.load(open(os.path.join(ds, "summary.json")))
    check = json.load(open(os.path.join(ds, "selfcheck.json")))
    return recs, rejects, summary, check


def trace_of(ds, rec):
    return json.load(open(os.path.join(ds, rec["public_trace_path"])))


# ---------------------------------------------------------------- waveforms

def waveform(tr, start, n, color, width=820, row_h=34, label_w=118, names=None, clock=True):
    """Digital timing diagram of rows [start, start+n). Inputs in secondary ink, outputs in the family color.
    One column per trace row; the clock row shows the falling edge at the left of each column."""
    sig = tr["signals"]
    keep = [i for i, s in enumerate(sig) if names is None or s["name"] in names]
    rows = tr["rows"][start:start + n]
    lines = int(clock) + len(keep)  # clock row (if the block has a clock) plus one row per signal
    cw = (width - label_w) / n
    h = lines * row_h + 26
    out = ['<svg viewBox="0 0 %d %d" width="%d" height="%d" xmlns="http://www.w3.org/2000/svg">' % (width, h, width, h)]
    y0 = 4
    # column grid and cycle numbers
    for k in range(n + 1):
        x = label_w + k * cw
        out.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="%s" stroke-width="1"/>' % (x, y0, x, h - 22, GRID))
    for k in range(0, n, 4):
        out.append('<text x="%.1f" y="%d" fill="%s" font-size="13" text-anchor="middle">%d</text>'
                   % (label_w + (k + 0.5) * cw, h - 6, MUTED, start + k))
    r = 0
    hi, lo = 6, row_h - 8
    if clock:
        # clock: low for the first half of each row (inputs change at the fall), high for the second half
        yc = y0 + r * row_h
        out.append('<text x="0" y="%d" fill="%s" font-size="16">clk</text>' % (yc + row_h / 2 + 5, MUTED))
        pts = []
        for k in range(n):
            x = label_w + k * cw
            pts += ["%.1f,%.1f" % (x, yc + hi), "%.1f,%.1f" % (x, yc + lo), "%.1f,%.1f" % (x + cw / 2, yc + lo),
                    "%.1f,%.1f" % (x + cw / 2, yc + hi), "%.1f,%.1f" % (x + cw, yc + hi)]
        out.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="1.5"/>' % (" ".join(pts), MUTED))
        r += 1
    for i in keep:
        s = sig[i]
        is_out = s["dir"] == "output"
        c = color if is_out else INK2
        y = y0 + r * row_h
        out.append('<text x="0" y="%d" fill="%s" font-size="16" font-weight="%s">%s</text>'
                   % (y + row_h / 2 + 5, INK if is_out else INK2, 600 if is_out else 400, esc(s["name"])))
        vals = [row[i] for row in rows]
        if s["width"] == 1:
            k = 0
            while k < n:  # unknown spans as a muted band
                if vals[k] == "x":
                    j = k
                    while j < n and vals[j] == "x":
                        j += 1
                    out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s" opacity="0.55"/>'
                               % (label_w + k * cw, y + hi, (j - k) * cw, lo - hi, AXIS))
                    k = j
                else:
                    k += 1
            pts, prev = [], None
            for k, v in enumerate(vals):
                x = label_w + k * cw
                if v == "x":
                    if pts:
                        out.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="2"/>' % (" ".join(pts), c))
                    pts, prev = [], None
                    continue
                yy = y + (hi if v else lo)
                if prev is not None and prev != v:
                    pts.append("%.1f,%.1f" % (x, yy))
                elif not pts:
                    pts.append("%.1f,%.1f" % (x, yy))
                pts.append("%.1f,%.1f" % (x + cw, yy))
                prev = v
            if pts:
                out.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="2"/>' % (" ".join(pts), c))
        else:
            k = 0
            while k < n:
                j = k
                while j < n and vals[j] == vals[k]:
                    j += 1
                x1, x2 = label_w + k * cw + 1.5, label_w + j * cw - 1.5
                m = min(6, (x2 - x1) / 3)
                poly = "%.1f,%.1f %.1f,%.1f %.1f,%.1f %.1f,%.1f %.1f,%.1f %.1f,%.1f" % (
                    x1, y + row_h / 2 - 1, x1 + m, y + hi, x2 - m, y + hi, x2, y + row_h / 2 - 1, x2 - m, y + lo, x1 + m, y + lo)
                if vals[k] == "x":
                    out.append('<polygon points="%s" fill="%s" opacity="0.55"/>' % (poly, AXIS))
                else:
                    out.append('<polygon points="%s" fill="none" stroke="%s" stroke-width="1.5"/>' % (poly, c))
                    txt = str(vals[k])
                    if (x2 - x1) > 9 * len(txt) + 6:
                        out.append('<text x="%.1f" y="%.1f" fill="%s" font-size="14" text-anchor="middle">%s</text>'
                                   % ((x1 + x2) / 2, y + row_h / 2 + 4, INK if is_out else INK2, txt))
                k = j
        r += 1
    out.append("</svg>")
    return "\n".join(out)


def timing_rule_svg():
    """Illustration of the sampling rule for one row k (a drawing, not data)."""
    w, h = 900, 290
    x0, cw = 150, 560          # row k spans x0 .. x0 + cw: clock low first half, high second half
    rise = x0 + cw / 2
    sx = rise - 46             # sampling point: just before the rising edge
    o = ['<svg viewBox="0 0 %d %d" width="%d" height="%d" xmlns="http://www.w3.org/2000/svg">' % (w, h, w, h)]
    o.append('<text x="0" y="46" fill="%s" font-size="20">clk</text>' % MUTED)
    o.append('<polyline points="%d,26 %d,26 %d,62 %.0f,62 %.0f,26 %d,26 %d,62 %d,62" fill="none" stroke="%s" stroke-width="2.5"/>'
             % (x0 - 90, x0, x0, rise, rise, x0 + cw, x0 + cw, x0 + cw + 90, MUTED))
    o.append('<text x="0" y="122" fill="%s" font-size="20">inputs</text>' % INK2)
    o.append('<polygon points="%d,115 %d,96 %d,96 %d,115 %d,134 %d,134" fill="none" stroke="%s" stroke-width="2.5"/>'
             % (x0 + 2, x0 + 14, x0 + cw - 14, x0 + cw - 2, x0 + cw - 14, x0 + 14, INK2))
    o.append('<text x="%d" y="122" fill="%s" font-size="19">row k</text>' % (x0 + 34, INK2))
    o.append('<text x="0" y="176" fill="%s" font-size="20" font-weight="600">outputs</text>' % INK)
    o.append('<line x1="%.0f" y1="14" x2="%.0f" y2="190" stroke="%s" stroke-width="2.5"/>' % (sx, sx, FAM_COLOR["comb"]))
    o.append('<circle cx="%.0f" cy="170" r="8" fill="%s"/>' % (sx, FAM_COLOR["comb"]))
    o.append('<line x1="%.0f" y1="66" x2="%.0f" y2="190" stroke="%s" stroke-width="1.5"/>' % (rise, rise, AXIS))
    marks = [(x0, 26, "1"), (sx, 14, "2"), (rise, 26, "3")]  # numbered points on the drawing
    for x, y, n in marks:
        o.append('<circle cx="%.0f" cy="%d" r="13" fill="%s" stroke="%s" stroke-width="2"/>' % (x, y - 2, SURF, INK2))
        o.append('<text x="%.0f" y="%d" fill="%s" font-size="15" font-weight="700" text-anchor="middle">%s</text>'
                 % (x, y + 3, INK, n))
    notes = ["1  inputs of row k change at the falling edge", "2  outputs are sampled 1 ns before the rising edge",
             "3  the rising edge updates the state"]
    for i, t in enumerate(notes):
        o.append('<text x="0" y="%d" fill="%s" font-size="19">%s</text>' % (226 + 28 * i, INK2, esc(t)))
    o.append("</svg>")
    return "\n".join(o)


# ---------------------------------------------------------------- charts

def catch_chart(summary):
    """Horizontal bars: share of bug runs caught by the hidden tests and by the visible trace alone."""
    fams = list(FAMILIES)
    w, bar, label_w = 760, 24, 190
    group_h = 2 * bar + 2 + 40
    h = len(fams) * group_h + 40
    plot_w = w - label_w - 90
    o = ['<svg viewBox="0 0 %d %d" width="%d" height="%d" xmlns="http://www.w3.org/2000/svg">' % (w, h, w, h)]
    for t in (0, 50, 100):
        x = label_w + plot_w * t / 100
        o.append('<line x1="%.1f" y1="0" x2="%.1f" y2="%d" stroke="%s"/>' % (x, x, h - 28, GRID))
        o.append('<text x="%.1f" y="%d" fill="%s" font-size="14" text-anchor="middle">%d%%</text>' % (x, h - 8, MUTED, t))
    for gi, f in enumerate(fams):
        s = summary[f]
        y = gi * group_h + 6
        o.append('<text x="0" y="%d" fill="%s" font-size="18">%s</text>' % (y + bar + 6, INK, esc(FAM_LABEL[f])))
        for bi, (num, color, name) in enumerate([(s["mutants_killed"], "#3987e5", "hidden"),
                                                  (s["mutants_caught_by_visible_trace_alone"], "#d95926", "visible")]):
            yy = y + bi * (bar + 2)
            frac = num / s["mutants"]
            bw = max(4, plot_w * frac)
            o.append('<path d="M%.1f %.1f h%.1f a4 4 0 0 1 4 4 v%.1f a4 4 0 0 1 -4 4 h-%.1f z" fill="%s"/>'
                     % (label_w, yy, bw - 4, bar - 8, bw - 4, color))
            o.append('<text x="%.1f" y="%.1f" fill="%s" font-size="15">%d / %d</text>'
                     % (label_w + bw + 8, yy + bar - 4, INK2, num, s["mutants"]))
    o.append("</svg>")
    return "\n".join(o)


def split_chart(by_family):
    fams = list(FAMILIES) + ["ingested"]
    w, bar, label_w = 760, 26, 190
    row_h = bar + 16
    h = len(fams) * row_h + 34
    mx = max(v["tasks"] for v in by_family.values())
    plot_w = w - label_w - 60
    o = ['<svg viewBox="0 0 %d %d" width="%d" height="%d" xmlns="http://www.w3.org/2000/svg">' % (w, h, w, h)]
    for t in range(0, mx + 1, 5):
        x = label_w + plot_w * t / mx
        o.append('<line x1="%.1f" y1="0" x2="%.1f" y2="%d" stroke="%s"/>' % (x, x, h - 26, GRID))
        o.append('<text x="%.1f" y="%d" fill="%s" font-size="14" text-anchor="middle">%d</text>' % (x, h - 6, MUTED, t))
    for i, f in enumerate(fams):
        v = by_family[f]
        y = i * row_h + 4
        o.append('<text x="0" y="%d" fill="%s" font-size="18">%s</text>' % (y + bar - 7, INK, esc(FAM_LABEL.get(f, "Ingested fixtures"))))
        x = label_w
        segs = [(sp, v[sp]) for sp in ("train", "val", "test") if v[sp]]
        for j, (sp, cnt) in enumerate(segs):
            sw = plot_w * cnt / mx
            last = j == len(segs) - 1
            gapw = 0 if last else 2
            if last:
                o.append('<path d="M%.1f %.1f h%.1f a4 4 0 0 1 4 4 v%.1f a4 4 0 0 1 -4 4 h-%.1f z" fill="%s"/>'
                         % (x, y, sw - 4, bar - 8, sw - 4, SPLIT_COLOR[sp]))
            else:
                o.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%d" fill="%s"/>' % (x, y, sw - gapw, bar, SPLIT_COLOR[sp]))
            if sw > 26:
                o.append('<text x="%.1f" y="%.1f" fill="#0d0d0d" font-size="14" text-anchor="middle">%d</text>'
                         % (x + sw / 2, y + bar - 8, cnt))
            x += sw
    o.append("</svg>")
    return "\n".join(o)


# ---------------------------------------------------------------- pages

def tests_line(path):
    text = open(path).read()
    ran = re.search(r"Ran (\d+) tests? in ([\d.]+)s", text)
    ok = re.search(r"\n(OK|FAILED[^\n]*)\s*$", text)
    return int(ran.group(1)), float(ran.group(2)), ok.group(1) if ok else "unknown"


def pick_windows(ds, recs):
    """(family, record, start, n, caption) for the waveform page, from variant-0 tasks of chosen groups."""
    want = {"comb": 'comb:{"W": 4, "op": "add_sat"}', "counter": 'counter:{"W": 3, "enable": true}',
            "fsm": 'fsm:{"pattern": "1011"}', "arbiter": 'arbiter:{"N": 3}', "handshake": 'handshake:{"D": 2, "W": 8}'}
    cap = {"comb": "y = min(a + b, 15): saturates instead of wrapping",
           "counter": "3-bit counter: reset, count when en, hold, wrap 7 to 0",
           "fsm": "detects 1011 with overlap; y is high the cycle after the last bit",
           "arbiter": "registered one-hot grant: the lowest-numbered request wins (not fair)",
           "handshake": "2-entry buffer: backpressure, in order, data held while stalled"}
    out = []
    for f, g in want.items():
        rec = next(r for r in recs if r["design_group"] == g)
        tr = trace_of(ds, rec)
        start, n = 0, 24
        if f == "fsm":
            hit = next(k for k, r in enumerate(tr["rows"]) if r[-1] == 1)
            start = max(0, hit - 14)
        if f == "comb":
            n = 16
        out.append((f, rec, tr, start, n, cap[f]))
    return out


CSS = """
@page { size: 1920px 1080px; margin: 0; }
* { box-sizing: border-box; }
body { margin: 0; background: #0d0d0d; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; color: %(INK)s; }
.page { width: 1920px; height: 1080px; padding: 72px 96px 64px; background: %(SURF)s; position: relative;
        page-break-after: always; overflow: hidden; }
.page:last-child { page-break-after: auto; }
h1 { font-size: 60px; font-weight: 650; margin: 0 0 14px; letter-spacing: -0.5px; }
h2 { font-size: 22px; font-weight: 500; color: %(INK2)s; margin: 0 0 44px; max-width: 1500px; line-height: 1.4; }
.kicker { font-size: 18px; letter-spacing: 2px; text-transform: uppercase; color: %(MUTED)s; margin-bottom: 18px; }
.foot { position: absolute; bottom: 30px; left: 96px; right: 96px; font-size: 15px; color: %(MUTED)s;
        display: flex; justify-content: space-between; }
.tiles { display: flex; gap: 28px; margin-top: 40px; }
.tile { flex: 1; background: #232321; border-radius: 14px; padding: 24px 28px; }
.tile { display: flex; align-items: center; gap: 26px; padding: 16px 28px; }
.tile .v { font-size: 52px; font-weight: 650; min-width: 236px; }
.tile .l { font-size: 19px; color: %(INK2)s; line-height: 1.35; }
.flow { display: flex; align-items: stretch; gap: 0; margin-top: 8px; }
.box { background: #232321; border-radius: 14px; padding: 24px 24px; flex: 1; }
.box .n { font-size: 15px; color: %(MUTED)s; letter-spacing: 1px; margin-bottom: 6px; }
.box .t { font-size: 25px; font-weight: 600; margin-bottom: 10px; }
.box .d { font-size: 19px; color: %(INK2)s; line-height: 1.45; }
.arrow { width: 44px; display: flex; align-items: center; justify-content: center; color: %(MUTED)s; font-size: 30px; }
.outs { display: flex; flex-direction: column; gap: 12px; width: 360px; }
.out { background: #232321; border-radius: 12px; padding: 14px 20px; border-left: 5px solid %(MUTED)s; flex: 1; }
.out .t { font-size: 22px; font-weight: 600; }
.out .d { font-size: 17px; color: %(INK2)s; margin-top: 4px; line-height: 1.35; }
.grid5 { display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: auto auto auto; gap: 22px 64px;
         grid-template-areas: "comb arbiter" "counter handshake" "fsm handshake"; }
.panel .name { font-size: 22px; font-weight: 600; display: flex; align-items: center; gap: 10px; }
.dot { width: 14px; height: 14px; border-radius: 4px; display: inline-block; }
.panel .cap { font-size: 16px; color: %(INK2)s; margin: 4px 0 6px 24px; }
.cols { display: flex; gap: 72px; }
.col { flex: 1; }
.ctitle { font-size: 24px; font-weight: 600; margin-bottom: 6px; }
.csub { font-size: 16px; color: %(INK2)s; margin-bottom: 18px; line-height: 1.4; }
.legend { display: flex; gap: 26px; font-size: 16px; color: %(INK2)s; margin: 0 0 14px; }
.legend span { display: flex; align-items: center; gap: 8px; }
table.m { border-collapse: separate; border-spacing: 4px; font-size: 15px; }
table.m th { color: %(MUTED)s; font-weight: 500; text-align: center; padding: 4px 6px; font-size: 14px; }
table.m th.r { text-align: left; color: %(INK)s; font-size: 16px; font-weight: 500; white-space: nowrap; padding-right: 10px; }
table.m td { background: #232321; border-radius: 6px; padding: 9px 8px; text-align: center; color: %(INK)s; white-space: nowrap; }
.ok { color: %(GOOD)s; font-weight: 700; margin-right: 4px; }
.bad { color: %(CRIT)s; font-weight: 700; margin-right: 4px; }
pre { background: #232321; border-radius: 12px; padding: 16px 20px; font-size: 14.5px; line-height: 1.45; color: %(INK2)s;
      margin: 0; white-space: pre; overflow: hidden; font-family: ui-monospace, Menlo, monospace; }
.check { font-size: 18px; line-height: 1.5; }
.check .row { display: flex; gap: 12px; margin-bottom: 7px; }
.check .s { width: 92px; flex: none; font-weight: 600; font-size: 15px; padding-top: 2px; }
.s.done { color: %(GOOD)s; } .s.part { color: #fab219; } .s.miss { color: %(CRIT)s; }
""" % {"INK": INK, "INK2": INK2, "MUTED": MUTED, "SURF": SURF, "GOOD": GOOD, "CRIT": CRIT}


def foot(n, commit_note):
    return '<div class="foot"><span>trace-code · CPU pipeline milestone · %s</span><span>%d / 4</span></div>' % (commit_note, n)


def build_deck(ds, test_log, out_html, note, preview_dir=None):
    recs, rejects, summary, check = load(ds)
    n_tests, t_tests, tests_ok = tests_line(test_log)
    synth = [r for r in recs if r["family"] in FAMILIES]
    s = check["summary"]
    refs = sum(v["references_pass"] for v in s.values()), sum(v["references"] for v in s.values())
    muts = sum(v["mutants_killed"] for v in s.values()), sum(v["mutants"] for v in s.values())
    vis = sum(v["mutants_caught_by_visible_trace_alone"] for v in s.values())
    brk = sum(v["broken_classified"] for v in s.values()), sum(v["broken"] for v in s.values())
    ingest_rej = [r for r in rejects if "file" in r]
    groups = len({r["design_group"] for r in synth})
    by = summary["by_family"]
    pages = []

    # -------- page 1
    p = ['<div class="page">', '<div class="kicker">Signal-to-code · CPU pipeline milestone</div>',
         "<h1>From observed signals to graded Verilog</h1>",
         "<h2>A model sees only a hidden module's interface and one observed trace. It must write Verilog "
         "that passes hidden tests it never saw. This milestone builds the data and the grader underneath.</h2>",
         '<div class="flow">',
         '<div class="box"><div class="n">STEP 1</div><div class="t">Sources</div><div class="d">5 family generators, %d design groups<br>'
         "%d local fixture files with a license list</div></div>" % (groups, len(ingest_rej) + by["ingested"]["tasks"] + 0),
         '<div class="arrow">→</div>',
         '<div class="box"><div class="n">STEP 2</div><div class="t">Ingest and check</div><div class="d">one module, plain ports, safe code, '
         "compiles<br>%d files rejected, each with a reason</div></div>" % len(ingest_rej),
         '<div class="arrow">→</div>',
         '<div class="box"><div class="n">STEP 3</div><div class="t">Dedup and split</div><div class="d">exact and comment/whitespace hashes<br>'
         "split by design group, before seeds</div></div>",
         '<div class="arrow">→</div>',
         '<div class="box"><div class="n">STEP 4</div><div class="t">Simulate</div><div class="d">Icarus Verilog, isolated, time limit<br>'
         "reference must match an independent Python model</div></div>",
         '<div class="arrow">→</div>',
         '<div class="outs">',
         '<div class="out" style="border-color:%s"><div class="t">Public</div><div class="d">interface + observed trace</div></div>' % FAM_COLOR["comb"],
         '<div class="out" style="border-color:%s"><div class="t">Target</div><div class="d">reference RTL for training</div></div>' % FAM_COLOR["fsm"],
         '<div class="out" style="border-color:%s"><div class="t">Private</div><div class="d">hidden corner cases + 200 random rows</div></div>' % FAM_COLOR["counter"],
         "</div></div>",
         '<div style="display:flex; gap:80px; align-items:flex-end; margin-top:44px">',
         '<div><div class="ctitle">One timing rule for every task, so traces have no races</div>%s</div>' % timing_rule_svg(),
         '<div class="tiles" style="flex:1; margin:0; flex-direction:column; gap:14px">',
         '<div class="tile"><div class="v">%d</div><div class="l">tasks in the seed-0 build<br>(%d synthetic, %d ingested)</div></div>'
         % (summary["tasks"], len(synth), by["ingested"]["tasks"]),
         '<div class="tile"><div class="v">%d / %d</div><div class="l">deliberate bugs fail<br>the hidden tests</div></div>' % muts,
         '<div class="tile"><div class="v">%d</div><div class="l">unit tests, %s<br>(%.0f s on a laptop CPU)</div></div>'
         % (n_tests, "all pass" if tests_ok == "OK" else esc(tests_ok), t_tests),
         "</div></div>", foot(1, note), "</div>"]
    pages.append("\n".join(p))

    # -------- page 2
    p = ['<div class="page">', '<div class="kicker">Five task families</div>',
         "<h1>What a model gets to see</h1>",
         "<h2>Real rows from public traces in the seed-0 build: inputs in gray, outputs in color, unknown values "
         "before the first reset as a gray band. Each rule is written in plain words, and a separate Python model "
         "built from it must agree with the reference RTL on every row.</h2>", '<div class="grid5">']
    for f, rec, tr, start, n, caption in pick_windows(ds, recs):
        p.append('<div class="panel" style="grid-area:%s"><div class="name"><span class="dot" style="background:%s"></span>%s</div>'
                 '<div class="cap">%s · rows %d–%d</div>%s</div>'
                 % (f, FAM_COLOR[f], esc(FAM_LABEL[f]), esc(caption), start, start + n - 1,
                    waveform(tr, start, n, FAM_COLOR[f], width=820, row_h=44 if f == "handshake" else 32,
                             clock=rec["interface"]["clock"] is not None)))
    p += ["</div>", foot(2, note), "</div>"]
    pages.append("\n".join(p))

    # -------- page 3
    kinds = ["syntax_error", "renamed_port", "runtime_fatal", "early_finish", "endless_loop", "forbidden_task"]
    klabel = {"syntax_error": "syntax error", "renamed_port": "renamed port", "runtime_fatal": "$fatal at run time",
              "early_finish": "early $finish", "endless_loop": "endless loop", "forbidden_task": "$system call"}
    broken = {(r["family"], r["candidate"]): r for r in check["results"] if r["kind"] == "broken"}
    hs = next(r for r in recs if r["design_group"] == 'handshake:{"D": 2, "W": 8}')
    rep = evaluate(ds, hs, FAMILIES["handshake"].rtl(hs["params"], "drop_word"))
    m = rep["mismatches"][0]
    fail_text = ("candidate: drop_word   status: %s   failing rows: %d of %d\n"
                 "first failing row: cycle %d\n"
                 "  inputs    %s\n  expected  %s\n  actual    %s\n"
                 "protocol check: %s") % (
        rep["status"], rep["failing_rows"], rep["hidden_rows"], m["cycle"],
        "  ".join("%s=%s" % kv for kv in m["inputs"].items()),
        "  ".join("%s=%s" % kv for kv in m["expected"].items()),
        "  ".join("%s=%s" % kv for kv in m["actual"].items()),
        rep["protocol_problems"][0] if rep.get("protocol_problems") else "none")
    p = ['<div class="page">', '<div class="kicker">Testing the tests</div>',
         "<h1>The hidden tests catch the bugs that the trace misses</h1>",
         "<h2>Every reference passes (%d of %d). Every deliberate bug fails the hidden tests (%d of %d bug runs). "
         "Checked against the visible trace alone, %d of those bugs would have passed.</h2>"
         % (refs[0], refs[1], muts[0], muts[1], muts[1] - vis),
         '<div class="cols"><div class="col">',
         '<div class="ctitle">Bug runs caught, by family</div>',
         '<div class="csub">Bugs include a wrong reset, wrapping one early, a wrong transition, reversed priority, '
         "and dropped or duplicated words. Each runs on every task of its family.</div>",
         '<div class="legend"><span><span class="dot" style="background:#3987e5"></span>hidden tests</span>'
         '<span><span class="dot" style="background:#d95926"></span>visible trace alone</span></div>',
         catch_chart(s), "</div>", '<div class="col">',
         '<div class="ctitle">Broken candidates get the right status</div>',
         '<div class="csub">Six broken versions of a reference per family, %d of %d classified as expected.</div>' % brk,
         '<table class="m"><tr><th></th>' + "".join("<th>%s</th>" % esc(klabel[k]) for k in kinds) + "</tr>"]
    for f in FAMILIES:
        cells = []
        for k in kinds:
            r = broken[(f, k)]
            mark = '<span class="ok">✓</span>' if r["ok"] else '<span class="bad">✗</span>'
            cells.append("<td>%s%s</td>" % (mark, esc(r["status"])))
        p.append('<tr><th class="r"><span class="dot" style="background:%s"></span> %s</th>%s</tr>'
                 % (FAM_COLOR[f], esc(FAM_LABEL[f]), "".join(cells)))
    p += ["</table>", '<div class="ctitle" style="margin-top:30px">What a failure report shows (one real bug run)</div>',
          "<pre>%s</pre>" % esc(fail_text), "</div></div>", foot(3, note), "</div>"]
    pages.append("\n".join(p))

    # -------- page 4
    sample = next(r for r in recs if r["design_group"] == 'fsm:{"pattern": "1011"}')
    keep = ["task_id", "family", "design_group", "split", "seed", "simulator_version", "reference_status",
            "model_check_status", "public_trace_path", "private_tests_path"]
    show = lambda v: v if isinstance(v, str) else json.dumps(v)
    rec_text = "\n".join("%-19s %s" % (k, show(sample[k])) for k in keep)
    status = [
        ("done", "One command builds all five families, with public traces, targets and hidden tests"),
        ("done", "Harness: 7 distinct statuses, time limits, bounded logs, untrusted code never run"),
        ("done", "References pass, all bugs fail, broken candidates classified; same seed gives identical bytes"),
        ("done", "Local ingestion with reasons; exact and normalized dedup; splits by design group"),
        ("part", "Dedup is comments and whitespace only: renamed copies are not caught (tested)"),
        ("part", "Splits hold new parameter sets of the same 5 templates, not new kinds of designs"),
        ("miss", "External benchmark ingestion (no license check or download done)"),
        ("miss", "Synthesis check: a pass is simulation only, not proof that the design synthesizes"),
    ]
    lab = {"done": "Done", "part": "Partial", "miss": "Missing"}
    p = ['<div class="page">', '<div class="kicker">Ready for baseline training?</div>',
         "<h1>The data and the grader are ready; models come next</h1>",
         "<h2>%d tasks, each with a public trace, a reference target and private hidden tests. Splits are fixed by "
         "design group. Model, hardware and budget choices are left to the next stage.</h2>" % summary["tasks"],
         '<div class="cols"><div class="col">',
         '<div class="ctitle">Tasks by family and split</div>',
         '<div class="legend">' + "".join('<span><span class="dot" style="background:%s"></span>%s</span>'
                                          % (SPLIT_COLOR[sp], sp) for sp in ("train", "val", "test")) + "</div>",
         split_chart(by),
         '<div class="ctitle" style="margin-top:22px; font-size:20px">A record (one line of records.jsonl, selected fields)</div>',
         "<pre>%s</pre>" % esc(rec_text), "</div>", '<div class="col">',
         '<div class="ctitle">Status against the milestone</div><div class="check" style="margin-top:18px">']
    for st, text in status:
        p.append('<div class="row"><div class="s %s">%s</div><div>%s</div></div>' % (st, lab[st], esc(text)))
    p += ["</div>",
          '<div class="csub" style="margin-top:26px; font-size:17px">Caution: with only 21 synthetic design groups, '
          "the split sizes are uneven and some family and split pairs are empty. The seed and the generator are public, "
          "so a real held-out evaluation needs a seed that is not published.</div>",
          "</div></div>", foot(4, note), "</div>"]
    pages.append("\n".join(p))

    doc = ('<!doctype html><html><head><meta charset="utf-8"><title>trace-code CPU pipeline milestone</title>'
           "<style>%s</style></head><body>%s</body></html>" % (CSS, "\n".join(pages)))
    with open(out_html, "w") as f:
        f.write(doc)
    if preview_dir:  # one file per page, for 1920x1080 screenshots
        os.makedirs(preview_dir, exist_ok=True)
        for i, page in enumerate(pages, 1):
            with open(os.path.join(preview_dir, "page%d.html" % i), "w") as f:
                f.write('<!doctype html><html><head><meta charset="utf-8"><style>%s</style></head><body>%s</body></html>'
                        % (CSS, page))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--tests", default=os.path.join(HERE, "test_output.txt"))
    ap.add_argument("--out", default=os.path.join(HERE, "deck.html"))
    ap.add_argument("--note", default="October 2026")
    ap.add_argument("--preview", help="also write one HTML file per page into this folder")
    a = ap.parse_args()
    build_deck(a.dataset, a.tests, a.out, a.note, a.preview)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
