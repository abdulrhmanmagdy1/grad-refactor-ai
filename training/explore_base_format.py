"""Exploratory T04 check: does the base model ever produce the refactor-v1 format?

Greedy decoding (the default of every role) produced no code block on the pilot
functions. This script samples the same prompts with the temperature and top_p the
model card recommends (0.7 and 0.8; the provider contract has no top_k or repetition
penalty) for several seeds and counts the outputs that parse and pass the rubric. It is
an exploration of the base model, not the evaluation protocol, and uses pilot material.

    .venv-train/Scripts/python.exe -X utf8 training/explore_base_format.py \
        --out experiments/models/2026-10-20-base-format-sampling-exploration.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from common import ROOT, load_worker_module, require_free_disk
from pilot.functions import pilot_functions

from refactor_ai import task_format
from refactor_ai.tasks import guard_clauses

MODEL_ID = "Qwen/Qwen2.5-Coder-0.5B-Instruct"
MODEL_REVISION = "ea3f2471cf1b1f0db85067f1ef93848e38e88c25"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--top-p", type=float, default=0.8)
    parser.add_argument("--seeds", default="1,2,3")
    parser.add_argument("--max-new-tokens", type=int, default=768)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    require_free_disk(min_mb=300, needed_mb=1)
    worker = load_worker_module()
    backend = worker.TorchBackend(
        worker.LoadSettings(
            model_dir=ROOT / "models" / "Qwen2.5-Coder-0.5B-Instruct",
            model_id=MODEL_ID,
            model_revision=MODEL_REVISION,
            adapter_dir=None,
            adapter_id=None,
            adapter_sha256=None,
            device="cuda",
            dtype="bfloat16",
        )
    )
    seeds = [int(s) for s in args.seeds.split(",")]
    results = []
    for seed in seeds:
        for case in pilot_functions("benchmark"):
            output = backend.generate(
                worker.GenerateRequest(
                    id=f"{case['id']}-seed{seed}",
                    messages=task_format.build_refactor_messages(case["code"]),
                    max_new_tokens=args.max_new_tokens,
                    temperature=args.temperature,
                    top_p=args.top_p,
                    seed=seed,
                    max_input_tokens=32768,
                    use_adapter=False,
                )
            )
            parsed = task_format.parse_refactor_output(output["text"])
            rubric = guard_clauses.rubric(case["code"], parsed.code) if parsed.code else None
            results.append(
                {
                    "case_id": case["id"],
                    "seed": seed,
                    "completion_tokens": output["completion_tokens"],
                    "finish_reason": output["finish_reason"],
                    "has_code_fence": "```" in output["text"],
                    "parse_error": parsed.error,
                    "parse_repaired": parsed.repaired,
                    "rubric_passed": None if rubric is None else rubric.passed,
                    "raw_output": output["text"],
                }
            )
            print(f"seed {seed} {case['id']}: parse={parsed.error or 'ok'}", flush=True)
    record = {
        "record": "Exploratory base-model format check with sampling (pilot functions; "
        "not the evaluation protocol)",
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "command": " ".join([Path(sys.executable).name, *sys.argv]),
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "decoding": {"temperature": args.temperature, "top_p": args.top_p, "top_k": None},
        "seeds": seeds,
        "summary": {
            "outputs": len(results),
            "with_code_fence": sum(r["has_code_fence"] for r in results),
            "parsed": sum(r["parse_error"] is None for r in results),
            "rubric_passed": sum(bool(r["rubric_passed"]) for r in results),
        },
        "results": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(record["summary"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
