"""Shared by training and generation: the model name, the system message and the chat layout."""
import json

MODEL = "Qwen/Qwen2.5-Coder-1.5B-Instruct"
SYSTEM = ("You are an expert hardware engineer. Given a cycle-by-cycle trace of a hardware block, "
          "write synthesizable Verilog for a module named dut that reproduces it.")


def read_jsonl(path, limit=None):
    with open(path) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    return rows[:limit] if limit else rows


def chat(prompt, completion=None):
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]
    if completion is not None:
        msgs.append({"role": "assistant", "content": completion})
    return msgs
