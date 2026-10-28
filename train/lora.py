"""LoRA supervised fine-tuning of a small code model on trace-to-Verilog records.

    python train/lora.py --train train.jsonl --val val.jsonl --out runs/lora1 [--epochs 3] [--limit 40]

Each record is {"task_id", "family", "prompt", "completion"}. The chat is system + user (prompt) +
assistant (completion); loss is computed only on the assistant tokens. Writes the adapter and
run.json (arguments, counts, token-length stats, loss history, wall-clock time) to --out.
"""
import argparse
import json
import os
import statistics
import time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments
from peft import LoraConfig, get_peft_model

MODEL = "Qwen/Qwen2.5-Coder-1.5B-Instruct"
SYSTEM = ("You are an expert hardware engineer. Given a cycle-by-cycle trace of a hardware block, "
          "write synthesizable Verilog for a module named dut that reproduces it.")
TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]


def read_jsonl(path, limit=None):
    with open(path) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    return rows[:limit] if limit else rows


def chat(prompt, completion=None):
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]
    if completion is not None:
        msgs.append({"role": "assistant", "content": completion})
    return msgs


def encode(tok, row):
    """Token ids for the full chat, with labels masked to -100 outside the assistant turn."""
    prefix = tok.apply_chat_template(chat(row["prompt"]), tokenize=False, add_generation_prompt=True)
    full = tok.apply_chat_template(chat(row["prompt"], row["completion"]), tokenize=False)
    assert full.startswith(prefix), "chat template prefix mismatch"
    p = tok(prefix, add_special_tokens=False)["input_ids"]
    ids = tok(full, add_special_tokens=False)["input_ids"]
    return {"input_ids": ids, "labels": [-100] * len(p) + ids[len(p):]}


def encode_all(tok, rows, max_len, name):
    kept, dropped = [], []
    for r in rows:
        e = encode(tok, r)
        if len(e["input_ids"]) <= max_len:
            kept.append(e)
        else:
            dropped.append(r["task_id"])
    lens = [len(e["input_ids"]) for e in kept]
    stats = {"n": len(rows), "kept": len(kept), "dropped_too_long": len(dropped),
             "dropped_ids": dropped[:50], "tokens": sum(lens),
             "len_min": min(lens, default=0), "len_median": statistics.median(lens) if lens else 0,
             "len_max": max(lens, default=0),
             "target_tokens": sum(sum(1 for x in e["labels"] if x != -100) for e in kept)}
    print(f"{name}: {len(kept)} kept, {len(dropped)} dropped (> {max_len} tokens), "
          f"median {stats['len_median']} max {stats['len_max']} tokens")
    return kept, stats


class Collator:
    """Right-pad a batch; padding is masked from attention and loss."""

    def __init__(self, pad_id):
        self.pad_id = pad_id

    def __call__(self, batch):
        n = max(len(b["input_ids"]) for b in batch)
        ids, labels, mask = [], [], []
        for b in batch:
            k = n - len(b["input_ids"])
            ids.append(b["input_ids"] + [self.pad_id] * k)
            labels.append(b["labels"] + [-100] * k)
            mask.append([1] * len(b["input_ids"]) + [0] * k)
        return {"input_ids": torch.tensor(ids), "labels": torch.tensor(labels),
                "attention_mask": torch.tensor(mask)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", required=True)
    ap.add_argument("--val", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--epochs", type=float, default=3)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--alpha", type=int, default=32)
    ap.add_argument("--dropout", type=float, default=0.05)
    ap.add_argument("--max-len", type=int, default=4096)
    ap.add_argument("--batch", type=int, default=4, help="per-device batch size")
    ap.add_argument("--accum", type=int, default=4, help="gradient accumulation steps")
    ap.add_argument("--warmup", type=float, default=0.03, help="warmup as a fraction of total steps")
    ap.add_argument("--limit", type=int, default=None, help="use only the first N train and val records")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--no-checkpointing", action="store_true", help="disable gradient checkpointing")
    args = ap.parse_args()

    t0 = time.time()
    tok = AutoTokenizer.from_pretrained(args.model)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    train, train_stats = encode_all(tok, read_jsonl(args.train, args.limit), args.max_len, "train")
    val, val_stats = encode_all(tok, read_jsonl(args.val, args.limit), args.max_len, "val")

    model = AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.bfloat16, attn_implementation="sdpa")
    model = get_peft_model(model, LoraConfig(r=args.rank, lora_alpha=args.alpha, lora_dropout=args.dropout,
                                             target_modules=TARGETS, task_type="CAUSAL_LM"))
    model.print_trainable_parameters()

    targs = TrainingArguments(
        output_dir=os.path.join(args.out, "checkpoints"), num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch, per_device_eval_batch_size=args.batch,
        gradient_accumulation_steps=args.accum, learning_rate=args.lr, lr_scheduler_type="cosine",
        warmup_steps=args.warmup, bf16=True, logging_steps=1, eval_strategy="epoch", save_strategy="no",
        gradient_checkpointing=not args.no_checkpointing,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        remove_unused_columns=False, report_to=[], seed=args.seed, dataloader_num_workers=2)
    trainer = Trainer(model=model, args=targs, train_dataset=train, eval_dataset=val,
                      data_collator=Collator(tok.pad_token_id))
    val_before = trainer.evaluate()["eval_loss"]
    torch.cuda.reset_peak_memory_stats()
    result = trainer.train()
    model.save_pretrained(args.out)
    tok.save_pretrained(args.out)

    hist = trainer.state.log_history
    train_time = result.metrics["train_runtime"]
    run = {"args": vars(args), "system": SYSTEM, "train": train_stats, "val": val_stats,
           "train_loss": [{"epoch": h["epoch"], "step": h["step"], "loss": h["loss"]} for h in hist if "loss" in h],
           "val_loss": [{"epoch": 0, "loss": val_before}] +
                       [{"epoch": h["epoch"], "loss": h["eval_loss"]} for h in hist if "eval_loss" in h and h["epoch"] > 0],
           "train_runtime_s": train_time,
           "train_tokens_per_s": train_stats["tokens"] * args.epochs / train_time,
           "peak_gpu_mem_gb": torch.cuda.max_memory_allocated() / 2**30,
           "wall_clock_s": time.time() - t0}
    with open(os.path.join(args.out, "run.json"), "w") as f:
        json.dump(run, f, indent=1)
    print(json.dumps({k: run[k] for k in ("val_loss", "train_tokens_per_s", "peak_gpu_mem_gb", "wall_clock_s")}))


if __name__ == "__main__":
    main()
