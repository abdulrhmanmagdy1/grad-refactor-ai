"""Run evaluation arms A/B/C/D on a dataset split and keep every attempt.

Examples (from the repository root; prefix each with python -m uv run python):

    # plumbing check with the deterministic fake provider (not model evidence)
    scripts/evaluate.py --split validation --arms A,B --provider fake --limit 5

    # validation baseline with the local model (models workstream configuration)
    scripts/evaluate.py --split validation --provider local

    # final run, only after the protocol freeze record exists
    scripts/evaluate.py --split test --provider local --i-confirm-frozen-test
        --protocol-version eval-v1

Records go to runs/evaluation/<evaluation-id>/records.jsonl (Git-ignored) with a run
manifest next to them; tables and figures come from scripts/report_evaluation.py.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from refactor_ai.evaluation import cases, harness, protocol  # noqa: E402


def git_head() -> str | None:
    try:
        done = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout.strip() or None


def make_provider(kind: str, model_config: Path | None):
    if kind == "fake":
        from refactor_ai.providers.fake import FakeProvider

        return FakeProvider()
    from refactor_ai.providers.local import LocalProvider  # models workstream

    return LocalProvider.from_config(model_config or ROOT / "configs" / "model.local.json")


def make_runner(mode: str):
    from refactor_ai.verification import create_runner  # workflow and verification workstream

    return create_runner(mode)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dataset", type=Path, default=ROOT / cases.DEFAULT_DATASET)
    parser.add_argument("--split", choices=("train", "validation", "test"), default="validation")
    parser.add_argument("--arms", default=",".join(protocol.ARMS))
    parser.add_argument("--provider", choices=("fake", "local"), required=True)
    parser.add_argument("--model-config", type=Path)
    parser.add_argument("--runner", choices=("auto", "disabled"), default="auto")
    parser.add_argument("--limit", type=int, help="evaluate only the first N cases (dry runs)")
    parser.add_argument("--case-ids", nargs="*")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "runs" / "evaluation")
    parser.add_argument("--evaluation-id")
    parser.add_argument("--resume", action="store_true", help="append missing attempts only")
    parser.add_argument("--gpu-memory", action="store_true", help="sample nvidia-smi per case")
    parser.add_argument("--i-confirm-frozen-test", action="store_true")
    parser.add_argument("--protocol-version")
    args = parser.parse_args(argv)

    arms = protocol.parse_arms(args.arms)
    provider_mode = "fake" if args.provider == "fake" else "local_model"
    try:
        authorization = protocol.authorize_split(
            args.split,
            records_path=args.dataset,
            root=ROOT,
            confirm_frozen_test=args.i_confirm_frozen_test,
            protocol_version=args.protocol_version,
            provider_mode=provider_mode,
        )
    except protocol.TestSplitRefused as exc:
        print(f"Refused: {exc}", file=sys.stderr)
        return 2
    records = cases.select(cases.load_records(args.dataset), args.split, args.case_ids)
    if args.limit is not None:
        records = records[: args.limit]
    if not records:
        print("No cases selected.", file=sys.stderr)
        return 1
    state = protocol.protocol_state(ROOT)
    started = datetime.now(UTC)
    evaluation_id = args.evaluation_id or (
        f"{args.split}-{protocol.PROTOCOL_VERSION}-{args.provider}-{started:%Y%m%dT%H%M%SZ}"
    )
    out_dir = args.output_dir / evaluation_id
    output = out_dir / "records.jsonl"
    if args.provider == "fake":
        print("FAKE PROVIDER: plumbing check only; results are not model evidence.")
    provider = make_provider(args.provider, args.model_config)
    runner = make_runner(args.runner)
    context = harness.EvaluationContext(
        evaluation_id=evaluation_id,
        protocol_version=protocol.PROTOCOL_VERSION,
        protocol_status=state["status"],
        dataset_sha256=cases.dataset_sha256(args.dataset),
        split=args.split,
        split_sha256=protocol.split_sha256(args.dataset, args.split),
        code_sha=git_head(),
        measure_gpu=args.gpu_memory,
    )

    def progress(record) -> None:
        print(
            f"{record.case_id} arm {record.arm}: {record.disposition} "
            f"({record.failure_type}, {record.call_count} calls, {record.latency_s:.1f} s)"
        )

    if output.exists() and not args.resume:
        print(
            f"Refused: {output} exists; choose a new --evaluation-id or --resume.", file=sys.stderr
        )
        provider.close()
        return 2
    try:
        warmup = harness.warm_up(provider, runner, arms)
        summary = harness.run_evaluation(
            records,
            arms,
            workflow=harness.default_workflow(),
            provider=provider,
            runner=runner,
            context=context,
            output_path=output,
            resume=args.resume,
            progress=progress,
        )
        provider_info = provider.info().model_dump(mode="json")
    finally:
        provider.close()
    manifest = {
        "evaluation_id": evaluation_id,
        "command": [Path(sys.executable).name, *sys.argv],
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "protocol": state,
        "arms": {arm: protocol.arm_settings(arm).model_dump(mode="json") for arm in arms},
        "dataset": str(
            args.dataset.relative_to(ROOT) if args.dataset.is_relative_to(ROOT) else args.dataset
        ),
        "dataset_sha256": context.dataset_sha256,
        "split": args.split,
        "split_sha256": context.split_sha256,
        "cases": [record["id"] for record in records],
        "provider": provider_info,
        "runner": runner.info().model_dump(mode="json"),
        "warm_up": warmup,
        "arm_order": "rotated per case (case i starts with arm i mod number of arms)",
        "code_sha": context.code_sha,
        "test_authorization": authorization,
        "summary": summary,
    }
    (out_dir / "run.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
