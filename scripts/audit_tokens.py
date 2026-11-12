"""Audit prompt/completion lengths against the training context window.

The default mode is an offline regex proxy: it is fast, deterministic and
dependency-free, but it is **not** a tokenizer. Pass ``--tokenizer`` in the
training environment to get exact counts with the real chat template and
assistant end token used by :mod:`models.prompting`.

Examples::

    python scripts/audit_tokens.py data/curated.jsonl --max-length 2048
    python scripts/audit_tokens.py data/curated.jsonl --max-length 2048 \
        --tokenizer Qwen/Qwen2.5-Coder-3B-Instruct

Exit code is 1 when any record exceeds ``--max-length``; the report says which
method produced the numbers (NFR06: never present a proxy as an exact count).
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.ast_analyzer import analyze  # noqa: E402
from models.prompting import (  # noqa: E402
    assistant_end_token,
    build_messages,
    render_prompt,
)

_TOKEN_RE = re.compile(r"[A-Za-z_]\w*|\d+|[^\sA-Za-z0-9_]")


def _proxy_tokens(text: str) -> int:
    return len(_TOKEN_RE.findall(text))


def _percentile(values: list[int], fraction: float) -> int:
    ordered = sorted(values)
    if not ordered:
        return 0
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def _exact_lengths(tokenizer: Any, row: dict[str, Any]) -> tuple[int, int]:
    """Return ``(prompt_tokens, completion_tokens)`` with the real tokenizer."""
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
                return len(prefix_ids), len(full_ids) - len(prefix_ids)
        except (AttributeError, TypeError, ValueError):
            pass

    assistant_end_token(tokenizer)
    completion_ids = list(tokenizer(completion, add_special_tokens=False)["input_ids"])
    return len(prefix_ids), len(completion_ids) + 1


def _proxy_lengths(row: dict[str, Any]) -> tuple[int, int]:
    """Approximate lengths without a tokenizer (clearly labelled in the report)."""
    code = str(row["prompt"])
    messages = build_messages(code, analyze(code).findings)
    prompt_text = "\n\n".join(message["content"] for message in messages)
    return _proxy_tokens(prompt_text), _proxy_tokens(str(row["completion"]))


def audit(
    rows: list[dict[str, Any]],
    max_length: int,
    tokenizer: Any | None = None,
) -> dict[str, Any]:
    method = "exact tokenizer (shared chat template)" if tokenizer else "regex proxy"
    by_split: dict[str, list[int]] = {"train": [], "validation": [], "test": []}
    prompt_lengths: list[int] = []
    completion_lengths: list[int] = []
    over_limit: list[dict[str, Any]] = []

    for row in rows:
        if tokenizer is not None:
            prompt_tokens, completion_tokens = _exact_lengths(tokenizer, row)
        else:
            prompt_tokens, completion_tokens = _proxy_lengths(row)
        total = prompt_tokens + completion_tokens
        by_split.setdefault(str(row["split"]), []).append(total)
        prompt_lengths.append(prompt_tokens)
        completion_lengths.append(completion_tokens)
        if total > max_length:
            over_limit.append(
                {
                    "id": row["id"],
                    "split": row["split"],
                    "prompt": prompt_tokens,
                    "completion": completion_tokens,
                    "total": total,
                }
            )

    all_lengths = [length for lengths in by_split.values() for length in lengths]
    return {
        "method": method,
        "exact": tokenizer is not None,
        "max_length": max_length,
        "records": len(rows),
        "overall": {
            "max": max(all_lengths) if all_lengths else 0,
            "mean": round(statistics.mean(all_lengths), 1) if all_lengths else 0,
            "p50": _percentile(all_lengths, 0.50),
            "p90": _percentile(all_lengths, 0.90),
            "p95": _percentile(all_lengths, 0.95),
            "p99": _percentile(all_lengths, 0.99),
            "prompt_max": max(prompt_lengths) if prompt_lengths else 0,
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


def _load_rows(path: Path) -> list[dict[str, Any]]:
    rows = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    if not rows:
        raise SystemExit(f"Dataset is empty: {path}")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path, nargs="?", default=ROOT / "data/curated.jsonl")
    parser.add_argument("--max-length", type=int, default=2048)
    parser.add_argument(
        "--tokenizer",
        default=None,
        help="Model ID or local tokenizer path for exact counts; omit for a regex proxy.",
    )
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()

    tokenizer = None
    if args.tokenizer:
        try:
            from transformers import AutoTokenizer
        except ImportError as exc:
            raise SystemExit(
                "--tokenizer needs transformers; install training/requirements.txt "
                "or run the default regex proxy."
            ) from exc
        tokenizer = AutoTokenizer.from_pretrained(args.tokenizer, trust_remote_code=False)

    report = audit(_load_rows(args.dataset), args.max_length, tokenizer)
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
