"""QLoRA fine-tuning for the refactoring adapter (ADR08, NFR04, NFR05).

The training text is rendered by :mod:`models.prompting`, the same renderer the
inference provider uses. This is deliberate: before this change, training used
``row["prompt"] + "\n"`` (a raw code block) while inference used a chat template
with system instructions and findings, so the adapter was trained on a
different input distribution than it was evaluated on.

Defaults target ``Qwen/Qwen2.5-Coder-3B-Instruct`` with 4-bit NF4 QLoRA, rank
16 / alpha 32 over all linear layers, ``max_length=2048`` and three epochs.
All values are configuration-driven; the example file is
``configs/training.example.json``. A 1.5B fallback and a 7B Colab option use
the same script and only change ``model_id`` / batch settings.

Commands::

    python training/train_lora.py --config configs/training.local.json --dry-run
    python training/train_lora.py --config configs/training.local.json
    python training/train_lora.py --config configs/training.local.json \
        --resume-from-checkpoint runs/lora-first/checkpoint-42

``--dry-run`` tokenizes every record with the real tokenizer and reports the
length distribution without loading the model or requiring CUDA. The run
manifest records the dataset hash, resolved model commit, package versions,
hardware, seed, adapter checksum and a syntax-only generation smoke test. It
never executes generated code (NFR01); the smoke test only parses it.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from validate_dataset import load_and_validate  # noqa: E402

from core.ast_analyzer import analyze  # noqa: E402
from models.prompting import (  # noqa: E402
    assistant_end_token,
    build_messages,
    extract_refactored_code,
    render_prompt,
)

DEFAULTS: dict[str, Any] = {
    "dataset": "data/curated.jsonl",
    "output_dir": "runs/lora-first",
    "seed": 42,
    "max_length": 2048,
    "load_in_4bit": True,
    "bnb_4bit_quant_type": "nf4",
    "bnb_4bit_use_double_quant": True,
    "bnb_4bit_compute_dtype": "bfloat16",
    "lora_rank": 16,
    "lora_alpha": 32,
    "lora_dropout": 0.05,
    "target_modules": "all-linear",
    "learning_rate": 0.0001,
    "epochs": 3,
    "per_device_train_batch_size": 1,
    "per_device_eval_batch_size": 1,
    "gradient_accumulation_steps": 16,
    "gradient_checkpointing": True,
    "warmup_ratio": 0.03,
    "lr_scheduler_type": "cosine",
    "optim": "paged_adamw_8bit",
    "logging_steps": 5,
    "save_total_limit": 2,
    "report_to": "none",
    "max_new_tokens": 1024,
    "smoke_max_new_tokens": 512,
}


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _load_config(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Cannot read training config {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"Training config {path} must be a JSON object")

    config = {**DEFAULTS, **payload}
    for field in ("model_id", "model_revision"):
        value = config.get(field)
        if not isinstance(value, str) or not value.strip() or "CHOOSE" in value:
            raise SystemExit(f"Choose {field} in {path} after the hardware and license review")

    if int(config["max_length"]) < 256:
        raise SystemExit("max_length must be at least 256")
    if int(config["lora_rank"]) <= 0:
        raise SystemExit("lora_rank must be positive")
    if int(config["epochs"]) <= 0:
        raise SystemExit("epochs must be positive")
    if int(config["gradient_accumulation_steps"]) <= 0:
        raise SystemExit("gradient_accumulation_steps must be positive")
    if int(config["max_new_tokens"]) <= 0:
        raise SystemExit("max_new_tokens must be positive")

    if str(config["model_revision"]).strip().lower() in {"main", "master"}:
        print(
            "Warning: model_revision is a mutable branch; the run manifest records "
            "the resolved commit hash for reproducibility.",
            file=sys.stderr,
        )
    return config


def _load_rows(config: dict[str, Any]) -> tuple[list[dict[str, Any]], Path]:
    dataset_path = Path(str(config["dataset"]))
    if not dataset_path.is_absolute():
        dataset_path = ROOT / dataset_path
    return load_and_validate(dataset_path), dataset_path


# --------------------------------------------------------------------------- #
# Tokenization: one renderer for training and inference
# --------------------------------------------------------------------------- #
def _load_tokenizer(config: dict[str, Any]):
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        str(config["model_id"]),
        revision=str(config["model_revision"]),
        trust_remote_code=False,
    )
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
        tokenizer.pad_token_id = tokenizer.eos_token_id
    tokenizer.padding_side = "right"
    return tokenizer


def _tokenize_example(
    tokenizer: Any,
    row: dict[str, Any],
    eos_token_id: int,
) -> tuple[list[int], list[int]]:
    """Return ``(input_ids, labels)`` with the completion as the only target.

    The prompt is rendered by the shared :mod:`models.prompting` contract.
    When the tokenizer has a chat template, the full conversation is rendered
    and the prefix is checked to be an exact prefix; this captures the
    assistant header and the ``<|im_end|>`` turn terminator exactly. Otherwise
    the completion and the assistant end token are appended manually.
    """
    code = str(row["prompt"])
    findings = analyze(code).findings
    prefix = render_prompt(tokenizer, code, findings)
    prefix_ids = list(tokenizer(prefix, add_special_tokens=False)["input_ids"])
    completion = str(row["completion"]).strip()

    apply_template = getattr(tokenizer, "apply_chat_template", None)
    if callable(apply_template):
        try:
            messages = [
                *build_messages(code, findings),
                {"role": "assistant", "content": completion},
            ]
            full_text = str(apply_template(messages, tokenize=False, add_generation_prompt=False))
            full_ids = list(tokenizer(full_text, add_special_tokens=False)["input_ids"])
            if len(full_ids) > len(prefix_ids) and full_ids[: len(prefix_ids)] == prefix_ids:
                labels = [-100] * len(prefix_ids) + full_ids[len(prefix_ids) :]
                return full_ids, labels
        except (AttributeError, TypeError, ValueError):
            pass

    target_ids = list(tokenizer(completion, add_special_tokens=False)["input_ids"])
    target_ids.append(eos_token_id)
    input_ids = prefix_ids + target_ids
    labels = [-100] * len(prefix_ids) + target_ids
    return input_ids, labels


def _percentile(values: list[int], fraction: float) -> int:
    ordered = sorted(values)
    if not ordered:
        return 0
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def _audit_tokens(tokenizer: Any, rows: list[dict[str, Any]], max_length: int) -> int:
    eos_token_id = assistant_end_token(tokenizer)[1]
    by_split: dict[str, list[int]] = {"train": [], "validation": [], "test": []}
    prefix_lengths: list[int] = []
    completion_lengths: list[int] = []
    over_limit: list[dict[str, Any]] = []

    for row in rows:
        input_ids, labels = _tokenize_example(tokenizer, row, eos_token_id)
        length = len(input_ids)
        by_split.setdefault(str(row["split"]), []).append(length)
        prefix_lengths.append(labels.count(-100))
        completion_lengths.append(length - labels.count(-100))
        if length > max_length:
            over_limit.append({"id": row["id"], "tokens": length, "split": row["split"]})

    all_lengths = [length for lengths in by_split.values() for length in lengths]
    report: dict[str, Any] = {
        "method": "exact tokenizer (shared chat template)",
        "max_length": max_length,
        "records": len(rows),
        "overall": {
            "max": max(all_lengths) if all_lengths else 0,
            "mean": round(statistics.mean(all_lengths), 1) if all_lengths else 0,
            "p50": _percentile(all_lengths, 0.50),
            "p90": _percentile(all_lengths, 0.90),
            "p95": _percentile(all_lengths, 0.95),
            "p99": _percentile(all_lengths, 0.99),
            "prompt_max": max(prefix_lengths) if prefix_lengths else 0,
            "completion_max": max(completion_lengths) if completion_lengths else 0,
        },
        "splits": {
            split: {
                "records": len(lengths),
                "max": max(lengths) if lengths else 0,
                "p95": _percentile(lengths, 0.95),
            }
            for split, lengths in by_split.items()
        },
        "over_limit": over_limit,
        "status": "pass" if not over_limit else "fail",
    }
    print(json.dumps(report, indent=2))
    return 0 if not over_limit else 1


# --------------------------------------------------------------------------- #
# Model and adapter
# --------------------------------------------------------------------------- #
def _load_model(config: dict[str, Any], tokenizer: Any):
    import torch
    from peft import LoraConfig, TaskType, get_peft_model, prepare_model_for_kbit_training
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig

    model_kwargs: dict[str, Any] = {"trust_remote_code": False}
    if bool(config["load_in_4bit"]):
        compute_dtype_name = str(config["bnb_4bit_compute_dtype"])
        if compute_dtype_name == "bfloat16" and not torch.cuda.is_bf16_supported():
            compute_dtype_name = "float16"
        model_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type=str(config["bnb_4bit_quant_type"]),
            bnb_4bit_use_double_quant=bool(config["bnb_4bit_use_double_quant"]),
            bnb_4bit_compute_dtype=getattr(torch, compute_dtype_name),
        )
        model_kwargs["device_map"] = "auto"
    else:
        model_kwargs["torch_dtype"] = (
            torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        )

    model = AutoModelForCausalLM.from_pretrained(
        str(config["model_id"]),
        revision=str(config["model_revision"]),
        **model_kwargs,
    )
    model.config.use_cache = False

    if bool(config["gradient_checkpointing"]):
        model.gradient_checkpointing_enable()
    if bool(config["load_in_4bit"]):
        model = prepare_model_for_kbit_training(
            model,
            use_gradient_checkpointing=bool(config["gradient_checkpointing"]),
        )

    model = get_peft_model(
        model,
        LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=int(config["lora_rank"]),
            lora_alpha=int(config["lora_alpha"]),
            lora_dropout=float(config["lora_dropout"]),
            target_modules=config["target_modules"] or "all-linear",
            bias="none",
        ),
    )
    return model


def _training_arguments(config: dict[str, Any], output: Path, torch: Any):
    from transformers import TrainingArguments

    use_bf16 = bool(torch.cuda.is_bf16_supported())
    optim = str(config["optim"])
    if optim.startswith("paged_") and not _module_available("bitsandbytes"):
        print(
            "Warning: bitsandbytes is missing; falling back from paged optimizers to adamw_torch.",
            file=sys.stderr,
        )
        optim = "adamw_torch"
    return TrainingArguments(
        output_dir=str(output),
        learning_rate=float(config["learning_rate"]),
        num_train_epochs=float(config["epochs"]),
        per_device_train_batch_size=int(config["per_device_train_batch_size"]),
        per_device_eval_batch_size=int(config["per_device_eval_batch_size"]),
        gradient_accumulation_steps=int(config["gradient_accumulation_steps"]),
        bf16=use_bf16,
        fp16=not use_bf16,
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=int(config["save_total_limit"]),
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        logging_steps=int(config["logging_steps"]),
        lr_scheduler_type=str(config["lr_scheduler_type"]),
        warmup_ratio=float(config["warmup_ratio"]),
        optim=optim,
        report_to=str(config["report_to"]),
        seed=int(config["seed"]),
        data_seed=int(config["seed"]),
        remove_unused_columns=False,
    )


def _make_collator(torch: Any, pad_token_id: int):
    def collate(features: list[dict[str, Any]]) -> dict[str, Any]:
        longest = max(len(feature["input_ids"]) for feature in features)
        batch: dict[str, list[list[int]]] = {
            "input_ids": [],
            "attention_mask": [],
            "labels": [],
        }
        for feature in features:
            padding = longest - len(feature["input_ids"])
            batch["input_ids"].append(feature["input_ids"] + [pad_token_id] * padding)
            batch["attention_mask"].append(feature["attention_mask"] + [0] * padding)
            batch["labels"].append(feature["labels"] + [-100] * padding)
        return {key: torch.tensor(value) for key, value in batch.items()}

    return collate


# --------------------------------------------------------------------------- #
# Evidence
# --------------------------------------------------------------------------- #
def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _code_sha() -> tuple[str | None, str | None]:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=False,
        cwd=ROOT,
    )
    if result.returncode == 0:
        return result.stdout.strip(), None
    return None, (result.stderr or "git not available").strip()


def _package_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in ("torch", "transformers", "peft", "datasets", "accelerate", "bitsandbytes"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "missing"
    return versions


def _smoke_generate(
    config: dict[str, Any],
    model: Any,
    tokenizer: Any,
    rows: list[dict[str, Any]],
    eos_token_id: int,
    torch: Any,
) -> dict[str, Any]:
    """Generate once and check syntax (AST only; never execute, NFR01)."""
    sample = next(
        (row for row in rows if row["split"] == "validation"),
        rows[0],
    )
    code = str(sample["prompt"])
    prompt = render_prompt(tokenizer, code, analyze(code).findings)
    tokenizer.padding_side = "left"
    inputs = tokenizer(prompt, return_tensors="pt")
    device = next(model.parameters()).device
    inputs = {name: value.to(device) for name, value in inputs.items()}
    model.eval()
    with torch.no_grad():
        output = model.generate(
            **inputs,
            max_new_tokens=min(int(config["smoke_max_new_tokens"]), int(config["max_new_tokens"])),
            do_sample=False,
            eos_token_id=eos_token_id,
            pad_token_id=int(tokenizer.pad_token_id),
        )
    generated = tokenizer.decode(
        output[0][inputs["input_ids"].shape[1] :],
        skip_special_tokens=True,
    )
    candidate = extract_refactored_code(generated)
    result = analyze(candidate)
    return {
        "record_id": sample["id"],
        "syntax_valid": bool(result.syntax_valid),
        "findings_after": [finding.rule for finding in result.findings],
        "raw_text": generated[:2000],
        "generated_code": candidate[:4000],
        "executed": False,
    }


def _trainable_parameter_counts(model: Any) -> dict[str, Any]:
    trainable = sum(
        parameter.numel() for parameter in model.parameters() if parameter.requires_grad
    )
    total = sum(parameter.numel() for parameter in model.parameters())
    return {
        "trainable": trainable,
        "total": total,
        "ratio": round(trainable / total, 6) if total else 0.0,
    }


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(description="QLoRA fine-tuning for the refactoring adapter")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--resume-from-checkpoint", default=None)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Tokenize every record with the real tokenizer and report lengths; "
            "does not load the model or require CUDA."
        ),
    )
    args = parser.parse_args()

    config = _load_config(args.config)
    rows, dataset_path = _load_rows(config)

    if args.dry_run:
        if not _module_available("transformers"):
            raise SystemExit(
                "--dry-run needs transformers and the tokenizer; install "
                "training/requirements.txt in the training environment first."
            )
        tokenizer = _load_tokenizer(config)
        return _audit_tokens(tokenizer, rows, int(config["max_length"]))

    import torch

    if not torch.cuda.is_available():
        raise SystemExit(
            "CUDA GPU required for QLoRA fine-tuning; run --dry-run on a CPU-only "
            "machine to audit tokens, then train on the CUDA host."
        )
    from datasets import Dataset
    from transformers import Trainer

    torch.manual_seed(int(config["seed"]))
    torch.cuda.manual_seed_all(int(config["seed"]))
    torch.cuda.reset_peak_memory_stats()

    tokenizer = _load_tokenizer(config)
    eos_token_id = assistant_end_token(tokenizer)[1]
    examples: dict[str, list[dict[str, Any]]] = {"train": [], "validation": [], "test": []}
    over_limit: list[dict[str, Any]] = []
    for row in rows:
        input_ids, labels = _tokenize_example(tokenizer, row, eos_token_id)
        if len(input_ids) > int(config["max_length"]):
            over_limit.append({"id": row["id"], "tokens": len(input_ids)})
            continue
        examples.setdefault(str(row["split"]), []).append(
            {
                "input_ids": input_ids,
                "attention_mask": [1] * len(input_ids),
                "labels": labels,
            }
        )
    if over_limit:
        raise SystemExit(
            "Records exceed max_length; shorten them or raise max_length before "
            f"training: {over_limit[:10]}"
        )
    if not examples["train"] or not examples["validation"]:
        raise SystemExit("Training requires non-empty train and validation splits")

    model = _load_model(config, tokenizer)
    output = Path(str(config["output_dir"]))
    if not output.is_absolute():
        output = ROOT / output
    output.mkdir(parents=True, exist_ok=True)

    train_dataset = Dataset.from_list(examples["train"])
    eval_dataset = Dataset.from_list(examples["validation"])
    trainer = Trainer(
        model=model,
        args=_training_arguments(config, output, torch),
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        data_collator=_make_collator(torch, int(tokenizer.pad_token_id)),
        tokenizer=tokenizer,
    )

    code_sha, code_sha_error = _code_sha()
    dataset_sha = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    started = time.perf_counter()
    trainer.train(resume_from_checkpoint=args.resume_from_checkpoint)
    duration_seconds = round(time.perf_counter() - started, 2)

    adapter_dir = output / "adapter"
    trainer.save_model(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))
    validation_metrics = trainer.evaluate()
    (output / "validation-metrics.json").write_text(
        json.dumps(validation_metrics, indent=2), encoding="utf-8"
    )
    (output / "trainer-log.json").write_text(
        json.dumps(trainer.state.log_history, indent=2), encoding="utf-8"
    )

    smoke = _smoke_generate(config, model, tokenizer, rows, eos_token_id, torch)
    manifest = {
        "config": config,
        "code_sha": code_sha,
        "code_sha_error": code_sha_error,
        "dataset": {
            "path": str(dataset_path),
            "sha256": dataset_sha,
            "records": len(rows),
            "splits": {
                split: sum(row["split"] == split for row in rows)
                for split in ("train", "validation", "test")
            },
        },
        "model": {
            "model_id": str(config["model_id"]),
            "requested_revision": str(config["model_revision"]),
            "resolved_commit": getattr(model.config, "_commit_hash", None),
        },
        "hardware": {
            "device": torch.cuda.get_device_name(0),
            "device_count": torch.cuda.device_count(),
            "total_memory_bytes": torch.cuda.get_device_properties(0).total_memory,
        },
        "platform": platform.platform(),
        "python": sys.version,
        "cuda": torch.version.cuda,
        "packages": _package_versions(),
        "trainable_parameters": _trainable_parameter_counts(model),
        "duration_seconds": duration_seconds,
        "peak_gpu_memory_bytes": torch.cuda.max_memory_allocated(),
        "best_checkpoint": trainer.state.best_model_checkpoint,
        "resume": args.resume_from_checkpoint,
        "validation_metrics": validation_metrics,
        "smoke_generation": smoke,
        "adapter": {
            "path": str(adapter_dir),
            "model_sha256": _sha256_file(adapter_dir / "adapter_model.safetensors"),
            "config_sha256": _sha256_file(adapter_dir / "adapter_config.json"),
        },
        "executed_generated_code": False,
    }
    (output / "run-manifest.json").write_text(
        json.dumps(manifest, indent=2, default=str), encoding="utf-8"
    )

    print(f"Adapter: {adapter_dir}")
    print(f"Manifest: {output / 'run-manifest.json'}")
    print(json.dumps({"validation": validation_metrics, "smoke": smoke}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
