"""Merge a LoRA adapter into its base model and save the result, so vLLM can load it as a plain model.

    python train/merge.py --adapter runs/lora1 --out runs/lora1/merged [--model BASE]
"""
import argparse
import json
import os

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default=None, help="base model (default: the one in the adapter config)")
    a = ap.parse_args()
    with open(os.path.join(a.adapter, "adapter_config.json")) as f:
        base = a.model or json.load(f)["base_model_name_or_path"]
    model = AutoModelForCausalLM.from_pretrained(base, dtype=torch.bfloat16)
    model = PeftModel.from_pretrained(model, a.adapter).merge_and_unload()
    model.save_pretrained(a.out)
    AutoTokenizer.from_pretrained(base).save_pretrained(a.out)
    print("merged", base, "+", a.adapter, "->", a.out)


if __name__ == "__main__":
    main()
