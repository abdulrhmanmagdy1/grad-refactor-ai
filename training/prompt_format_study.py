"""Validation-only prompt-format selection for the refactoring role (wave 2, step 1).

Run in the CORE environment from the repository root (it drives the real LocalProvider,
whose worker uses the training environment, and the isolated reference runner):

    python -m uv run python training/prompt_format_study.py --variants v1,v2,v3

Selection rule, fixed before any output is seen: the variant with the most validation
records whose output passes syntax AND the rubric AND the reference tests wins; ties are
broken by the parse rate, then by the shorter prompt. Only split "validation" is read:
test lines are discarded as soon as their split is known and nothing runs on them.

Records: 2 per validation source_group, the lowest ids. Model: the base model from
configs/model.local.json, no adapter, greedy decoding. Raw outputs are cached in
runs/prompt-study/ (ignored by Git) so an interrupted run resumes without regenerating.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "training"))

import prompt_formats as pf  # noqa: E402

from refactor_ai import task_format  # noqa: E402
from refactor_ai.contracts import (  # noqa: E402
    ChatMessage,
    GenerationConfig,
    GenerationRequest,
    ReferenceCase,
    ReferenceTest,
    Role,
)
from refactor_ai.providers.local import LocalProvider  # noqa: E402
from refactor_ai.verification import checks  # noqa: E402
from refactor_ai.verification.runner import create_runner  # noqa: E402

SELECTION_RULE = (
    "Highest number of validation records with syntax pass AND rubric pass AND reference "
    "tests pass; ties broken by parse rate, then by the shorter mean prompt (tokens)."
)


def validation_records(path: Path, per_group: int) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("split") != "validation":
            continue  # never keep train or test records
        rows.append(row)
    groups: dict[str, list[dict]] = {}
    for row in sorted(rows, key=lambda r: r["id"]):
        groups.setdefault(row["source_group"], []).append(row)
    chosen = [row for group in sorted(groups) for row in groups[group][:per_group]]
    assert all(r["split"] == "validation" for r in chosen)
    return chosen


def reference_case(row: dict) -> ReferenceCase:
    return ReferenceCase(
        case_id=row["id"],
        task_type=row["refactoring_type"],
        function_name=row["function_name"],
        original_code=row["original_code"],
        reference_code=row["target_code"],
        tests=[ReferenceTest.model_validate(t) for t in row["tests"]],
        source_group=row["source_group"],
        license=row["license"],
        provenance=row["provenance"],
    )


def score(row: dict, text: str, runner) -> dict:
    parsed = task_format.parse_refactor_output(text)
    entry = {
        "parse_error": parsed.error,
        "parse_repaired": parsed.repaired,
        "parse_notes": parsed.notes,
        "explanation": parsed.explanation,
    }
    if parsed.code is None:
        entry.update(syntax="not_run", rubric="not_run", tests="not_run", overall=False)
        return entry
    result = checks.run_checks(
        row["original_code"], parsed.code, case=reference_case(row), runner=runner
    )
    tests = result.tests
    entry.update(
        syntax=result.syntax.status,
        syntax_error=result.syntax.error,
        rubric=result.rubric.status,
        rubric_reasons=result.rubric.reasons,
        tests=tests.status,
        tests_passed=tests.passed,
        tests_total=tests.total,
        tests_reason=tests.reason,
        same_as_reference=parsed.code.strip() == row["target_code"].strip(),
        overall=result.syntax.status == "pass"
        and result.rubric.status == "pass"
        and tests.status == "pass",
    )
    return entry


def summarize(items: list[dict]) -> dict:
    n = len(items)
    elapsed = [i["elapsed_s"] for i in items if i.get("elapsed_s") is not None]
    completion = [i["completion_tokens"] for i in items if i.get("completion_tokens") is not None]
    prompt = [i["prompt_tokens"] for i in items if i.get("prompt_tokens") is not None]
    return {
        "records": n,
        "provider_errors": sum(i.get("provider_error") is not None for i in items),
        "parsed": sum(i["parse_error"] is None for i in items),
        "parse_repaired": sum(bool(i.get("parse_repaired")) for i in items),
        "syntax_pass": sum(i["syntax"] == "pass" for i in items),
        "rubric_pass": sum(i["rubric"] == "pass" for i in items),
        "tests_pass": sum(i["tests"] == "pass" for i in items),
        "overall_pass": sum(bool(i["overall"]) for i in items),
        "same_as_reference": sum(bool(i.get("same_as_reference")) for i in items),
        "finish_length": sum(i.get("finish_reason") == "length" for i in items),
        "prompt_tokens_mean": round(statistics.mean(prompt), 1) if prompt else None,
        "completion_tokens_mean": round(statistics.mean(completion), 1) if completion else None,
        "completion_tokens_max": max(completion, default=None),
        "elapsed_s_median": round(statistics.median(elapsed), 2) if elapsed else None,
        "elapsed_s_max": round(max(elapsed), 2) if elapsed else None,
        "elapsed_s_total": round(sum(elapsed), 1) if elapsed else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dataset", type=Path, default=ROOT / "datasets/guard_clauses/v1/records.jsonl"
    )
    parser.add_argument("--config", type=Path, default=ROOT / "configs/model.local.json")
    parser.add_argument("--variants", default="v1,v2,v3")
    parser.add_argument("--per-group", type=int, default=2)
    parser.add_argument("--max-new-tokens", type=int, default=1024)
    parser.add_argument("--timeout-s", type=float, default=300.0)
    parser.add_argument("--cache", type=Path, default=ROOT / "runs/prompt-study/raw.jsonl")
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "experiments/models/2026-10-20-prompt-format-selection.json",
    )
    args = parser.parse_args()
    variants = args.variants.split(",")
    records = validation_records(args.dataset, args.per_group)
    for row in records:  # the v1 builder must reproduce the stored prompt exactly
        if pf.build_user_prompt("v1", row["original_code"]) != row["prompt"]:
            raise SystemExit(f"{row['id']}: the stored prompt is not the refactor-v1 prompt")

    args.cache.parent.mkdir(parents=True, exist_ok=True)
    cached: dict[tuple[str, str], dict] = {}
    if args.cache.exists():
        for line in args.cache.read_text(encoding="utf-8").splitlines():
            item = json.loads(line)
            cached[(item["variant"], item["id"])] = item
    config = GenerationConfig(
        max_new_tokens=args.max_new_tokens,
        temperature=0.0,
        max_input_tokens=4096,
        timeout_s=args.timeout_s,
    )
    todo = [(v, r) for v in variants for r in records if (v, r["id"]) not in cached]
    provider = LocalProvider.from_config(args.config) if todo else None
    load_info = None
    try:
        if provider is not None:
            if provider.settings.adapter_dir is not None:
                raise SystemExit("the study uses the base model; the config has an adapter")
            load_info = provider.warm_up().model_dump()
            print(f"model ready: {load_info['detail']}", flush=True)
        for variant, row in todo:
            messages = pf.build_messages(variant, row["original_code"])
            result = provider.generate(
                GenerationRequest(
                    role=Role.REFACTOR,
                    messages=[ChatMessage(**m) for m in messages],
                    config=config,
                    use_adapter=False,
                )
            )
            item = {
                "variant": variant,
                "id": row["id"],
                "text": result.text,
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "finish_reason": result.finish_reason,
                "elapsed_s": round(result.elapsed_s, 3),
                "provider_error": None if result.error is None else result.error.model_dump(),
                "model": None if result.model is None else result.model.model_dump(),
            }
            cached[(variant, row["id"])] = item
            with args.cache.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(item, ensure_ascii=False) + "\n")
            print(
                f"{variant} {row['id']}: {item['completion_tokens']} tokens in "
                f"{item['elapsed_s']} s, finish={item['finish_reason']}",
                flush=True,
            )
    finally:
        if provider is not None:
            provider.close()

    runner = create_runner("auto")
    runner_info = runner.info()
    if not runner_info.enabled:
        raise SystemExit(f"the reference runner is disabled: {runner_info.reason}")
    control = []
    for row in records:  # the reference target must pass its own tests
        tests = checks.run_reference_tests(
            reference_case(row),
            row["target_code"],
            runner=runner,
            syntax=checks.check_syntax(row["target_code"]),
            rubric=checks.check_rubric(
                row["original_code"], row["target_code"], checks.check_syntax(row["target_code"])
            ),
        )
        control.append(
            {"id": row["id"], "tests": tests.status, "passed": tests.passed, "total": tests.total}
        )
    per_variant = {}
    for variant in variants:
        items = []
        for row in records:
            raw = cached[(variant, row["id"])]
            started = time.perf_counter()
            scored = score(row, raw["text"], runner)
            items.append({**raw, **scored, "scoring_s": round(time.perf_counter() - started, 2)})
            print(f"scored {variant} {row['id']}: overall={scored['overall']}", flush=True)
        per_variant[variant] = {"summary": summarize(items), "items": items}

    def key(variant: str):
        s = per_variant[variant]["summary"]
        return (-s["overall_pass"], -s["parsed"], s["prompt_tokens_mean"] or 0)

    ranking = sorted(variants, key=key)
    record = {
        "record": "Validation-only prompt-format selection for the refactoring role (base model)",
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "selection_rule": SELECTION_RULE,
        "command": " ".join([Path(sys.executable).name, *sys.argv]),
        "dataset": "datasets/guard_clauses/v1/records.jsonl (validation only; test not read)",
        "records": [
            {"id": r["id"], "source_group": r["source_group"], "tests": len(r["tests"])}
            for r in records
        ],
        "model": load_info,
        "decoding": {
            "temperature": 0.0,
            "max_new_tokens": args.max_new_tokens,
            "timeout_s": args.timeout_s,
        },
        "runner": runner_info.model_dump(),
        "control_reference_targets": {
            "passed": sum(c["tests"] == "pass" for c in control),
            "total": len(control),
            "items": control,
        },
        "variants": {
            v: {"user_prompt_example": pf.build_user_prompt(v, records[0]["original_code"])}
            for v in variants
        },
        "summary": {v: per_variant[v]["summary"] for v in variants},
        "ranking": ranking,
        "winner": ranking[0],
        "items": {v: per_variant[v]["items"] for v in variants},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "summary": record["summary"],
                "ranking": ranking,
                "control": record["control_reference_targets"]["passed"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
