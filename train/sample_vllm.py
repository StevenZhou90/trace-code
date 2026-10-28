"""Draw many samples per eval prompt with vLLM (for search against the visible trace).

    python train/sample_vllm.py --model runs/q7_abc/merged --eval eval_test_C.jsonl --out samples.jsonl \
        [--n 32] [--temperature 0.8] [--max-tokens 1536]

Writes one line per (task, sample): {"task_id", "family", "level", "sample", "verilog", "raw"}, with the
same system message and code extraction as generate.py. Runs in its own environment (vLLM brings its
own torch), so it imports only the standard library and common.py.
"""
import argparse
import json
import re
import time

from vllm import LLM, SamplingParams

from common import chat, read_jsonl

FENCE = re.compile(r"```(?:verilog|systemverilog|v)?\s*\n(.*?)```", re.S)


def extract(raw):
    m = FENCE.search(raw)
    text = m.group(1) if m else raw
    start, end = text.find("module"), text.rfind("endmodule")
    return text[start:end + len("endmodule")] + "\n" if 0 <= start < end else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--eval", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=32)
    ap.add_argument("--temperature", type=float, default=0.8)
    ap.add_argument("--top-p", type=float, default=0.95)
    ap.add_argument("--max-tokens", type=int, default=1536)
    ap.add_argument("--max-model-len", type=int, default=16384)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    rows = read_jsonl(a.eval, a.limit)
    llm = LLM(model=a.model, dtype="bfloat16", max_model_len=a.max_model_len, seed=a.seed,
              gpu_memory_utilization=0.9, enable_prefix_caching=True)
    greedy = a.n == 1 and a.temperature == 0
    params = SamplingParams(n=a.n, temperature=a.temperature, top_p=1.0 if greedy else a.top_p,
                            max_tokens=a.max_tokens, seed=a.seed)
    t0 = time.time()
    outs = llm.chat([chat(r["prompt"]) for r in rows], params, use_tqdm=True)
    secs = time.time() - t0
    tokens = 0
    with open(a.out, "w") as f:
        for r, o in zip(rows, outs):
            for k, c in enumerate(o.outputs):
                tokens += len(c.token_ids)
                f.write(json.dumps({"task_id": r["task_id"], "family": r["family"], "level": r.get("level", "A"),
                                    "sample": k, "verilog": extract(c.text), "raw": c.text}) + "\n")
    print("wrote %s: %d prompts x %d samples, %d tokens in %.0fs = %.0f tokens/s"
          % (a.out, len(rows), a.n, tokens, secs, tokens / secs))


if __name__ == "__main__":
    main()
