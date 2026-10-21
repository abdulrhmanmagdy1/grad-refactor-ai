"""Check the configured adapter through the real LocalProvider on this machine.

Run in the CORE environment from the repository root (the provider starts the worker
with the training environment):

    python -m uv run python training/laptop_adapter_check.py \
        --out experiments/models/2026-10-21-laptop-adapter-check.json

It loads configs/model.local.json, records the provider identity (adapter weights and
config checksums), and runs the eight benchmark pilot functions (training/pilot,
never dataset records) with the adapter on and off, greedy, scoring each output with
the refactor-v2 parser, ast and the task rubric. The pilot functions have no reference
tests, so behavior is not checked here; this is pilot evidence, not an evaluation.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "training"))

from pilot.functions import pilot_functions  # noqa: E402

from refactor_ai.contracts import (  # noqa: E402
    ChatMessage,
    GenerationConfig,
    GenerationRequest,
    Role,
)
from refactor_ai.providers.local import LocalProvider  # noqa: E402
from refactor_ai.task_format import (  # noqa: E402
    PROMPT_VERSION,
    build_refactor_messages,
    parse_refactor_output,
)
from refactor_ai.tasks import guard_clauses  # noqa: E402
from refactor_ai.verification import checks  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "model.local.json")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    provider = LocalProvider.from_config(args.config)
    if provider.settings.adapter_dir is None:
        raise SystemExit("the config has no adapter")
    config = GenerationConfig(max_new_tokens=768, temperature=0.0, timeout_s=120)
    items = []
    try:
        info = provider.warm_up()
        if not info.ready:
            raise SystemExit(f"the model did not load: {info.detail}")
        for case in pilot_functions("benchmark"):
            messages = [ChatMessage(**m) for m in build_refactor_messages(case["code"])]
            for use_adapter in (True, False):
                result = provider.generate(
                    GenerationRequest(
                        role=Role.REFACTOR,
                        messages=messages,
                        config=config,
                        use_adapter=use_adapter,
                    )
                )
                entry = {
                    "case_id": case["id"],
                    "use_adapter": use_adapter,
                    "error": None if result.error is None else result.error.model_dump(),
                    "model": None if result.model is None else result.model.model_dump(),
                    "elapsed_s": round(result.elapsed_s, 2),
                    "completion_tokens": result.completion_tokens,
                    "finish_reason": result.finish_reason,
                    "raw_output": result.text,
                }
                parsed = parse_refactor_output(result.text)
                entry["parse_error"] = parsed.error
                if parsed.code is not None:
                    syntax = checks.check_syntax(parsed.code)
                    rubric = checks.check_rubric(case["code"], parsed.code, syntax)
                    entry.update(
                        syntax=syntax.status,
                        rubric=rubric.status,
                        rubric_reasons=rubric.reasons,
                        same_as_reference=guard_clauses.same_code(
                            parsed.code, guard_clauses.to_guard_clauses(case["code"])
                        ),
                    )
                items.append(entry)
                print(
                    f"{case['id']} adapter={use_adapter}: parse={parsed.error or 'ok'} "
                    f"rubric={entry.get('rubric')}",
                    flush=True,
                )
    finally:
        provider.close()

    def summary(active: bool) -> dict:
        chosen = [i for i in items if i["use_adapter"] is active]
        return {
            "outputs": len(chosen),
            "provider_errors": sum(i["error"] is not None for i in chosen),
            "parsed": sum(i["parse_error"] is None for i in chosen),
            "syntax_pass": sum(i.get("syntax") == "pass" for i in chosen),
            "rubric_pass": sum(i.get("rubric") == "pass" for i in chosen),
            "same_as_reference": sum(bool(i.get("same_as_reference")) for i in chosen),
            "median_elapsed_s": statistics.median(i["elapsed_s"] for i in chosen),
        }

    record = {
        "record": "Trained adapter through the LocalProvider on the demonstration laptop "
        "(pilot functions; not an evaluation)",
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "command": " ".join([Path(sys.executable).name, *sys.argv]),
        "prompt_version": PROMPT_VERSION,
        "provider_info": info.model_dump(),
        "decoding": config.model_dump(),
        "summary": {"adapter": summary(True), "base": summary(False)},
        "items": items,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(record["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
