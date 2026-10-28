"""Generate Verilog candidates for an eval jsonl with the base model or a LoRA adapter.

    python train/generate.py --eval eval.jsonl --out candidates.jsonl [--adapter runs/lora1]
                             [--samples N --temperature 0.8] [--batch 16] [--max-new-tokens 1024]

Writes one line per (task, sample): {"task_id", "family", "verilog", "raw"}, plus "sample" when N > 1.
"""
import argparse
import json
import re
import time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from lora import MODEL, chat, read_jsonl

FENCE = re.compile(r"```(?:verilog|systemverilog|v)?\s*\n(.*?)```", re.S)


def extract(raw):
    """The module text: inside the first code fence if any, from the first `module` to the last `endmodule`."""
    m = FENCE.search(raw)
    text = m.group(1) if m else raw
    start, end = text.find("module"), text.rfind("endmodule")
    if start < 0 or end < start:
        return ""
    return text[start:end + len("endmodule")] + "\n"


def make_batches(lens, samples, max_seqs, max_tokens, max_new):
    """Group prompts of similar length (less padding) under a sequence cap and a token budget."""
    batches, cur = [], []
    for i in sorted(range(len(lens)), key=lambda i: lens[i]):
        n = (len(cur) + 1) * samples
        if cur and (n > max_seqs or n * (lens[i] + max_new) > max_tokens):
            batches.append(cur)
            cur = []
        cur.append(i)
    return batches + [cur] if cur else batches


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--adapter", default=None)
    ap.add_argument("--samples", type=int, default=1)
    ap.add_argument("--temperature", type=float, default=0.8, help="used only when --samples > 1")
    ap.add_argument("--top-p", type=float, default=0.95)
    ap.add_argument("--batch", type=int, default=64, help="max sequences per batch (prompts x samples)")
    ap.add_argument("--batch-tokens", type=int, default=200000,
                    help="max sequences x (prompt + new tokens) per batch, to bound GPU memory")
    ap.add_argument("--max-new-tokens", type=int, default=1024)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    tok = AutoTokenizer.from_pretrained(args.model, padding_side="left")
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.bfloat16, attn_implementation="sdpa")
    if args.adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, args.adapter).merge_and_unload()
    model.to("cuda").eval()

    rows = read_jsonl(args.eval, args.limit)
    texts = [tok.apply_chat_template(chat(r["prompt"]), tokenize=False, add_generation_prompt=True) for r in rows]
    lens = [len(ids) for ids in tok(texts, add_special_tokens=False)["input_ids"]]
    batches = make_batches(lens, args.samples, args.batch, args.batch_tokens, args.max_new_tokens)
    sample = args.samples > 1
    gen = dict(max_new_tokens=args.max_new_tokens, num_return_sequences=args.samples, do_sample=sample,
               pad_token_id=tok.pad_token_id)
    if sample:
        gen.update(temperature=args.temperature, top_p=args.top_p)
    else:  # clear the sampling defaults in the model's generation config to avoid warnings
        gen.update(temperature=None, top_p=None, top_k=None)

    results, new_tokens, t0 = {}, 0, time.time()
    for idx in batches:
        enc = tok([texts[i] for i in idx], return_tensors="pt", padding=True, add_special_tokens=False).to("cuda")
        with torch.no_grad():
            out = model.generate(**enc, **gen)
        out = out[:, enc["input_ids"].shape[1]:]
        new_tokens += int((out != tok.pad_token_id).sum())
        raws = tok.batch_decode(out, skip_special_tokens=True)
        for j, i in enumerate(idx):
            results[i] = raws[j * args.samples:(j + 1) * args.samples]
        print(f"{len(results)}/{len(rows)} prompts, {new_tokens / (time.time() - t0):.0f} new tokens/s", flush=True)
    secs = time.time() - t0

    with open(args.out, "w") as f:
        for i, r in enumerate(rows):
            for k, raw in enumerate(results[i]):
                rec = {"task_id": r["task_id"], "family": r["family"], "verilog": extract(raw), "raw": raw}
                if sample:
                    rec["sample"] = k
                f.write(json.dumps(rec) + "\n")
    found = sum(1 for i in results for raw in results[i] if extract(raw))
    print(f"wrote {args.out}: {len(rows)} prompts x {args.samples} samples, {found} with a module; "
          f"{new_tokens} new tokens in {secs:.1f}s = {new_tokens / secs:.0f} tokens/s, "
          f"peak GPU memory {torch.cuda.max_memory_allocated() / 2**30:.1f} GB")


if __name__ == "__main__":
    main()
