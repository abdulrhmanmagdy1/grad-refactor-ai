"""T05 reload check: load a saved LoRA adapter in a fresh process and measure its effect.

Run with the training environment from the repository root, for example:

    .venv-train/Scripts/python.exe -X utf8 training/check_adapter.py \
        --adapter-dir runs/training/pilot-full/adapter \
        --dataset training/pilot/pilot-records.jsonl \
        --out experiments/training/pilot-2026-10-20-reload-check.json

The adapter is loaded through model_worker.TorchBackend, the code path the
LocalProvider worker uses. For every validation record (never the test split) and
every benchmark pilot function it compares the adapter turned on and off (PEFT
disable_adapter, which is how use_adapter=false runs the base model): the largest
logit difference at the last prompt position, the teacher-forced loss of the reference
completion (validation records only), and the greedy outputs with their parse and
rubric results. Pilot results show that the adapter loads and changes the model; they
are not an evaluation of quality.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

from common import ROOT, load_worker_module, require_free_disk, sha256_file
from pilot.functions import pilot_functions
from train_lora import end_of_turn

from refactor_ai import task_format
from refactor_ai.tasks import guard_clauses

MODEL_ID = "Qwen/Qwen2.5-Coder-0.5B-Instruct"
MODEL_REVISION = "ea3f2471cf1b1f0db85067f1ef93848e38e88c25"


def main() -> int:
    parser = argparse.ArgumentParser(description="LoRA adapter reload check")
    parser.add_argument("--adapter-dir", required=True, type=Path)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--model-dir", type=Path, default=ROOT / "models" / MODEL_ID.split("/")[1])
    parser.add_argument("--max-new-tokens", type=int, default=512)
    parser.add_argument(
        "--base-benchmark",
        type=Path,
        help="T04 benchmark record whose greedy base-model outputs the disabled adapter must match",
    )
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    require_free_disk(min_mb=1500, needed_mb=5)
    worker = load_worker_module()
    adapter_sha = sha256_file(args.adapter_dir / "adapter_model.safetensors")
    backend = worker.TorchBackend(
        worker.LoadSettings(
            model_dir=args.model_dir.resolve(),
            model_id=MODEL_ID,
            model_revision=MODEL_REVISION,
            adapter_dir=args.adapter_dir.resolve(),
            adapter_id=args.adapter_dir.parent.name,
            adapter_sha256=adapter_sha,
            device="cuda",
            dtype="bfloat16",
        )
    )
    import torch

    model, tokenizer = backend.model, backend.tokenizer
    eot_id, _ = end_of_turn(tokenizer, backend.eos_token_ids)
    rows = [
        json.loads(line)
        for line in args.dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    validation = [r for r in rows if r["split"] == "validation"]
    items = [
        {"id": r["id"], "kind": "validation", "code": r["original_code"], "row": r}
        for r in validation
    ] + [
        {"id": f["id"], "kind": "benchmark", "code": f["code"], "row": None}
        for f in pilot_functions("benchmark")
    ]

    def last_logits(ids, use_adapter: bool):
        context = model.disable_adapter() if not use_adapter else torch.no_grad()
        with torch.inference_mode(), context:
            return model(input_ids=ids, logits_to_keep=1).logits[0, -1].float()

    def completion_loss(row: dict, use_adapter: bool) -> float:
        messages = task_format.messages_from_prompt(row["prompt"])
        prefix = tokenizer(worker.chat_prompt_text(tokenizer, messages), add_special_tokens=False)[
            "input_ids"
        ]
        target = tokenizer(row["completion"], add_special_tokens=False)["input_ids"] + [eot_id]
        ids = torch.tensor([prefix + target], device="cuda:0")
        labels = torch.tensor([[-100] * len(prefix) + target], device="cuda:0")
        context = model.disable_adapter() if not use_adapter else torch.no_grad()
        with torch.inference_mode(), context:
            return float(model(input_ids=ids, labels=labels).loss)

    results = []
    for item in items:
        messages = task_format.build_refactor_messages(item["code"])
        ids = backend.prompt_ids(messages).to("cuda:0")
        on, off = last_logits(ids, True), last_logits(ids, False)
        entry = {
            "id": item["id"],
            "kind": item["kind"],
            "max_abs_logit_diff_last_prompt_position": round(float((on - off).abs().max()), 4),
            "argmax_same": int(on.argmax()) == int(off.argmax()),
        }
        if item["row"] is not None:
            entry["reference_completion_loss"] = {
                "adapter": round(completion_loss(item["row"], True), 4),
                "base": round(completion_loss(item["row"], False), 4),
            }
        for label, use_adapter in (("adapter", True), ("base", False)):
            output = backend.generate(
                worker.GenerateRequest(
                    id=f"{item['id']}-{label}",
                    messages=messages,
                    max_new_tokens=args.max_new_tokens,
                    temperature=0.0,
                    top_p=1.0,
                    seed=42,
                    max_input_tokens=32768,
                    use_adapter=use_adapter,
                )
            )
            parsed = task_format.parse_refactor_output(output["text"])
            rubric = guard_clauses.rubric(item["code"], parsed.code) if parsed.code else None
            entry[label] = {
                "completion_tokens": output["completion_tokens"],
                "finish_reason": output["finish_reason"],
                "generation_s": output["generation_s"],
                "parse_error": parsed.error,
                "rubric_passed": None if rubric is None else rubric.passed,
                "same_as_reference": bool(parsed.code)
                and guard_clauses.same_code(
                    parsed.code, guard_clauses.to_guard_clauses(item["code"])
                ),
                "raw_output": output["text"],
            }
        entry["outputs_differ"] = entry["adapter"]["raw_output"] != entry["base"]["raw_output"]
        results.append(entry)
        print(
            f"{item['id']}: logit diff {entry['max_abs_logit_diff_last_prompt_position']}, "
            f"outputs differ {entry['outputs_differ']}, adapter parse "
            f"{entry['adapter']['parse_error'] or 'ok'} rubric {entry['adapter']['rubric_passed']}",
            flush=True,
        )

    def count(kind: str, label: str, key: str) -> int:
        return sum(bool(r[label][key]) for r in results if r["kind"] == kind)

    losses = [r["reference_completion_loss"] for r in results if "reference_completion_loss" in r]
    record = {
        "record": "T05 adapter reload check in a fresh process (pilot material; not an evaluation)",
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "command": " ".join([Path(sys.executable).name, *sys.argv]),
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "adapter_dir": str(args.adapter_dir).replace("\\", "/"),
        "adapter_sha256": adapter_sha,
        "adapter_sha256_reported_by_worker": backend.adapter_sha256,
        "dataset_sha256": sha256_file(args.dataset),
        "load_s": round(backend.load_s, 2),
        "versions": backend.versions,
        "summary": {
            "items": len(results),
            "max_abs_logit_diff_max": max(
                r["max_abs_logit_diff_last_prompt_position"] for r in results
            ),
            "outputs_differ": sum(r["outputs_differ"] for r in results),
            "validation_mean_reference_loss": {
                key: round(sum(x[key] for x in losses) / len(losses), 4) if losses else None
                for key in ("adapter", "base")
            },
            "parse_ok": {
                kind: {
                    label: sum(
                        r[label]["parse_error"] is None for r in results if r["kind"] == kind
                    )
                    for label in ("adapter", "base")
                }
                for kind in ("validation", "benchmark")
            },
            "rubric_passed": {
                kind: {label: count(kind, label, "rubric_passed") for label in ("adapter", "base")}
                for kind in ("validation", "benchmark")
            },
        },
        "items": results,
    }
    if args.base_benchmark is not None:
        recorded = json.loads(args.base_benchmark.read_text(encoding="utf-8"))
        base_outputs = {c["case_id"]: c.get("raw_output") for c in recorded["cases"]}
        compared = [r for r in results if r["kind"] == "benchmark" and r["id"] in base_outputs]
        record["summary"]["disabled_adapter_matches_separate_base_process"] = {
            "benchmark_record": args.base_benchmark.name,
            "compared": len(compared),
            "identical": sum(r["base"]["raw_output"] == base_outputs[r["id"]] for r in compared),
        }
    if any(math.isnan(x["adapter"]) or math.isnan(x["base"]) for x in losses):
        record["failures"] = ["NaN loss"]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(record["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
