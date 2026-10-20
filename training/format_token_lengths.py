"""Training-record token lengths of the curated dataset under prompt-format variants.

Run with the training environment from the repository root (tokenizer only, no GPU):

    .venv-train/Scripts/python.exe -X utf8 training/format_token_lengths.py --variants v1,v3

Only train and validation records are read; test lines are discarded as soon as their
split is known. v1 uses the stored prompt and completion. Other variants rewrite the
stored prompt with prompt_formats.convert_v1_prompt and render the stored explanation
and target_code in the variant's output format. Lengths are computed exactly as
train_lora.py encodes records (chat-template prefix plus completion plus end-of-turn),
including its check against the template's own rendering.
"""

from __future__ import annotations

import argparse
import json
import statistics
from datetime import UTC, datetime
from pathlib import Path

import prompt_formats as pf
from common import ROOT
from train_lora import encode, end_of_turn

from refactor_ai import task_format

MODEL_DIR = ROOT / "models" / "Qwen2.5-Coder-0.5B-Instruct"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dataset", type=Path, default=ROOT / "datasets/guard_clauses/v1/records.jsonl"
    )
    parser.add_argument("--variants", default="v1,v3")
    parser.add_argument("--max-length", type=int, default=1024)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    from transformers import AutoTokenizer, GenerationConfig

    rows = []
    for line in args.dataset.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if row["split"] in ("train", "validation"):
                rows.append(row)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR, local_files_only=True)
    eos = GenerationConfig.from_pretrained(MODEL_DIR, local_files_only=True).eos_token_id
    eot_id, _ = end_of_turn(tokenizer, list(eos) if isinstance(eos, list) else [eos])
    report = {
        "record": "Curated train/validation record lengths under refactoring prompt formats",
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "dataset": "datasets/guard_clauses/v1/records.jsonl (train and validation only)",
        "max_length": args.max_length,
        "variants": {},
    }
    for variant in args.variants.split(","):
        lengths: dict[str, list[tuple[int, str, int, int]]] = {"train": [], "validation": []}
        for row in rows:
            if variant == "v1":
                prompt, completion = row["prompt"], row["completion"]
            else:
                parsed = task_format.parse_refactor_output(row["completion"])
                if parsed.code != row["target_code"].rstrip() + "\n" or not parsed.explanation:
                    raise SystemExit(f"{row['id']}: the stored completion does not parse cleanly")
                prompt = pf.convert_v1_prompt(variant, row["prompt"])
                completion = pf.render_completion(variant, parsed.explanation, row["target_code"])
            item = encode(
                {"id": row["id"], "prompt": prompt, "completion": completion}, tokenizer, eot_id
            )
            lengths[row["split"]].append(
                (len(item["input_ids"]), row["id"], item["prefix_tokens"], item["target_tokens"])
            )
        summary = {}
        for split, values in lengths.items():
            totals = [v[0] for v in values]
            worst = sorted(values, reverse=True)[:10]
            summary[split] = {
                "records": len(values),
                "mean_tokens": round(statistics.mean(totals), 1),
                "median_tokens": statistics.median(totals),
                "max_tokens": max(totals),
                "over_max_length": sum(t > args.max_length for t in totals),
                "worst": [
                    {"id": i, "tokens": t, "prompt_tokens": p, "target_tokens": g}
                    for t, i, p, g in worst
                ],
            }
        report["variants"][variant] = summary
        print(
            variant,
            json.dumps(
                {s: {k: v for k, v in d.items() if k != "worst"} for s, d in summary.items()}
            ),
        )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
