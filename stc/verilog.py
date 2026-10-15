"""Small text-level Verilog helpers: comment stripping, safety scan, module and port parsing.

This is not a Verilog parser. It understands the plain module headers this project produces and
accepts (ANSI or non-ANSI port lists, constant or simple parameter-based ranges). Anything it cannot
read is reported, never guessed.
"""
import ast
import re

# System tasks a candidate may use. Everything else ($fopen, $system, $readmemh, $dumpfile, plusargs, ...)
# is rejected before compiling, so untrusted RTL cannot touch files or the host.
SAFE_SYSTEM_TASKS = {
    "$display", "$write", "$strobe", "$monitor", "$finish", "$stop", "$fatal", "$error", "$warning",
    "$info", "$signed", "$unsigned", "$clog2", "$bits", "$time", "$stime", "$realtime", "$random",
}
KEYWORDS = {"input", "output", "inout", "wire", "reg", "logic", "var", "signed", "unsigned", "integer"}


def strip_comments(text):
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def unsafe_constructs(text):
    """Return a sorted list of reasons this source must not be compiled (empty list = allowed)."""
    code = strip_comments(text)
    bad = {"system_task:" + t for t in re.findall(r"\$[A-Za-z_][\w$]*", code) if t not in SAFE_SYSTEM_TASKS}
    if re.search(r"`\s*include\b", code):
        bad.add("include_directive")
    return sorted(bad)


def modules(text):
    """[(name, header_and_body)] for every module in the source, comments removed."""
    code = strip_comments(text)
    return [(m.group(1), m.group(2)) for m in re.finditer(r"\bmodule\s+([A-Za-z_]\w*)(.*?)\bendmodule\b", code, re.S)]


def _verilog_number(tok):
    m = re.fullmatch(r"(\d+)?'[sS]?([dDhHbBoO])([0-9a-fA-F_]+)", tok)
    if not m:
        return tok
    base = {"d": 10, "h": 16, "b": 2, "o": 8}[m.group(2).lower()]
    return str(int(m.group(3).replace("_", ""), base))


def const_eval(expr, params):
    """Evaluate a constant integer expression using known parameters. Returns None if it cannot."""
    expr = re.sub(r"\d*'[sS]?[dDhHbBoO][0-9a-fA-F_]+", lambda m: _verilog_number(m.group(0)), expr.strip())
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return None
    ops = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
           ast.Div: lambda a, b: a // b, ast.FloorDiv: lambda a, b: a // b, ast.Mod: lambda a, b: a % b,
           ast.LShift: lambda a, b: a << b, ast.RShift: lambda a, b: a >> b}

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, int):
            return n.value
        if isinstance(n, ast.Name) and n.id in params:
            return params[n.id]
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.USub):
            return -ev(n.operand)
        if isinstance(n, ast.BinOp) and type(n.op) in ops:
            return ops[type(n.op)](ev(n.left), ev(n.right))
        raise ValueError(expr)

    try:
        return ev(tree)
    except (ValueError, ZeroDivisionError, TypeError):
        return None


def ports(body):
    """Ports of one module body, in declaration order: [{name, dir, width, signed}].
    width is None when the range cannot be evaluated."""
    body = re.sub(r"\bfunction\b.*?\bendfunction\b", " ", body, flags=re.S)
    body = re.sub(r"\btask\b.*?\bendtask\b", " ", body, flags=re.S)
    params = {}
    for name, expr in re.findall(r"\b(?:parameter|localparam)\b\s*(?:integer\s+)?(?:\[[^\]]*\]\s*)?(\w+)\s*=\s*([^,;)]+)", body):
        v = const_eval(expr, params)
        if v is not None:
            params[name] = v
    toks = re.findall(r"\[[^\]]*\]|[A-Za-z_][\w$]*|[;,()=]|\S", body)
    found, order = {}, []
    i = 0
    while i < len(toks):
        if toks[i] not in ("input", "output", "inout"):
            i += 1
            continue
        direction, signed, width = toks[i], False, 1
        i += 1
        while i < len(toks):
            t = toks[i]
            if t in ("input", "output", "inout"):
                break  # next ANSI declaration
            if t in ("wire", "reg", "logic", "var", "unsigned"):
                pass
            elif t == "signed":
                signed = True
            elif t.startswith("["):
                lo_hi = t[1:-1].split(":")
                vals = [const_eval(x, params) for x in lo_hi] if len(lo_hi) == 2 else [None]
                width = None if None in vals else abs(vals[0] - vals[1]) + 1
            elif re.fullmatch(r"[A-Za-z_]\w*", t) and t not in KEYWORDS:
                if t not in found:
                    order.append(t)
                found[t] = {"name": t, "dir": direction, "width": width, "signed": signed}
            elif t == "=":  # skip an initializer up to the next separator
                while i + 1 < len(toks) and toks[i + 1] not in (",", ";", ")"):
                    i += 1
            elif t in (";", ")"):
                break
            i += 1
    return [found[n] for n in order]
