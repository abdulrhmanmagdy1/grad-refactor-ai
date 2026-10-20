"""T04 benchmark: measure one local candidate model on the demonstration laptop.

Run with the training environment from the repository root, for example:

    .venv-train/Scripts/python.exe -X utf8 training/benchmark_model.py \
        --model-dir models/Qwen2.5-Coder-0.5B-Instruct \
        --model-id Qwen/Qwen2.5-Coder-0.5B-Instruct \
        --revision ea3f2471cf1b1f0db85067f1ef93848e38e88c25 \
        --license apache-2.0 \
        --out experiments/models/2026-10-20-qwen2.5-coder-0.5b-instruct-benchmark.json

The script loads the model through model_worker.TorchBackend, the same code path the
LocalProvider worker uses, and records load time, memory, latency, throughput, the raw
outputs on the pilot functions (training/pilot/functions.py, purpose "benchmark") and
their parse and rubric results, plus token lengths of maximal 3,000-character inputs.
Pilot results describe these pilot functions only; they are not an evaluation.
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from common import (
    ROOT,
    GpuSampler,
    gpu_used_mib,
    load_worker_module,
    nvidia_smi,
    require_free_disk,
)
from pilot.functions import maximal_inputs, pilot_functions

from refactor_ai import task_format
from refactor_ai.tasks import guard_clauses


def main() -> int:
    parser = argparse.ArgumentParser(description="T04 local model benchmark")
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--license", required=True, help="license verified from the model card")
    parser.add_argument("--dtype", default="bfloat16")
    parser.add_argument("--max-new-tokens", type=int, default=1024)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    require_free_disk(min_mb=1500, needed_mb=10)

    import psutil

    worker = load_worker_module()
    process = psutil.Process()
    record: dict = {
        "record": "T04 model benchmark (pilot functions; not an evaluation)",
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model_id": args.model_id,
        "model_revision": args.revision,
        "license": args.license,
        "dtype": args.dtype,
        "decoding": "greedy (temperature 0); repository sampling defaults replaced",
        "prompt_version": task_format.PROMPT_VERSION,
        "task_version": guard_clauses.TASK_VERSION,
        "command": " ".join([Path(sys.executable).name, *sys.argv]),
        "platform": platform.platform(),
        "gpu": nvidia_smi("name,memory.total,driver_version"),
        "other_gpu_processes_at_start": len(
            [
                line
                for line in (
                    subprocess.run(
                        ["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"],
                        capture_output=True,
                        text=True,
                        timeout=20,
                        check=False,
                    ).stdout.splitlines()
                )
                if line.strip()
            ]
        ),
        "ram_total_gb": round(psutil.virtual_memory().total / 2**30, 1),
        "ram_available_gb_at_start": round(psutil.virtual_memory().available / 2**30, 1),
        "disk_free_gb_at_start": round(shutil.disk_usage(ROOT).free / 1e9, 2),
        "failures": [],
    }
    gpu_before = gpu_used_mib()
    rss_before = process.memory_info().rss
    started = time.perf_counter()
    with GpuSampler() as load_sampler:
        backend = worker.TorchBackend(
            worker.LoadSettings(
                model_dir=args.model_dir,
                model_id=args.model_id,
                model_revision=args.revision,
                adapter_dir=None,
                adapter_id=None,
                adapter_sha256=None,
                device="cuda",
                dtype=args.dtype,
            )
        )
    load_wall_s = time.perf_counter() - started
    import torch

    record["versions"] = backend.versions
    record["load"] = {
        "wall_s_including_torch_import": round(load_wall_s, 2),
        "backend_load_s": round(backend.load_s, 2),
        "revision_verified": backend.revision_verified,
        "torch_allocated_mib_after_load": round(torch.cuda.memory_allocated() / 2**20, 1),
        "gpu_used_mib_before_load_all_processes": gpu_before,
        "gpu_used_mib_after_load_all_processes": gpu_used_mib(),
        "gpu_used_mib_peak_during_load_all_processes": load_sampler.peak,
        "rss_mib_before_load": round(rss_before / 2**20, 1),
        "rss_mib_after_load": round(process.memory_info().rss / 2**20, 1),
    }

    def request(messages, max_new_tokens=args.max_new_tokens, request_id="bench"):
        return worker.GenerateRequest(
            id=request_id,
            messages=messages,
            max_new_tokens=max_new_tokens,
            temperature=0.0,
            top_p=1.0,
            seed=42,
            max_input_tokens=32768,
            use_adapter=False,
        )

    def prefill_s(input_ids) -> float:
        """One forward pass over the prompt, keeping only the last logits like generate()."""
        with torch.inference_mode():
            torch.cuda.synchronize()
            begin = time.perf_counter()
            backend.model(input_ids=input_ids.to("cuda:0"), logits_to_keep=1)
            torch.cuda.synchronize()
            return time.perf_counter() - begin

    def with_oom_retry(label: str, action):
        """Run action(); on CUDA OOM record the failure, free the cache and retry once."""
        for attempt in (1, 2):
            try:
                return action()
            except (torch.OutOfMemoryError, worker.WorkerError) as exc:
                if isinstance(exc, worker.WorkerError) and "out of memory" not in exc.message:
                    raise
                torch.cuda.empty_cache()
                record["failures"].append(
                    {
                        "step": label,
                        "attempt": attempt,
                        "error": "CUDA out of memory",
                        "detail": str(exc).split(". GPU 0", 1)[0][:200],
                        "gpu_used_mib_all_processes_after": gpu_used_mib(),
                    }
                )
                print(f"{label}: CUDA out of memory (attempt {attempt})", flush=True)
                time.sleep(2)
        return None

    cases = pilot_functions("benchmark")
    # Decoding check with the worker's own generation config: no logits processor may
    # change the raw logits (no repetition penalty, top-k or temperature), and every
    # chosen token must be the argmax, i.e. pure greedy decoding.
    check_messages = task_format.build_refactor_messages(cases[0]["code"])
    check_ids = backend.prompt_ids(check_messages).to("cuda:0")

    def traced_generate():
        with torch.inference_mode():
            return backend.model.generate(
                input_ids=check_ids,
                attention_mask=torch.ones_like(check_ids),
                generation_config=backend.generation_config_for(
                    request(check_messages, max_new_tokens=64)
                ),
                output_scores=True,
                output_logits=True,
                return_dict_in_generate=True,
            )

    traced = with_oom_retry("greedy-check", traced_generate)
    if traced is not None:
        chosen = traced.sequences[0, check_ids.shape[1] :]
        record["greedy_check"] = {
            "steps": len(traced.scores),
            "scores_equal_raw_logits": all(
                torch.equal(s, raw) for s, raw in zip(traced.scores, traced.logits, strict=True)
            ),
            "chosen_tokens_are_argmax": all(
                int(chosen[i]) == int(traced.scores[i][0].argmax()) for i in range(len(chosen))
            ),
            "model_generation_config_after_load": {
                key: getattr(backend.model.generation_config, key, None)
                for key in ("do_sample", "temperature", "top_p", "top_k", "repetition_penalty")
            },
        }
        del traced

    backend.generate(request(check_messages, max_new_tokens=16))  # warm-up, not recorded
    results = []
    with GpuSampler() as bench_sampler:
        for case in cases:
            code = case["code"]
            messages = task_format.build_refactor_messages(code)

            def run_case(messages=messages, case_id=case["id"]):
                torch.cuda.reset_peak_memory_stats()
                wall_start = time.perf_counter()
                output = backend.generate(request(messages, request_id=case_id))
                wall_s = time.perf_counter() - wall_start
                return output, wall_s, prefill_s(backend.prompt_ids(messages))

            measured = with_oom_retry(case["id"], run_case)
            if measured is None:
                results.append({"case_id": case["id"], "label": "pilot", "error": "CUDA OOM"})
                continue
            output, wall_s, prefill = measured
            parsed = task_format.parse_refactor_output(output["text"])
            rubric = guard_clauses.rubric(code, parsed.code) if parsed.code else None
            reference = guard_clauses.to_guard_clauses(code)
            decode_tokens = max(output["completion_tokens"] - 1, 1)
            results.append(
                {
                    "case_id": case["id"],
                    "label": "pilot",
                    "input_chars": len(code),
                    "prompt_tokens": output["prompt_tokens"],
                    "completion_tokens": output["completion_tokens"],
                    "finish_reason": output["finish_reason"],
                    "wall_s": round(wall_s, 3),
                    "generation_s": output["generation_s"],
                    "prefill_s": round(prefill, 4),
                    "tokens_per_s_end_to_end": round(
                        output["completion_tokens"] / output["generation_s"], 2
                    ),
                    "decode_tokens_per_s": round(
                        decode_tokens / max(output["generation_s"] - prefill, 1e-6), 2
                    ),
                    "peak_vram_mib_torch": output["peak_vram_mb"],
                    "parse_error": parsed.error,
                    "parse_repaired": parsed.repaired,
                    "parse_notes": parsed.notes,
                    "explanation": parsed.explanation,
                    "rubric_passed": None if rubric is None else rubric.passed,
                    "rubric_checks": None if rubric is None else rubric.checks,
                    "rubric_reasons": None if rubric is None else rubric.reasons,
                    "same_as_reference_transformation": (
                        bool(parsed.code) and guard_clauses.same_code(parsed.code, reference)
                    ),
                    "raw_output": output["text"],
                }
            )
            print(
                f"{case['id']}: {output['completion_tokens']} tokens in "
                f"{output['generation_s']:.2f} s, parse={parsed.error or 'ok'}, "
                f"rubric={None if rubric is None else rubric.passed}",
                flush=True,
            )
    record["cases"] = results
    record["gpu_used_mib_peak_during_cases_all_processes"] = bench_sampler.peak

    # Repeatability of greedy decoding on two cases.
    repeat = []
    for case in cases[:2]:
        first = next(r for r in results if r["case_id"] == case["id"])
        if "raw_output" not in first:
            continue
        messages = task_format.build_refactor_messages(case["code"])
        again = with_oom_retry(
            case["id"] + "-repeat",
            lambda messages=messages, case=case: backend.generate(
                request(messages, request_id=case["id"] + "-repeat")
            ),
        )
        if again is not None:
            repeat.append(
                {"case_id": case["id"], "identical_text": again["text"] == first["raw_output"]}
            )
    record["greedy_repeatability"] = repeat

    # Token lengths of maximal inputs, and the long-context worst case.
    long_inputs = {}
    for name, code in maximal_inputs().items():
        check = guard_clauses.check_input(code)
        findings = [
            {"start_line": o.start_line, "end_line": o.end_line, "reason": o.reason}
            for o in check.opportunities
        ]
        single = backend.prompt_ids(task_format.build_refactor_messages(code)).shape[1]
        multi = backend.prompt_ids(task_format.build_refactor_messages(code, findings)).shape[1]
        entry = {
            "chars": len(code),
            "lines": len(code.splitlines()),
            "utf8_bytes": len(code.encode("utf-8")),
            "supported": check.supported,
            "reasons": check.reasons,
            "code_tokens": len(backend.tokenizer(code, add_special_tokens=False)["input_ids"]),
            "prompt_tokens_single_role": int(single),
            "prompt_tokens_with_findings": int(multi),
            "findings": len(findings),
        }
        target = guard_clauses.to_guard_clauses(code) if check.supported else None
        if target:
            completion = task_format.render_refactor_completion(
                "Handled each special case first with an early return or raise.", target
            )
            entry["reference_completion_tokens_with_end_of_turn"] = (
                len(backend.tokenizer(completion, add_special_tokens=False)["input_ids"]) + 1
            )
        long_inputs[name] = entry
    record["maximal_inputs"] = long_inputs
    instructions_only = backend.prompt_ids(task_format.build_refactor_messages("")).shape[1]
    record["prompt_overhead_tokens_empty_code"] = int(instructions_only)

    realistic = maximal_inputs()["realistic_ascii"]
    messages = task_format.build_refactor_messages(realistic)
    long_context: dict = {"input": "realistic_ascii"}
    torch.cuda.reset_peak_memory_stats()
    with GpuSampler() as long_sampler:
        natural = with_oom_retry(
            "long-natural",
            lambda: backend.generate(request(messages, max_new_tokens=2048, request_id="long")),
        )
        if natural is not None:
            natural_parsed = task_format.parse_refactor_output(natural["text"])
            long_context["natural_generation"] = {
                "prompt_tokens": natural["prompt_tokens"],
                "completion_tokens": natural["completion_tokens"],
                "finish_reason": natural["finish_reason"],
                "generation_s": natural["generation_s"],
                "parse_error": natural_parsed.error,
                "rubric_passed": (
                    guard_clauses.rubric(realistic, natural_parsed.code).passed
                    if natural_parsed.code
                    else None
                ),
                "raw_output": natural["text"],
            }
        ids = backend.prompt_ids(messages).to("cuda:0")
        forced_tokens = 1024

        def forced_run():
            with torch.inference_mode():
                torch.cuda.synchronize()
                begin = time.perf_counter()
                output = backend.model.generate(
                    input_ids=ids,
                    attention_mask=torch.ones_like(ids),
                    max_new_tokens=forced_tokens,
                    min_new_tokens=forced_tokens,
                    do_sample=False,
                )
                torch.cuda.synchronize()
                return output, time.perf_counter() - begin

        forced = with_oom_retry("long-forced-1024", forced_run)
        if forced is not None:
            generated = int(forced[0].shape[1] - ids.shape[1])
            long_context["forced_1024_new_tokens"] = {
                "prompt_tokens": int(ids.shape[1]),
                "generated_tokens": generated,
                "seconds": round(forced[1], 2),
                "tokens_per_s": round(generated / forced[1], 2),
            }
    long_context.update(
        peak_vram_mib_torch=round(torch.cuda.max_memory_allocated() / 2**20, 1),
        peak_reserved_mib_torch=round(torch.cuda.max_memory_reserved() / 2**20, 1),
        gpu_used_mib_peak_all_processes=long_sampler.peak,
    )
    record["long_context"] = long_context

    # Token sizes of structured outputs other roles produce (shapes only, not model output).
    sizes = []
    for case in cases:
        check = guard_clauses.check_input(case["code"])
        analysis = json.dumps(
            {
                "supported_task": check.supported,
                "findings": [
                    {
                        "type": guard_clauses.FINDING_TYPE,
                        "start_line": o.start_line,
                        "end_line": o.end_line,
                        "reason": o.reason,
                    }
                    for o in check.opportunities
                ],
                "unsupported_reason": None,
            }
        )
        review = json.dumps(
            {
                "verdict": "reject",
                "reasons": [
                    "The second guard clause inverts the comparison incorrectly.",
                    "The final return value differs from the original else branch.",
                ],
                "suggested_correction": guard_clauses.to_guard_clauses(case["code"]),
            }
        )
        sizes.append(
            {
                "case_id": case["id"],
                "analysis_json_tokens": len(backend.tokenizer(analysis)["input_ids"]),
                "review_json_with_correction_tokens": len(backend.tokenizer(review)["input_ids"]),
            }
        )
    record["structured_output_token_sizes"] = sizes
    record["rss_mib_end"] = round(process.memory_info().rss / 2**20, 1)
    peak_wset = getattr(process.memory_info(), "peak_wset", None)
    record["peak_working_set_mib"] = None if peak_wset is None else round(peak_wset / 2**20, 1)

    done = [r for r in results if "error" not in r]

    def median(values: list[float]) -> float | None:
        values = sorted(values)
        if not values:
            return None
        middle = len(values) // 2
        return values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2

    record["summary"] = {
        "cases": len(results),
        "cases_failed_oom": len(results) - len(done),
        "parsed_ok": sum(r["parse_error"] is None for r in done),
        "rubric_passed": sum(bool(r["rubric_passed"]) for r in done),
        "same_as_reference": sum(r["same_as_reference_transformation"] for r in done),
        "finish_length": sum(r["finish_reason"] == "length" for r in done),
        "median_generation_s": median([r["generation_s"] for r in done]),
        "max_generation_s": max((r["generation_s"] for r in done), default=None),
        "median_decode_tokens_per_s": median([r["decode_tokens_per_s"] for r in done]),
        "max_completion_tokens": max((r["completion_tokens"] for r in done), default=None),
        "max_peak_vram_mib_torch": max((r["peak_vram_mib_torch"] for r in done), default=None),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(record["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
