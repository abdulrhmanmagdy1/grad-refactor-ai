"""Measure LoRA training memory and step time against sequence length (T05 budget).

Run with the training environment from the repository root, for example:

    .venv-train/Scripts/python.exe -X utf8 training/probe_training_memory.py \
        --out experiments/training/2026-10-20-training-memory-probe.json

For each length it runs one forward and backward pass of the pilot LoRA configuration
(bf16 base, fp32 adapters, batch size 1) on a sequence cut from real pilot text, with
the last 45% of the positions as labels (about the completion share of the long pilot
records), and records PyTorch's peak memory and the step time. Out-of-memory is
recorded as a result, not hidden. Nothing is written to disk except the record.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from common import ROOT, gpu_used_mib, load_worker_module, nvidia_smi, require_free_disk
from pilot.functions import maximal_inputs

from refactor_ai import task_format
from refactor_ai.tasks import guard_clauses

MODEL_DIR = ROOT / "models" / "Qwen2.5-Coder-0.5B-Instruct"
TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]


def main() -> int:
    parser = argparse.ArgumentParser(description="LoRA training memory probe")
    parser.add_argument("--lengths", default="512,768,1024,1280,1536,2048")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    require_free_disk(min_mb=1500, needed_mb=5)
    import torch
    from peft import LoraConfig, TaskType, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    worker = load_worker_module()
    tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR, local_files_only=True)
    # Real text: the chat-formatted refactoring prompts and reference completions of the
    # maximal pilot inputs, concatenated, so every probe length has realistic tokens.
    pool: list[int] = []
    for code in maximal_inputs().values():
        messages = task_format.build_refactor_messages(code)
        pool += tokenizer(worker.chat_prompt_text(tokenizer, messages), add_special_tokens=False)[
            "input_ids"
        ]
        target = task_format.render_refactor_completion(
            "Handled each special case first.", guard_clauses.to_guard_clauses(code)
        )
        pool += tokenizer(target, add_special_tokens=False)["input_ids"]
    lengths = [int(x) for x in args.lengths.split(",")]
    if max(lengths) > len(pool):
        raise SystemExit(f"the text pool has only {len(pool)} tokens")

    record = {
        "record": "T05 training memory probe (one LoRA step per length; pilot text)",
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "command": " ".join([Path(sys.executable).name, *sys.argv]),
        "gpu": nvidia_smi("name,memory.total,driver_version"),
        "gpu_used_mib_all_processes_before_load": gpu_used_mib(),
        "lora": {"r": 8, "alpha": 16, "dropout": 0.05, "target_modules": TARGET_MODULES},
        "precision": "bf16 base weights, fp32 LoRA weights, bf16 autocast",
        "batch_size": 1,
        "label_share": 0.45,
        "results": [],
    }
    for checkpointing in (False, True):
        model = AutoModelForCausalLM.from_pretrained(
            MODEL_DIR, dtype=torch.bfloat16, local_files_only=True, device_map={"": "cuda:0"}
        )
        model.config.use_cache = False
        if checkpointing:
            model.gradient_checkpointing_enable(
                gradient_checkpointing_kwargs={"use_reentrant": False}
            )
            model.enable_input_require_grads()
        model = get_peft_model(
            model,
            LoraConfig(
                task_type=TaskType.CAUSAL_LM,
                r=8,
                lora_alpha=16,
                lora_dropout=0.05,
                target_modules=TARGET_MODULES,
                bias="none",
            ),
        )
        for parameter in model.parameters():
            if parameter.requires_grad:
                parameter.data = parameter.data.float()
        model.train()
        optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=1e-4)
        warm = torch.tensor([pool[:128]], device="cuda:0")  # unrecorded warm-up step
        with torch.autocast("cuda", dtype=torch.bfloat16):
            model(input_ids=warm, labels=warm).loss.backward()
        optimizer.zero_grad(set_to_none=True)
        for length in lengths:
            ids = torch.tensor([pool[:length]], device="cuda:0")
            labels = ids.clone()
            labels[0, : int(length * (1 - record["label_share"]))] = -100
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
            entry = {"gradient_checkpointing": checkpointing, "length": length}
            try:
                torch.cuda.synchronize()
                started = time.perf_counter()
                with torch.autocast("cuda", dtype=torch.bfloat16):
                    loss = model(input_ids=ids, labels=labels).loss
                loss.backward()
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)
                torch.cuda.synchronize()
                entry.update(
                    status="ok",
                    step_s=round(time.perf_counter() - started, 3),
                    loss=round(float(loss), 4),
                    peak_allocated_mib=round(torch.cuda.max_memory_allocated() / 2**20, 1),
                    peak_reserved_mib=round(torch.cuda.max_memory_reserved() / 2**20, 1),
                )
            except torch.OutOfMemoryError:
                optimizer.zero_grad(set_to_none=True)
                entry.update(status="out_of_memory")
            loss = None
            torch.cuda.empty_cache()
            entry["gpu_used_mib_all_processes_after"] = gpu_used_mib()
            record["results"].append(entry)
            print(json.dumps(entry), flush=True)
        del model, optimizer
        torch.cuda.empty_cache()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
