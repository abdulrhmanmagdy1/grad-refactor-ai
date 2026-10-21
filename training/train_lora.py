"""LoRA fine-tuning of the refactoring role (T05 pilot, T17 training run).

The training text equals the inference text token for token. The masked prefix is the
refactoring-role chat, task_format.messages_from_prompt(record["prompt"]), rendered by
model_worker.chat_prompt_text (the chat template with the assistant turn opened, the
same function the LocalProvider worker uses) and tokenized without extra special
tokens. The target is record["completion"] followed by the token that closes an
assistant turn in the chat template (<|im_end|> for Qwen2.5 instruct models), which is
one of the model's end-of-sequence ids, so generation stops there. Before training,
every record is compared with the template's own rendering of the full conversation.

Protections: unknown keys or unresolved CHOOSE values in the config stop the run; the
dataset must pass scripts/validate_dataset.py, contain only guard_clauses records and
match the current prompt version; only split "train" is trained on and "validation"
evaluated, "test" records never reach the Trainer; records longer than max_length stop
the run (curate them, never truncate silently); a CUDA GPU is required.

Run with the training environment from the repository root:

    .venv-train/Scripts/python.exe -X utf8 training/train_lora.py --config CONFIG
        [--max-steps N] [--resume-from-checkpoint DIR] [--check-data] [--record PATH]

Relative paths in the config resolve against the config file's directory. The run
manifest (experiments/run-template.json fields plus details) is written to
<output_dir>/run-manifest.json and, with --record, to that path as well.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path

from common import (
    ROOT,
    GpuSampler,
    git_state,
    gpu_used_mib,
    load_worker_module,
    nvidia_smi,
    package_versions,
    require_free_disk,
    sha256_file,
)

from refactor_ai import task_format
from refactor_ai.tasks import guard_clauses

sys.path.insert(0, str(ROOT / "scripts"))
from validate_dataset import load_and_validate  # noqa: E402

REQUIRED = {
    "model_id": str,
    "model_revision": str,
    "model_path": str,
    "dataset": str,
    "output_dir": str,
    "seed": int,
    "max_length": int,
    "lora_rank": int,
    "lora_alpha": int,
    "lora_dropout": float,
    "target_modules": list,
    "learning_rate": float,
    "epochs": (int, float),
    "gradient_accumulation_steps": int,
}
OPTIONAL = {
    "run_id": (str, None),
    "per_device_train_batch_size": (int, 1),
    "warmup_steps": (int, 0),
    "lr_scheduler_type": (str, "linear"),
    "weight_decay": (float, 0.0),
    "logging_steps": (int, 1),
    "eval_steps": (int, None),
    "save_steps": (int, None),
    "save_total_limit": (int, 1),
    "max_steps": (int, -1),
    "gradient_checkpointing": (bool, False),
    "precision": (str, "auto"),
    "load_best_model_at_end": (bool, False),
    "max_runtime_minutes": (float, None),
}
MIN_FREE_MB = 1500


def load_config(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SystemExit("The config must be a JSON object")
    config = {key: value for key, value in raw.items() if not key.startswith("_")}
    unknown = sorted(set(config) - set(REQUIRED) - set(OPTIONAL))
    if unknown:
        raise SystemExit(f"Unknown config keys: {unknown}")
    for key, kind in REQUIRED.items():
        value = config.get(key)
        if value is None or value == "" or (isinstance(value, bool) and kind is not bool):
            raise SystemExit(f"Choose {key} after the hardware and license review")
        if kind is float and isinstance(value, int):
            value = config[key] = float(value)
        if not isinstance(value, kind):
            raise SystemExit(f"{key} has the wrong type")
    for key, (kind, default) in OPTIONAL.items():
        value = config.setdefault(key, default)
        if value is not None and kind is float and isinstance(value, int):
            value = config[key] = float(value)
        if value is not None and (
            not isinstance(value, kind) or (isinstance(value, bool) and kind is not bool)
        ):
            raise SystemExit(f"{key} has the wrong type")
    unresolved = [k for k, v in config.items() if isinstance(v, str) and "CHOOSE" in v]
    if unresolved:
        raise SystemExit(f"Choose {', '.join(unresolved)} after the hardware and license review")
    if len(config["model_revision"]) != 40:
        raise SystemExit("model_revision must be the exact 40-character commit")
    if config["precision"] not in ("auto", "bf16", "fp16", "fp32"):
        raise SystemExit("precision must be auto, bf16, fp16 or fp32")
    modules = config["target_modules"]
    if not modules or not all(isinstance(m, str) and m for m in modules):
        raise SystemExit("target_modules must be a non-empty list of module names")
    return config


def end_of_turn(tokenizer, eos_ids: list[int]) -> tuple[int, str]:
    """The token that closes an assistant turn, read from the chat template itself."""
    worker = load_worker_module()
    probe = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    prefix = worker.chat_prompt_text(tokenizer, probe)
    marker = "MARKER_9f2c"
    full = tokenizer.apply_chat_template(
        probe + [{"role": "assistant", "content": marker}], tokenize=False
    )
    if not full.startswith(prefix + marker):
        raise SystemExit("The chat template does not place the assistant text after the prompt")
    suffix = full[len(prefix + marker) :]
    suffix_ids = tokenizer(suffix, add_special_tokens=False)["input_ids"]
    if not suffix_ids or suffix_ids[0] not in eos_ids:
        raise SystemExit(f"The assistant turn ends with {suffix!r}, not an end-of-sequence token")
    return suffix_ids[0], suffix


def encode(row: dict, tokenizer, eot_id: int) -> dict:
    """Prefix (masked) plus completion and end-of-turn; checked against the template."""
    worker = load_worker_module()
    messages = task_format.messages_from_prompt(row["prompt"])
    prefix_ids = tokenizer(worker.chat_prompt_text(tokenizer, messages), add_special_tokens=False)[
        "input_ids"
    ]
    target_ids = tokenizer(row["completion"], add_special_tokens=False)["input_ids"] + [eot_id]
    full_text = tokenizer.apply_chat_template(
        messages + [{"role": "assistant", "content": row["completion"]}], tokenize=False
    )
    full_ids = tokenizer(full_text, add_special_tokens=False)["input_ids"]
    if full_ids[: len(prefix_ids) + len(target_ids)] != prefix_ids + target_ids:
        raise SystemExit(f"Record {row['id']}: tokens differ from the chat template's rendering")
    ids = prefix_ids + target_ids
    return {
        "input_ids": ids,
        "attention_mask": [1] * len(ids),
        "labels": [-100] * len(prefix_ids) + target_ids,
        "prefix_tokens": len(prefix_ids),
        "target_tokens": len(target_ids),
    }


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="LoRA training for the refactoring role")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--resume-from-checkpoint", type=Path)
    parser.add_argument("--max-steps", type=int, help="override max_steps (smoke runs)")
    parser.add_argument(
        "--stop-after-steps",
        type=int,
        help="simulate an interruption: save a checkpoint and stop after this optimizer step, "
        "keeping the full learning-rate schedule (for resume tests)",
    )
    parser.add_argument("--output-dir", type=Path, help="override output_dir (and run_id)")
    parser.add_argument("--check-data", action="store_true", help="check records and stop")
    parser.add_argument("--record", type=Path, help="also write the manifest to this path")
    args = parser.parse_args()
    config_path = args.config.resolve()
    config = load_config(config_path)
    if args.output_dir is not None:
        config["output_dir"] = str(args.output_dir.resolve())
        config["run_id"] = args.output_dir.name
    if args.max_steps is not None:
        if args.max_steps < 1:
            raise SystemExit("--max-steps must be positive")
        config["max_steps"] = args.max_steps
    if args.stop_after_steps is not None and args.stop_after_steps < 1:
        raise SystemExit("--stop-after-steps must be positive")

    def resolve(value: str) -> Path:
        path = Path(value)
        return (path if path.is_absolute() else config_path.parent / path).resolve()

    model_path = resolve(config["model_path"])
    dataset_path = resolve(config["dataset"])
    output = resolve(config["output_dir"])
    resume = args.resume_from_checkpoint.resolve() if args.resume_from_checkpoint else None
    if resume is not None and not resume.is_dir():
        raise SystemExit("--resume-from-checkpoint must be an existing checkpoint directory")

    rows = load_and_validate(dataset_path)
    wrong_task = [r["id"] for r in rows if r["refactoring_type"] != guard_clauses.TASK_TYPE]
    if wrong_task:
        raise SystemExit(f"Records for another refactoring type: {wrong_task[:10]}")
    stale = [
        r["id"]
        for r in rows
        if "prompt_version" in r and r["prompt_version"] != task_format.PROMPT_VERSION
    ]
    if stale:
        raise SystemExit(f"Records built for another prompt version: {stale[:10]}")
    train_rows = [r for r in rows if r["split"] == "train"]
    validation_rows = [r for r in rows if r["split"] == "validation"]
    test_count = sum(r["split"] == "test" for r in rows)

    from transformers import AutoTokenizer, GenerationConfig

    worker = load_worker_module()
    revision_verified = worker.verify_revision(model_path, config["model_revision"])
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    eos = GenerationConfig.from_pretrained(model_path, local_files_only=True).eos_token_id
    eos_ids = list(eos) if isinstance(eos, list) else [eos]
    if tokenizer.eos_token_id is not None and tokenizer.eos_token_id not in eos_ids:
        eos_ids.append(tokenizer.eos_token_id)
    eot_id, eot_suffix = end_of_turn(tokenizer, eos_ids)
    if tokenizer.pad_token_id is None:
        raise SystemExit("The tokenizer defines no padding token")
    encoded = {
        "train": [encode(r, tokenizer, eot_id) for r in train_rows],
        "validation": [encode(r, tokenizer, eot_id) for r in validation_rows],
    }
    lengths = {
        split: [len(item["input_ids"]) for item in items] for split, items in encoded.items()
    }
    too_long = [
        (row["id"], len(item["input_ids"]))
        for split, source in (("train", train_rows), ("validation", validation_rows))
        for row, item in zip(source, encoded[split], strict=True)
        if len(item["input_ids"]) > config["max_length"]
    ]
    data_report = {
        "dataset": dataset_path.name,
        "dataset_sha256": sha256_file(dataset_path),
        "records": {
            "train": len(train_rows),
            "validation": len(validation_rows),
            "test_excluded": test_count,
        },
        "end_of_turn_token": tokenizer.convert_ids_to_tokens(eot_id),
        "end_of_turn_id": eot_id,
        "template_suffix_after_completion": eot_suffix,
        "eos_ids": eos_ids,
        "max_tokens": {split: max(v, default=0) for split, v in lengths.items()},
        "mean_tokens": {
            split: round(sum(v) / len(v), 1) if v else 0 for split, v in lengths.items()
        },
        "max_length": config["max_length"],
        "records_over_max_length": too_long,
        "revision_verified": revision_verified,
    }
    if args.check_data:
        print(json.dumps(data_report, indent=2, ensure_ascii=False))
        return 1 if too_long else 0
    if too_long:
        raise SystemExit(f"Records exceed max_length (curate them, do not truncate): {too_long}")
    if not train_rows or not validation_rows:
        raise SystemExit("Training needs non-empty train and validation splits")
    require_free_disk(MIN_FREE_MB, needed_mb=300)

    import torch
    import transformers
    from peft import LoraConfig, TaskType, get_peft_model
    from transformers import (
        AutoModelForCausalLM,
        Trainer,
        TrainerCallback,
        TrainingArguments,
    )

    if not torch.cuda.is_available():
        raise SystemExit("CUDA GPU required by this script; review hardware before training")
    transformers.set_seed(config["seed"])
    precision = config["precision"]
    # Native bf16 needs compute capability 8.0 or newer; recent PyTorch also reports
    # emulated bf16 as supported on older GPUs, which is slow, so it is not used.
    native_bf16 = torch.cuda.get_device_capability(0)[0] >= 8
    if precision == "auto":
        precision = "bf16" if native_bf16 else "fp16"
    if precision == "bf16" and not native_bf16:
        raise SystemExit("This GPU has no native bf16 (compute capability below 8.0)")
    load_dtype = {"bf16": torch.bfloat16, "fp16": torch.float16, "fp32": torch.float32}[precision]
    gpu_before_load = gpu_used_mib()
    model = AutoModelForCausalLM.from_pretrained(
        model_path, dtype=load_dtype, local_files_only=True, device_map={"": "cuda:0"}
    )
    model.config.use_cache = False
    if config["gradient_checkpointing"]:
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
        model.enable_input_require_grads()
    model = get_peft_model(
        model,
        LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=config["lora_rank"],
            lora_alpha=config["lora_alpha"],
            lora_dropout=config["lora_dropout"],
            target_modules=config["target_modules"],
            bias="none",
        ),
    )
    # LoRA weights train in fp32 under bf16/fp16 autocast (PEFT upcasts; enforce it).
    for parameter in model.parameters():
        if parameter.requires_grad and parameter.dtype != torch.float32:
            parameter.data = parameter.data.float()
    trainable, total = model.get_nb_trainable_parameters()
    trainable_dtypes = sorted({str(p.dtype) for p in model.parameters() if p.requires_grad})

    class StepMeter(TrainerCallback):
        def __init__(self) -> None:
            self.steps: list[dict] = []
            self._started = 0.0

        def on_step_begin(self, args, state, control, **kwargs):
            torch.cuda.reset_peak_memory_stats()
            self._started = time.perf_counter()

        def on_step_end(self, args, state, control, **kwargs):
            self.steps.append(
                {
                    "step": state.global_step,
                    "seconds": round(time.perf_counter() - self._started, 3),
                    "peak_allocated_mib": round(torch.cuda.max_memory_allocated() / 2**20, 1),
                    "peak_reserved_mib": round(torch.cuda.max_memory_reserved() / 2**20, 1),
                }
            )

    class TimeCap(TrainerCallback):
        """Hard wall-clock cap: checkpoint and stop once the training time is used up."""

        def __init__(self, minutes: float) -> None:
            self.seconds = minutes * 60
            self.started = time.perf_counter()
            self.hit_at_step: int | None = None

        def on_train_begin(self, args, state, control, **kwargs):
            self.started = time.perf_counter()

        def on_step_end(self, args, state, control, **kwargs):
            if time.perf_counter() - self.started > self.seconds and self.hit_at_step is None:
                self.hit_at_step = state.global_step
                control.should_save = True
                control.should_evaluate = True
                control.should_training_stop = True

    class StopAfter(TrainerCallback):
        """Simulated interruption: checkpoint and stop at a step, schedule unchanged."""

        def __init__(self, step: int) -> None:
            self.step = step

        def on_step_end(self, args, state, control, **kwargs):
            if state.global_step >= self.step:
                control.should_save = True
                control.should_training_stop = True

    def as_dataset(items: list[dict]) -> list[dict]:
        """A plain list is a map-style dataset; only the model inputs reach the Trainer."""
        keep = ("input_ids", "attention_mask", "labels")
        return [{key: item[key] for key in keep} for item in items]

    def collate(features):
        size = max(len(f["input_ids"]) for f in features)
        batch = {key: [] for key in ("input_ids", "attention_mask", "labels")}
        for f in features:
            padding = size - len(f["input_ids"])
            batch["input_ids"].append(f["input_ids"] + [tokenizer.pad_token_id] * padding)
            batch["attention_mask"].append(f["attention_mask"] + [0] * padding)
            batch["labels"].append(f["labels"] + [-100] * padding)
        return {key: torch.tensor(value) for key, value in batch.items()}

    by_steps = config["eval_steps"] is not None
    saving_by_steps = config["save_steps"] is not None
    training_args = TrainingArguments(
        output_dir=str(output),
        learning_rate=config["learning_rate"],
        num_train_epochs=config["epochs"],
        max_steps=config["max_steps"],
        per_device_train_batch_size=config["per_device_train_batch_size"],
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=config["gradient_accumulation_steps"],
        warmup_steps=config["warmup_steps"],
        lr_scheduler_type=config["lr_scheduler_type"],
        weight_decay=config["weight_decay"],
        bf16=precision == "bf16",
        fp16=precision == "fp16",
        eval_strategy="steps" if by_steps else "epoch",
        eval_steps=config["eval_steps"],
        save_strategy="steps" if saving_by_steps else "epoch",
        save_steps=config["save_steps"],
        save_total_limit=config["save_total_limit"],
        logging_steps=config["logging_steps"],
        logging_first_step=True,
        report_to="none",
        seed=config["seed"],
        data_seed=config["seed"],
        dataloader_num_workers=0,
        remove_unused_columns=False,
        gradient_checkpointing=False,  # enabled on the base model above when configured
        load_best_model_at_end=config["load_best_model_at_end"],
        metric_for_best_model="eval_loss" if config["load_best_model_at_end"] else None,
        greater_is_better=False if config["load_best_model_at_end"] else None,
    )
    meter = StepMeter()
    callbacks = [meter]
    if args.stop_after_steps is not None:
        callbacks.append(StopAfter(args.stop_after_steps))
    time_cap = None
    if config["max_runtime_minutes"] is not None:
        time_cap = TimeCap(config["max_runtime_minutes"])
        callbacks.append(time_cap)
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=as_dataset(encoded["train"]),
        eval_dataset=as_dataset(encoded["validation"]),
        data_collator=collate,
        callbacks=callbacks,
    )

    run_id = config["run_id"] or output.name
    manifest = {
        "status": "running",
        "run_id": run_id,
        "code_sha": git_state(),
        "train_script_sha256": sha256_file(Path(__file__)),
        "model_id": config["model_id"],
        "model_revision": config["model_revision"],
        "dataset_sha256": data_report["dataset_sha256"],
        "split_manifest": data_report["records"],
        "hardware": {
            "gpu": torch.cuda.get_device_name(0),
            "nvidia_smi": nvidia_smi("name,memory.total,driver_version"),
            "platform": platform.platform(),
            "python": sys.version.split()[0],
        },
        "dependency_lock": {
            "file": "training/requirements-cuda.txt",
            "sha256": sha256_file(ROOT / "training" / "requirements-cuda.txt"),
            "packages": package_versions(),
            "cuda": torch.version.cuda,
        },
        "config": {**config, "precision_resolved": precision},
        "seed": config["seed"],
        "duration_seconds": None,
        "peak_memory_mb": None,
        "validation_metrics": None,
        "test_metrics": None,
        "failures": [],
        "artifact_url": None,
        "artifact_sha256": None,
        "evaluator": None,
        "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "command": " ".join([Path(sys.executable).name, *sys.argv]),
        "resumed_from_checkpoint": (
            None if resume is None else f"{resume.parent.name}/{resume.name}"
        ),
        "stop_after_steps": args.stop_after_steps,
        "data": data_report,
        "trainable_parameters": trainable,
        "total_parameters": total,
        "trainable_parameter_dtypes": trainable_dtypes,
    }
    output.mkdir(parents=True, exist_ok=True)

    def write_manifest() -> None:
        text = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
        (output / "run-manifest.json").write_text(text, encoding="utf-8")
        if args.record is not None:
            args.record.parent.mkdir(parents=True, exist_ok=True)
            args.record.write_text(text, encoding="utf-8")

    write_manifest()
    started = time.perf_counter()
    try:
        with GpuSampler() as sampler:
            result = trainer.train(resume_from_checkpoint=str(resume) if resume else None)
            torch.cuda.reset_peak_memory_stats()
            evaluation = trainer.evaluate()
            eval_peak = torch.cuda.max_memory_allocated() / 2**20
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["duration_seconds"] = round(time.perf_counter() - started, 1)
        manifest["failures"].append({"error": f"{type(exc).__name__}: {exc}"[:1000]})
        manifest["traceback_tail"] = traceback.format_exc().splitlines()[-8:]
        write_manifest()
        raise
    duration = time.perf_counter() - started
    adapter_dir = output / "adapter"
    trainer.save_model(str(adapter_dir))
    adapter_file = adapter_dir / "adapter_model.safetensors"
    checkpoints = sorted(p for p in output.glob("checkpoint-*") if p.is_dir())
    manifest.update(
        status=(
            "completed"
            if args.stop_after_steps is None
            else "stopped_after_steps (simulated interruption)"
        ),
        finished_at=datetime.now(UTC).isoformat(timespec="seconds"),
        duration_seconds=round(duration, 1),
        train_runtime_seconds=round(result.metrics.get("train_runtime", 0.0), 1),
        global_step=trainer.state.global_step,
        epochs_completed=trainer.state.epoch,
        time_cap_hit_at_step=None if time_cap is None else time_cap.hit_at_step,
        best_model_checkpoint=(
            Path(trainer.state.best_model_checkpoint).name
            if trainer.state.best_model_checkpoint
            else None
        ),
        best_eval_loss=trainer.state.best_metric,
        saved_adapter="best checkpoint by eval_loss"
        if config["load_best_model_at_end"]
        else "final step",
        peak_memory_mb={
            "torch_peak_allocated_per_step_max": max(
                (s["peak_allocated_mib"] for s in meter.steps), default=None
            ),
            "torch_peak_reserved_per_step_max": max(
                (s["peak_reserved_mib"] for s in meter.steps), default=None
            ),
            "torch_peak_allocated_evaluation": round(eval_peak, 1),
            "gpu_used_all_processes_before_load": gpu_before_load,
            "gpu_used_all_processes_peak_sampled": sampler.peak,
        },
        validation_metrics={k: v for k, v in evaluation.items() if isinstance(v, (int, float))},
        artifact_url=None,
        artifact_path=adapter_dir.relative_to(ROOT).as_posix()
        if adapter_dir.is_relative_to(ROOT)
        else None,
        artifact_sha256=sha256_file(adapter_file),
        adapter_files={
            p.name: sha256_file(p) for p in sorted(adapter_dir.iterdir()) if p.is_file()
        },
        adapter_bytes=adapter_file.stat().st_size,
        checkpoints={
            p.name: sha256_file(p / "adapter_model.safetensors")
            for p in checkpoints
            if (p / "adapter_model.safetensors").is_file()
        },
        step_metrics=meter.steps,
        log_history=trainer.state.log_history,
    )
    write_manifest()
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "duration_seconds": manifest["duration_seconds"],
                "global_step": manifest["global_step"],
                "validation": manifest["validation_metrics"],
                "adapter_sha256": manifest["artifact_sha256"],
                "peak_memory_mb": manifest["peak_memory_mb"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
