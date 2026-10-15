"""Initial unquantized CUDA LoRA path; requires a GPU smoke test before experiments."""

import argparse
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from validate_dataset import load_and_validate  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--resume-from-checkpoint")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    for field in ("model_id", "model_revision", "dataset", "output_dir"):
        if not config.get(field) or "CHOOSE" in config[field]:
            raise SystemExit(f"Choose {field} after the hardware and license review")
    rows = load_and_validate(Path(config["dataset"]))

    import torch
    from datasets import Dataset
    from peft import LoraConfig, TaskType, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments

    if not torch.cuda.is_available():
        raise SystemExit(
            "CUDA GPU required by this initial script; review hardware before training"
        )
    torch.manual_seed(config["seed"])
    tokenizer = AutoTokenizer.from_pretrained(
        config["model_id"], revision=config["model_revision"], trust_remote_code=False
    )
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    if tokenizer.eos_token_id is None:
        raise SystemExit("Tokenizer must define an EOS token")
    model = AutoModelForCausalLM.from_pretrained(
        config["model_id"],
        revision=config["model_revision"],
        trust_remote_code=False,
        torch_dtype=torch.float16,
    )
    model.config.use_cache = False
    model = get_peft_model(
        model,
        LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=config["lora_rank"],
            lora_alpha=config["lora_alpha"],
            lora_dropout=0.05,
            target_modules=config["target_modules"],
        ),
    )

    def encode(row):
        prefix = tokenizer(row["prompt"] + "\n", add_special_tokens=True)["input_ids"]
        target = tokenizer(row["completion"], add_special_tokens=False)["input_ids"]
        target += [tokenizer.eos_token_id]
        if len(prefix) + len(target) > config["max_length"]:
            raise ValueError(f"Record {row['id']} exceeds context; curate or chunk explicitly")
        ids = prefix + target
        return {
            "input_ids": ids,
            "attention_mask": [1] * len(ids),
            "labels": [-100] * len(prefix) + target,
        }

    def split(name):
        return Dataset.from_list([encode(row) for row in rows if row["split"] == name])

    def collate(features):
        size = max(len(f["input_ids"]) for f in features)
        batch = {key: [] for key in ("input_ids", "attention_mask", "labels")}
        for f in features:
            padding = size - len(f["input_ids"])
            batch["input_ids"].append(f["input_ids"] + [tokenizer.pad_token_id] * padding)
            batch["attention_mask"].append(f["attention_mask"] + [0] * padding)
            batch["labels"].append(f["labels"] + [-100] * padding)
        return {key: torch.tensor(value) for key, value in batch.items()}

    output = Path(config["output_dir"])
    output.mkdir(parents=True, exist_ok=True)
    git = subprocess.run(["git", "rev-parse", "HEAD"], text=True, capture_output=True, check=False)
    manifest = {
        "config": config,
        "code_sha": git.stdout.strip(),
        "dataset_sha256": hashlib.sha256(Path(config["dataset"]).read_bytes()).hexdigest(),
        "hardware": torch.cuda.get_device_name(0),
        "platform": platform.platform(),
        "python": sys.version,
        "cuda": torch.version.cuda,
        "packages": {
            name: importlib.metadata.version(name)
            for name in ("torch", "transformers", "peft", "datasets", "accelerate")
        },
        "resume": args.resume_from_checkpoint,
    }
    (output / "run-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    trainer = Trainer(
        model=model,
        args=TrainingArguments(
            output_dir=str(output),
            learning_rate=config["learning_rate"],
            num_train_epochs=config["epochs"],
            per_device_train_batch_size=1,
            per_device_eval_batch_size=1,
            gradient_accumulation_steps=config["gradient_accumulation_steps"],
            fp16=True,
            eval_strategy="epoch",
            save_strategy="epoch",
            save_total_limit=2,
            logging_steps=10,
            report_to="none",
            seed=config["seed"],
        ),
        train_dataset=split("train"),
        eval_dataset=split("validation"),
        data_collator=collate,
    )
    trainer.train(resume_from_checkpoint=args.resume_from_checkpoint)
    trainer.save_model(str(output / "adapter"))
    tokenizer.save_pretrained(str(output / "adapter"))
    metrics = trainer.evaluate()
    (output / "validation-metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
