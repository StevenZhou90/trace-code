# LoRA fine-tuning and generation

`lora.py` fine-tunes Qwen/Qwen2.5-Coder-1.5B-Instruct with LoRA on `train.jsonl` / `val.jsonl`
(records `{"task_id", "family", "prompt", "completion"}`), with loss only on the assistant turn.
`generate.py` writes `candidates.jsonl` (`{"task_id", "family", "verilog", "raw"}`) for an eval jsonl.
Both use the same system message and chat template (defined in `lora.py`). Grading happens elsewhere.

Copy code and data to the GPU machine:

    scp -r train ubuntu@GPU:~/trace-train/
    scp DATA/train.jsonl DATA/val.jsonl DATA/eval*.jsonl ubuntu@GPU:~/trace-train/data/

On the GPU machine (run long jobs with nohup so an SSH drop does not kill them):

    cd ~/trace-train
    nohup ~/venv/bin/python train/lora.py --train data/train.jsonl --val data/val.jsonl --out runs/lora1 > lora1.log 2>&1 &
    nohup ~/venv/bin/python train/generate.py --eval data/eval.jsonl --adapter runs/lora1 --out out/cand_lora1.jsonl > gen1.log 2>&1 &
    # base model: leave out --adapter; pass@k: add --samples 10 --temperature 0.8
    # quick smoke test: add --limit 40 --epochs 1 to lora.py
    # memory: lora.py peaks near 32 GB at 4096 tokens with --batch 4; use --batch 2 --accum 8 if it runs out.
    # generate.py caps each batch by --batch (sequences) and --batch-tokens; lower --batch-tokens on out-of-memory.

`runs/lora1/run.json` holds the arguments, example counts, token-length stats, loss history,
throughput, peak GPU memory and wall-clock time. Copy candidates back for grading:

    scp ubuntu@GPU:~/trace-train/out/cand_lora1.jsonl results/
